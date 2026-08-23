from contextlib import asynccontextmanager
from urllib.parse import urlencode
from fastapi import FastAPI, Request, Form, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
import threading
from .config import settings
from .db import Base, engine, get_db, SessionLocal
from .models import User, Payment, Server, ServerSnapshot, XUIClient, AppEvent
from .security import check_admin, encrypt_secret
from .seed import seed_users_if_empty
from .sync import sync_server, sync_all_servers
from .services import traffic_summary, traffic_daily
from .utils import jalali_date, jalali_datetime, parse_jalali_date, add_one_jalali_month, money, bytes_human, percent, due_meta, today_local, fa_digits
from .excel_import import import_users_xlsx

_stop_event = threading.Event()
_sync_thread = None

def _sync_loop():
    _stop_event.wait(10)
    while not _stop_event.is_set():
        try: sync_all_servers()
        except Exception: pass
        _stop_event.wait(max(60, settings.poll_seconds))

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try: seed_users_if_empty(db)
    finally: db.close()
    global _sync_thread
    _stop_event.clear()
    _sync_thread = threading.Thread(target=_sync_loop, name="xui-sync", daemon=True)
    _sync_thread.start()
    yield
    _stop_event.set()

app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["jdate"] = jalali_date
templates.env.filters["jdatetime"] = jalali_datetime
templates.env.filters["money"] = money
templates.env.filters["bytes"] = bytes_human
templates.env.filters["fa"] = fa_digits
templates.env.globals.update(due_meta=due_meta, percent=percent, today_local=today_local, app_name=settings.app_name)

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    public = path.startswith("/static/") or path in {"/login", "/health"}
    if not public and not request.session.get("admin"):
        return RedirectResponse("/login", status_code=303)
    return await call_next(request)

app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax", https_only=False, max_age=60*60*24*14)

@app.get("/health")
def health(): return {"ok": True, "service": settings.app_name}

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if request.session.get("admin"): return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if check_admin(username, password):
        request.session["admin"] = username
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html", context={"error": "نام کاربری یا رمز عبور اشتباه است"}, status_code=401)

@app.post("/logout")
def logout(request: Request):
    request.session.clear(); return RedirectResponse("/login", status_code=303)

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    today = today_local(); total_users = db.query(User).count(); unpaid = db.query(User).filter(User.payment_status == "unpaid").count()
    due_today = db.query(User).filter(User.payment_status == "unpaid", User.due_date == today).count(); overdue = db.query(User).filter(User.payment_status == "unpaid", User.due_date < today).count()
    missing_phone = db.query(User).filter(or_(User.phone.is_(None), User.phone == "")).count()
    total_due = db.query(func.coalesce(func.sum(User.fee_toman), 0)).filter(User.payment_status == "unpaid", User.due_date <= today).scalar() or 0
    servers = db.query(Server).order_by(Server.name).all(); server_cards = []
    for s in servers:
        snap = db.query(ServerSnapshot).filter(ServerSnapshot.server_id == s.id).order_by(ServerSnapshot.captured_at.desc()).first(); server_cards.append({"server": s, "snapshot": snap})
    upcoming = db.query(User).filter(User.payment_status == "unpaid", User.due_date.is_not(None)).order_by(User.due_date.asc()).limit(12).all()
    events = db.query(AppEvent).order_by(AppEvent.created_at.desc()).limit(6).all()
    return templates.TemplateResponse(request=request, name="dashboard.html", context={"stats": {"total": total_users, "unpaid": unpaid, "due_today": due_today, "overdue": overdue, "missing_phone": missing_phone, "total_due": total_due}, "server_cards": server_cards, "upcoming": upcoming, "events": events})

