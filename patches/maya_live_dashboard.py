# HESAB_MAYA_LIVE_DASHBOARD_V1
# Dynamic Maya1/S3/Maya4 live API view and verified manual per-client controls.
# Uses root-host UNIX socket bridge. Never touches finance or scheduler.
import json as _ml_json
import socket as _ml_socket
import secrets as _ml_secrets
import unicodedata as _ml_unicode
from pathlib import Path as _ml_Path
from datetime import datetime as _ml_datetime,timezone as _ml_tz
from concurrent.futures import ThreadPoolExecutor as _ml_Pool
from fastapi import Request as _ml_Request,Depends as _ml_Depends,Form as _ml_Form
from fastapi.responses import JSONResponse as _ml_JSON
from sqlalchemy.orm import Session as _ml_Session

_ML_SOCKET="/srv/maya-live/live.sock"
_ML_SERVERS=("maya1","maya-s3","maya4")
_ML_LABELS={"maya1":"مایا ۱","maya-s3":"مایا S3","maya4":"مایا ۴"}
_ML_APPROVAL_SHA="8e1509674cf0c06d1e8015064c8c3b69b76931311bce4489b1bbda49d50f37fb"

def _ml_call(action,server,**fields):
    if server not in _ML_SERVERS or action not in ("snapshot","toggle"):
        raise ValueError("Invalid Maya operation")
    request={"op":action,"server":server,**fields}
    with _ml_socket.socket(_ml_socket.AF_UNIX,_ml_socket.SOCK_STREAM) as sock:
        sock.settimeout(85 if action=="toggle" else 40)
        sock.connect(_ML_SOCKET)
        sock.sendall(_ml_json.dumps(request,ensure_ascii=False,separators=(",",":")).encode()+b"\n")
        sock.shutdown(_ml_socket.SHUT_WR)
        pieces=b""
        while len(pieces)<3000000 and not pieces.endswith(b"\n"):
            chunk=sock.recv(min(65536,3000000-len(pieces)))
            if not chunk:break
            pieces+=chunk
    if not pieces.endswith(b"\n"):
        raise ValueError("No complete bridge reply")
    response=_ml_json.loads(pieces)
    if response.get("ok") is not True:
        raise ValueError(str(response.get("error") or "Panel unavailable")[:150])
    return response

def _ml_normalize(value):
    normalized=_ml_unicode.normalize("NFKC",str(value or "")).casefold()
    return "".join(normalized.split())

def _ml_financial_mapping(db):
    states=_followup_states(db)
    index={}
    active={}
    for s in db.query(Subscription).all():
        if states.get(int(s.id))=="cut":continue
        key=_ml_normalize(s.display_name)
        index.setdefault(key,[]).append(s)
        active[int(s.id)]=s
    old={}
    try:
        path=_ml_Path("/srv/maya1-sync/mapping.json")
        if path.is_file() and path.stat().st_size<200000:
            raw=_ml_json.loads(path.read_text())
            if raw.get("format")=="MAYA1_CONTROL_MAPPING_V1" and raw.get("expected_sha")==_ML_APPROVAL_SHA:
                old=raw["mapping"]
    except (ValueError,KeyError,OSError):
        pass
    return index,active,old,states

def _ml_resolve(server,clients,db):
    index,active,old,states=_ml_financial_mapping(db)
    used=set()
    result=[]
    for c in clients:
        email=str(c.get("email") or "").strip()
        if not email:continue
        key=email.casefold()
        sid=None;reason="unmatched_review"
        # Maya1's earlier user-verified manual mapping survives a roster change.
        approved=old.get(key) if server=="maya1" else None
        if (isinstance(approved,dict) and approved.get("id") is not None
            and approved.get("reason") in ("confirmed","exact_approved")
            and int(approved["id"]) in active and int(approved["id"]) not in used):
            sid=int(approved["id"]);reason="approved_maya1"
        if sid is None:
            matches=index.get(_ml_normalize(email),[])
            if len(matches)==1 and int(matches[0].id) not in used:
                sid=int(matches[0].id);reason="exact_name"
        if sid is not None:used.add(sid)
        sub=active.get(sid) if sid else None
        def intval(v):
            try:return max(0,int(v or 0))
            except (TypeError,ValueError):return 0
        result.append({
          "email":email,"sid":sid,
          "name":sub.display_name if sub else "",
          "finance_state":(states.get(sid) or "normal") if sub else "",
          "expiry":sub.expiry_date.isoformat() if sub and sub.expiry_date else "",
          "reason":reason,
          "control_ambiguous":bool(c.get("control_ambiguous",False)),
          "client_enabled":bool(c.get("client_enabled",c.get("enabled",False))),
          "enabled":bool(c.get("enabled",False)),
          "up":intval(c.get("up_bytes")),"down":intval(c.get("down_bytes")),
          "quota":intval(c.get("quota_bytes")),
          "last_online":intval(c.get("last_online_ms"))
        })
    return result

