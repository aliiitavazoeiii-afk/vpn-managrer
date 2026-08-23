from datetime import datetime
from sqlalchemy.orm import Session
from .db import SessionLocal
from .models import Server, ServerSnapshot, XUIClient, User, AppEvent
from .xui import XUIClientAPI, parse_clients


def _norm(s: str | None) -> str:
    return " ".join((s or "").strip().lower().split())


def sync_server(server_id: int) -> dict:
    db: Session = SessionLocal()
    try:
        server = db.query(Server).filter(Server.id == server_id).first()
        if not server:
            raise RuntimeError("سرور پیدا نشد")
        api = XUIClientAPI(server)
        data = api.collect()
        clients = parse_clients(data["inbounds"], data["onlines"], data["last_online"])
        now = datetime.utcnow()
        user_map = {_norm(u.name): u.id for u in db.query(User).all()}
        existing = {c.client_key: c for c in db.query(XUIClient).filter(XUIClient.server_id == server.id).all()}
        for c in existing.values():
            c.present = False
            c.online = False
        total_up = total_down = 0
        for item in clients:
            key = item["client_key"]
            row = existing.get(key)
            if not row:
                row = XUIClient(server_id=server.id, client_key=key, email=item["email"])
                db.add(row)
            row.inbound_id = item["inbound_id"]
            row.email = item["email"]
            row.protocol = item["protocol"]
            row.enabled = item["enabled"]
            row.present = True
            row.online = item["online"]
            row.up = item["up"]
            row.down = item["down"]
            row.total = item["total"]
            row.expiry_time = item["expiry_time"]
            row.last_online = item["last_online"]
            row.synced_at = now
            if row.user_id is None:
                row.user_id = user_map.get(_norm(item["email"]))
            total_up += row.up
            total_down += row.down
        st = data["status"]
        mem = st.get("mem") or {}
        disk = st.get("disk") or {}
        netio = st.get("netIO") or {}
        nett = st.get("netTraffic") or {}
        xray = st.get("xray") or {}
        snap = ServerSnapshot(
            server_id=server.id,
            captured_at=now,
            cpu=float(st.get("cpu") or 0),
            mem_current=int(mem.get("current") or 0),
            mem_total=int(mem.get("total") or 0),
            disk_current=int(disk.get("current") or 0),
            disk_total=int(disk.get("total") or 0),
            net_up_bps=int(netio.get("up") or 0),
            net_down_bps=int(netio.get("down") or 0),
            net_sent_total=int(nett.get("sent") or 0),
            net_recv_total=int(nett.get("recv") or 0),
            client_up_total=total_up,
            client_down_total=total_down,
            online_count=sum(1 for c in clients if c["online"]),
            client_count=len(clients),
            xray_state=str(xray.get("state") or "unknown"),
            uptime=int(st.get("uptime") or 0),
        )
        db.add(snap)
        server.last_sync_at = now
        server.last_error = ""
        db.commit()
        return {"ok": True, "clients": len(clients), "online": snap.online_count}
    except Exception as exc:
        db.rollback()
        server = db.query(Server).filter(Server.id == server_id).first()
        if server:
            server.last_sync_at = datetime.utcnow()
            server.last_error = str(exc)[:1000]
            db.add(AppEvent(kind="server_sync_error", message=f"{server.name}: {exc}"))
            db.commit()
        return {"ok": False, "error": str(exc)}
    finally:
        db.close()


def sync_all_servers():
    db = SessionLocal()
    try:
        ids = [s.id for s in db.query(Server).filter(Server.enabled.is_(True)).all()]
    finally:
        db.close()
    return [sync_server(i) for i in ids]