@app.get("/users", response_class=HTMLResponse)
def users_page(request: Request, q: str = "", status: str = "all", page: int = 1, db: Session = Depends(get_db)):
    query = db.query(User)
    if q.strip():
        like = f"%{q.strip()}%"; query = query.filter(or_(User.name.ilike(like), User.phone.ilike(like)))
    today = today_local()
    if status == "paid": query = query.filter(User.payment_status == "paid")
    elif status == "unpaid": query = query.filter(User.payment_status == "unpaid")
    elif status == "today": query = query.filter(User.payment_status == "unpaid", User.due_date == today)
    elif status == "overdue": query = query.filter(User.payment_status == "unpaid", User.due_date < today)
    elif status == "missing_phone": query = query.filter(or_(User.phone.is_(None), User.phone == ""))
    per_page = 50; total = query.count(); users = query.order_by(User.due_date.asc().nullslast(), User.name.asc()).offset((max(page,1)-1)*per_page).limit(per_page).all(); pages = max(1, (total + per_page - 1)//per_page)
    return templates.TemplateResponse(request=request, name="users.html", context={"users": users, "q": q, "status": status, "page": page, "pages": pages, "total": total})

@app.get("/users/new", response_class=HTMLResponse)
def user_new_page(request: Request): return templates.TemplateResponse(request=request, name="user_form.html", context={"user": None, "error": None})

@app.post("/users/new")
def user_new(request: Request, name: str = Form(...), phone: str = Form(""), due_date: str = Form(""), fee_toman: int = Form(200000), notes: str = Form(""), db: Session = Depends(get_db)):
    try: due = parse_jalali_date(due_date) if due_date else None
    except Exception as exc: return templates.TemplateResponse(request=request, name="user_form.html", context={"user": None, "error": str(exc)}, status_code=400)
    user = User(name=name.strip(), phone=phone.strip() or None, due_date=due, fee_toman=fee_toman, notes=notes.strip(), payment_status="unpaid"); db.add(user); db.commit(); db.refresh(user)
    return RedirectResponse(f"/users/{user.id}", status_code=303)

@app.get("/users/{user_id}", response_class=HTMLResponse)
def user_detail(request: Request, user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user: return RedirectResponse("/users", status_code=303)
    payments = db.query(Payment).filter(Payment.user_id == user.id).order_by(Payment.paid_at.desc()).all(); clients = db.query(XUIClient).filter(XUIClient.user_id == user.id, XUIClient.present.is_(True)).all()
    return templates.TemplateResponse(request=request, name="user_detail.html", context={"user": user, "payments": payments, "clients": clients})

@app.post("/users/{user_id}/edit")
def user_edit(user_id: int, name: str = Form(...), phone: str = Form(""), due_date: str = Form(""), fee_toman: int = Form(...), payment_status: str = Form(...), notes: str = Form(""), auto_reminder: str | None = Form(None), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user:
        user.name = name.strip(); user.phone = phone.strip() or None; user.fee_toman = fee_toman; user.payment_status = payment_status; user.notes = notes.strip(); user.auto_reminder = auto_reminder == "on"; user.due_date = parse_jalali_date(due_date) if due_date else None; db.commit()
    return RedirectResponse(f"/users/{user_id}", status_code=303)

@app.post("/users/{user_id}/mark-paid")
def mark_paid(user_id: int, amount_toman: int = Form(...), note: str = Form("تمدید یک‌ماهه"), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user:
        db.add(Payment(user_id=user.id, amount_toman=amount_toman, note=note)); user.payment_status = "paid"; user.due_date = add_one_jalali_month(user.due_date); db.commit()
    return RedirectResponse(f"/users/{user_id}", status_code=303)

@app.post("/users/{user_id}/reopen")
def reopen_due(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user: user.payment_status = "unpaid"; db.commit()
    return RedirectResponse(f"/users/{user_id}", status_code=303)

@app.get("/debts", response_class=HTMLResponse)
def debts(request: Request, db: Session = Depends(get_db)):
    today = today_local(); users = db.query(User).filter(User.payment_status == "unpaid", User.due_date <= today).order_by(User.due_date.asc()).all(); total = sum(u.fee_toman for u in users)
    return templates.TemplateResponse(request=request, name="debts.html", context={"users": users, "total": total})

@app.get("/payments", response_class=HTMLResponse)
def payments(request: Request, db: Session = Depends(get_db)):
    rows = db.query(Payment).order_by(Payment.paid_at.desc()).limit(300).all(); total = sum(p.amount_toman for p in rows)
    return templates.TemplateResponse(request=request, name="payments.html", context={"payments": rows, "total": total})

@app.get("/servers", response_class=HTMLResponse)
def servers_page(request: Request, db: Session = Depends(get_db)):
    servers = db.query(Server).order_by(Server.name).all(); cards=[]
    for s in servers:
        snap = db.query(ServerSnapshot).filter(ServerSnapshot.server_id==s.id).order_by(ServerSnapshot.captured_at.desc()).first(); cards.append({"server":s,"snapshot":snap})
    return templates.TemplateResponse(request=request, name="servers.html", context={"cards": cards})

@app.post("/servers")
def add_server(name: str = Form(...), base_url: str = Form(...), username: str = Form(...), password: str = Form(...), verify_ssl: str | None = Form(None), db: Session = Depends(get_db)):
    server = Server(name=name.strip(), base_url=base_url.strip().rstrip("/"), username=username.strip(), password_encrypted=encrypt_secret(password), verify_ssl=verify_ssl=="on"); db.add(server); db.commit(); db.refresh(server); sync_server(server.id)
    return RedirectResponse(f"/servers/{server.id}", status_code=303)

@app.get("/servers/{server_id}", response_class=HTMLResponse)
def server_detail(request: Request, server_id: int, db: Session = Depends(get_db)):
    server = db.get(Server, server_id)
    if not server: return RedirectResponse("/servers", status_code=303)
    snap = db.query(ServerSnapshot).filter(ServerSnapshot.server_id==server.id).order_by(ServerSnapshot.captured_at.desc()).first(); clients = db.query(XUIClient).filter(XUIClient.server_id==server.id, XUIClient.present.is_(True)).order_by(XUIClient.online.desc(), XUIClient.email.asc()).all(); users = db.query(User).order_by(User.name.asc()).all(); traffic = traffic_summary(db, server.id, 24)
    return templates.TemplateResponse(request=request, name="server_detail.html", context={"server":server,"snapshot":snap,"clients":clients,"users":users,"traffic":traffic,"chart_labels":[x["label"] for x in traffic["points"]],"chart_values":[x["value"] for x in traffic["points"]]})

@app.post("/servers/{server_id}/sync")
def server_sync(server_id: int): sync_server(server_id); return RedirectResponse(f"/servers/{server_id}", status_code=303)

@app.post("/servers/{server_id}/edit")
def server_edit(server_id: int, name: str = Form(...), base_url: str = Form(...), username: str = Form(...), password: str = Form(""), verify_ssl: str | None = Form(None), enabled: str | None = Form(None), db: Session = Depends(get_db)):
    server = db.get(Server, server_id)
    if server:
        server.name=name.strip(); server.base_url=base_url.strip().rstrip("/"); server.username=username.strip(); server.verify_ssl=verify_ssl=="on"; server.enabled=enabled=="on"
        if password.strip(): server.password_encrypted=encrypt_secret(password)
        db.commit()
    return RedirectResponse(f"/servers/{server_id}", status_code=303)

@app.post("/servers/{server_id}/delete")
def server_delete(server_id: int, db: Session = Depends(get_db)):
    server=db.get(Server, server_id)
    if server: db.delete(server); db.commit()
    return RedirectResponse("/servers", status_code=303)

@app.post("/xui/{client_id}/link")
def xui_link(client_id: int, user_id: int = Form(0), db: Session = Depends(get_db)):
    client = db.get(XUIClient, client_id)
    if client:
        client.user_id = user_id or None; db.commit(); return RedirectResponse(f"/servers/{client.server_id}", status_code=303)
    return RedirectResponse("/servers", status_code=303)

@app.get("/traffic", response_class=HTMLResponse)
def traffic_page(request: Request, server_id: int | None = None, db: Session = Depends(get_db)):
    servers = db.query(Server).order_by(Server.name).all(); selected = db.get(Server, server_id) if server_id else (servers[0] if servers else None); traffic = traffic_summary(db, selected.id, 24) if selected else {"total":0,"points":[],"snapshots":[]}; daily = traffic_daily(db, selected.id, 7) if selected else {"total":0,"points":[],"snapshots":[]}; latest = traffic["snapshots"][-1] if traffic["snapshots"] else None
    return templates.TemplateResponse(request=request, name="traffic.html", context={"servers":servers,"selected":selected,"traffic":traffic,"daily":daily,"latest":latest,"chart_labels":[x["label"] for x in traffic["points"]],"chart_values":[x["value"] for x in traffic["points"]],"daily_labels":[x["label"] for x in daily["points"]],"daily_values":[x["value"] for x in daily["points"]]})

@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, imported: str = "", db: Session = Depends(get_db)):
    return templates.TemplateResponse(request=request, name="settings.html", context={"settings":settings,"user_count":db.query(User).count(),"server_count":db.query(Server).count(),"imported":imported})

@app.post("/settings/import-excel")
async def settings_import_excel(file: UploadFile = File(...), db: Session = Depends(get_db)):
    name = (file.filename or "").lower()
    if not name.endswith(".xlsx"): return RedirectResponse("/settings?" + urlencode({"imported":"فقط فایل xlsx مجاز است"}), status_code=303)
    try:
        raw = await file.read(); result = import_users_xlsx(db, raw); msg = f"ورود اکسل انجام شد: {result['created']} جدید، {result['updated']} بروزرسانی، {result['skipped']} رد شد"
    except Exception as exc:
        db.rollback(); msg = f"خطا در ورود اکسل: {str(exc)[:250]}"
    return RedirectResponse("/settings?" + urlencode({"imported": msg}), status_code=303)