def _ml_one(server,db):
    raw=_ml_call("snapshot",server)
    snap=raw["snapshot"]
    if snap.get("server")!=server or not isinstance(snap.get("clients"),list):
        raise ValueError("Unexpected remote Maya snapshot")
    clients=_ml_resolve(server,snap["clients"],db)
    return {"server":server,"label":_ML_LABELS[server],"ok":True,"rows":clients,
            "total":len(clients),"linked":sum(bool(x["sid"]) for x in clients),
            "unmatched":sum(not x["sid"] for x in clients),
            "enabled":sum(x["client_enabled"] for x in clients),
            "synced":snap.get("synced_at","")}

def _ml_data(request:_ml_Request,db:_ml_Session=_ml_Depends(get_db)):
    reports=[]
    # DB session is used sequentially for safety; each call is a live X-UI request.
    for name in _ML_SERVERS:
        try:reports.append(_ml_one(name,db))
        except Exception:
            reports.append({"server":name,"label":_ML_LABELS[name],"ok":False,
                            "message":"ارتباط زنده برقرار نیست یا پنل هنوز تنظیم نشده است."})
    return _ml_JSON({"ok":True,"servers":reports},headers={"Cache-Control":"no-store"})

def _ml_toggle(
    request:_ml_Request,
    server:str=_ml_Form(""),
    email:str=_ml_Form(""),
    sid:int=_ml_Form(0),
    expected:int=_ml_Form(-1),
    target:int=_ml_Form(-1),
    csrf:str=_ml_Form(""),
    db:_ml_Session=_ml_Depends(get_db),
):
    # Session and explicit CSRF; no browser may supply host/url/API credential.
    if (request.headers.get("origin")!="https://hesab.filmjadiid.ir" or
        request.headers.get("sec-fetch-site") not in (None,"same-origin")):
        return _ml_JSON({"ok":False,"error":"Invalid request origin"},status_code=403)
    token=request.session.get("maya1_control_csrf")
    if (not isinstance(token,str) or len(token)<30 or not _ml_secrets.compare_digest(token,csrf)):
        return _ml_JSON({"ok":False,"error":"Invalid session token"},status_code=403)
    if (server not in _ML_SERVERS or not email or len(email)>160 or sid<=0 or
        expected not in (0,1) or target not in (0,1) or expected==target):
        return _ml_JSON({"ok":False,"error":"Invalid operation"},status_code=400)
    try:
        live=_ml_one(server,db)
        matched=[r for r in live["rows"] if r["email"].casefold()==email.casefold()]
        if (len(matched)!=1 or matched[0]["sid"]!=sid or matched[0]["control_ambiguous"]
            or matched[0]["client_enabled"] is not bool(expected)):
            return _ml_JSON({"ok":False,"error":"وضعیت یا اتصال کاربر تغییر کرده؛ صفحه را به‌روز کن."},status_code=409)
        # One exact client and a verified expected state. No automatic retry.
        result=_ml_call("toggle",server,email=email,expected=bool(expected),target=bool(target))
        return _ml_JSON({"ok":True,"server":server,"email":email,
                         "enabled":result["client_enabled"],"confirmed":True},
                        headers={"Cache-Control":"no-store"})
    except Exception:
        return _ml_JSON({"ok":False,"error":"تغییر وضعیت تأیید نشد؛ وضعیت کاربر را در پنل بررسی کن."},status_code=502)

app.add_api_route("/control-room/maya-live/data",_ml_data,methods=["GET"])
app.add_api_route("/control-room/maya-live/toggle",_ml_toggle,methods=["POST"])

_ML_SECTION=r'''
<section id="ml-view" style="margin:22px 0;padding:14px;border:1px solid #35506b;border-radius:16px">
<style>
#ml-view{direction:rtl;color:#e8f3ff;background:#0f1a2a}
#ml-view h2{font-size:19px;margin:0 0 7px}#ml-view p{color:#a7bfd7;line-height:1.9;font-size:12px}
.ml-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.ml-card{padding:13px;border-radius:13px;border:1px solid #39536c;min-width:0;background:#142539}
.ml-card h3{margin:0 0 7px;font-size:15px}.ml-card .ml-meta{font-size:11px;color:#a7bfd7}
.ml-alert{padding:11px;border-radius:9px;border:1px solid #986c40;background:#3a2a20;color:#f1c49a}
.ml-search{width:100%;box-sizing:border-box;padding:10px;border:1px solid #56708c;
 background:#0b1a28;color:#e5f2ff;border-radius:9px;margin:10px 0;font:inherit}
.ml-scroll{max-height:530px;overflow:auto}
.ml-table{border-collapse:collapse;width:100%;min-width:400px}
.ml-table th,.ml-table td{border-bottom:1px solid #33465b;padding:8px 5px;text-align:right;font-size:11px}
.ml-table th{color:#acc9e2}.ml-table a{color:#add4fa}
.ml-btn{border:0;border-radius:8px;padding:7px 9px;color:#f8fbff;cursor:pointer;font:inherit;font-size:11px}
.ml-btn.off{background:#813a48}.ml-btn.on{background:#166452}
.ml-btn:disabled{opacity:.5;cursor:wait}.ml-note{color:#bacfe2;font-size:11px}
@media(max-width:1150px){.ml-grid{grid-template-columns:1fr}}
</style>
<h2>اتصال زنده به X-UI · مایا ۱، S3 و ۴</h2>
<p>اطلاعات مستقیم از API پنل خوانده می‌شود؛ تعداد کاربران ثابت نیست. قطع یا وصل فقط برای اکانت‌های تطبیق‌داده‌شده و با تأیید شما فعال است. تغییر وضعیت مالی یا قطع خودکار انجام نمی‌شود.</p>
<div class="ml-note" id="ml-status">در حال دریافت وضعیت زنده...</div>
<div class="ml-grid" id="ml-grid"></div>
<script>
(function(){
  "use strict";
  if(window.__hesabMayaLiveUI)return;window.__hesabMayaLiveUI=true;
  const root=document.getElementById("ml-grid"),status=document.getElementById("ml-status");
  const csrf="{{ mc.csrf_token }}";
  let sending=false;
  const labels={"maya1":"مایا ۱","maya-s3":"مایا S3","maya4":"مایا ۴"};
  const make=(tag,text,parent)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=String(text);if(parent)parent.append(el);return el;};
  const fmt=n=>Number(n||0).toLocaleString("fa-IR");
  const gig=n=>(Number(n||0)/1073741824).toFixed(2)+" GB";
  const normalize=s=>String(s||"").toLowerCase().replace(/ي/g,"ی").replace(/ك/g,"ک");
  async function refresh(){
    if(sending||document.hidden)return;
    try{
      const res=await fetch("/control-room/maya-live/data",{credentials:"same-origin",cache:"no-store"});
      if(!res.ok)throw Error("HTTP "+res.status);
      const obj=await res.json();if(!obj.ok)throw Error("No data");
      root.replaceChildren();
      let ok=0;
      for(const server of obj.servers){
        const card=make("article",undefined,root);card.className="ml-card";
        make("h3",labels[server.server]||server.server,card);
        if(!server.ok){const m=make("p",server.message||"اطلاعات در دسترس نیست",card);m.className="ml-alert";continue;}
        ok++;
        make("div","کل "+fmt(server.total)+" · متصل "+fmt(server.linked)+" · نامنطبق "+fmt(server.unmatched)+" · فعال "+fmt(server.enabled),card).className="ml-meta";
        const input=make("input",undefined,card);input.type="search";input.placeholder="جست‌وجوی کاربر";input.className="ml-search";
        const scroller=make("div",undefined,card);scroller.className="ml-scroll";
        const table=make("table",undefined,scroller);table.className="ml-table";
        const head=make("thead",undefined,table),tr=make("tr",undefined,head);
        for(const h of ["اکانت X-UI / داشبورد","وضعیت","مصرف","کنترل"])make("th",h,tr);
        const body=make("tbody",undefined,table);
        const rows=[];
        for(const item of server.rows){
          const r=make("tr",undefined,body);
          const cell=make("td",undefined,r);
          make("strong",item.email,cell);
          if(item.sid){
            const link=make("a","#"+item.sid+" · "+item.name,cell);
            link.href="/users/"+encodeURIComponent(item.sid);
            link.style.display="block";
          } else make("div","تطبیق تأیید نشده",cell).className="ml-note";
          make("td",!item.client_enabled?"غیرفعال":(item.enabled?"فعال":"روشن در تنظیمات / اتصال غیرفعال"),r);
          make("td",gig(item.up+item.down),r);
          const action=make("td",undefined,r);
          if(item.sid&&!item.control_ambiguous){
            const btn=make("button",item.client_enabled?"قطع کاربر":"وصل کاربر",action);
            btn.type="button";btn.className="ml-btn "+(item.client_enabled?"off":"on");
            btn.onclick=async()=>{
              if(sending||!confirm("تغییر وضعیت "+item.email+" روی "+labels[server.server]+" انجام شود؟"))return;
              sending=true;btn.disabled=true;
              const form=new FormData();
              for(const [k,v] of Object.entries({server:server.server,email:item.email,sid:item.sid,expected:item.client_enabled?1:0,target:item.client_enabled?0:1,csrf}))form.set(k,String(v));
              try{
                const response=await fetch("/control-room/maya-live/toggle",{method:"POST",body:form,credentials:"same-origin",headers:{"X-Requested-With":"XMLHttpRequest"}});
                const data=await response.json();if(!response.ok||!data.ok)throw Error(data.error||"ناموفق");
                status.textContent="✓ تغییر وضعیت کاربر روی سرور تأیید شد.";
              }catch(err){status.textContent="عملیات نامطمئن: "+err.message+"؛ پیش از تکرار پنل را بررسی کن."}
              finally{sending=false;await refresh();}
            };
          } else make("span",item.control_ambiguous?"تعارض در چند ورودی؛ بررسی در پنل":"نیازمند تطبیق",action).className="ml-note";
          const q=normalize([item.email,item.name,item.sid||""].join(" "));
          rows.push({r,q});
        }
        input.oninput=()=>{const q=normalize(input.value.trim());for(const item of rows)item.r.hidden=!item.q.includes(q)};
      }
      status.textContent="گزارش زنده: "+fmt(ok)+" سرور متصل · "+new Date().toLocaleTimeString("fa-IR");
      if(obj.servers.some(x=>x.server==="maya1"&&x.ok)){
        const old=document.querySelector(".mc-root");if(old)old.style.display="none";
      }
    }catch(_){status.textContent="دریافت گزارش زنده ناموفق بود. داده قدیمی به‌عنوان زنده نمایش داده نمی‌شود.";}
  }
  refresh();setInterval(refresh,20000);
})();
</script>
</section>
'''
_ml_tpl=TEMPLATES.get("control_room.html","")
if not _ml_tpl or "{% endblock %}" not in _ml_tpl:
    raise RuntimeError("Maya live dashboard: control-room page unavailable")
_ml_end=_ml_tpl.rfind("{% endblock %}")
_ml_tpl=_ml_tpl[:_ml_end]+_ML_SECTION+"\n"+_ml_tpl[_ml_end:]
TEMPLATES["control_room.html"]=_ml_tpl
if hasattr(env.loader,"mapping"):env.loader.mapping.update(TEMPLATES)
