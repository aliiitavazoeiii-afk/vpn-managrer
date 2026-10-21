# HESAB_WAITING_SERVER_STATUS_V1
# Read-only per-account connection labels in existing /followups cards.
# Absolutely no SSH, XUI or finance mutations. No remote calls on the waiting page.
import json as _wss_json
import sqlite3 as _wss_sqlite
import time as _wss_time
from pathlib import Path as _wss_Path
from fastapi import Request as _wss_Request,Depends as _wss_Depends
from fastapi.responses import JSONResponse as _wss_JSON
from sqlalchemy.orm import Session as _wss_Session

_WSS_SQLITE=_wss_Path("/srv/maya-live/usage_v1.sqlite3")
_WSS_SHAHAN=_wss_Path("/srv/maya-live/shahan_waiting_status_v1.json")
_WSS_MAYA_LABEL={"maya1":"مایا ۱","maya-s3":"مایا ۳","maya4":"مایا ۴"}

def _wss_maya(db):
    result={}
    if not _WSS_SQLITE.is_file():return result,False
    try:
        with _wss_sqlite.connect("file:"+str(_WSS_SQLITE)+"?mode=ro",uri=True,timeout=2) as con:
            data=list(con.execute("""
              SELECT server,email,client_enabled,inbound_enabled,effective_enabled,
                     quota_bytes,used_bytes,traffic_expiry_ms,sampled_at
              FROM client_access_state
              WHERE server IN ('maya1','maya-s3','maya4')
            """))
    except (_wss_sqlite.Error,OSError):
        return {},False
    by_server={s:[] for s in _WSS_MAYA_LABEL}
    cache={}
    now=int(_wss_time.time())
    for server,email,client,inbound,effective,quota,used,expiry,stamp in data:
        if server not in by_server:continue
        key=(server,str(email).strip().casefold())
        cache[key]=(bool(client),bool(inbound),bool(effective),
                    max(0,int(quota)),max(0,int(used)),max(0,int(expiry)),int(stamp))
        by_server[server].append({"email":email,"client_enabled":bool(client),
                                  "enabled":bool(effective),"control_ambiguous":False})
    for server,clients in by_server.items():
        if not clients:continue
        # Local-only mappings; reading verified manual links is allowed.
        # Never run _ml_one(), which would request XUI over the network.
        try:
            resolved=_ml_resolve(server,clients,db)
        except Exception:
            continue
        for r in resolved:
            sid=r["sid"]
            if not sid:continue
            k=(server,r["email"].strip().casefold())
            if k not in cache:continue
            client,inbound,effective,quota,used,expiry,stamp=cache[k]
            if stamp<=0 or now-stamp>900 or now-stamp<(-120):
                status="unknown"
                detail="نمونه مایا قدیمی است؛ وضعیت کنونی تأیید نشده"
            elif not client:
                status="blocked";detail="کلاینت در X-UI غیرفعال است"
            elif not inbound or not effective:
                status="blocked";detail="دسترسی مؤثر در X-UI غیرفعال است"
            elif expiry and expiry<=now*1000:
                status="blocked";detail="انقضای ترافیک در X-UI فرا رسیده"
            elif quota and used>=quota:
                status="blocked";detail="سقف مصرف X-UI تکمیل شده"
            else:
                status="active";detail="کلاینت در X-UI مجاز است؛ الزاماً آنلاین نیست"
            result.setdefault(int(sid),[]).append({
              "server":_WSS_MAYA_LABEL[server],"status":status,
              "username":r["email"],"detail":detail,
              "sampled_at":stamp,"source":"maya_sample"
            })
    return result,True

def _wss_shahan():
    if not _WSS_SHAHAN.is_file() or _WSS_SHAHAN.stat().st_size>200000:return {}
    try:
        obj=_wss_json.loads(_WSS_SHAHAN.read_text(encoding="utf8"))
        if obj.get("format")!="SHAHAN_WAITING_STATUS_V1" or not isinstance(obj.get("mapped"),list):
            return {}
        imported=int(obj.get("imported_at") or 0)
        result={}
        for item in obj["mapped"]:
            sid=item.get("sid")
            if type(sid) is not int or sid<1:continue
            raw=item.get("reported_state")
            if raw=="enabled_reported":
                status="reported_active";detail="در آخرین فایل دستی شاهان فعال گزارش شده؛ وضعیت زنده نیست"
            elif raw in ("disabled_reported","not_present"):
                status="reported_blocked";detail="در آخرین فایل دستی شاهان غیرفعال گزارش شده؛ وضعیت زنده نیست"
            else:
                status="unknown";detail="وضعیت SSH از گزارش قبلی مشخص نیست"
            result.setdefault(sid,[]).append({
              "server":"SSH شاهان","status":status,
              "username":str(item.get("ssh") or "")[:128],
              "detail":detail,"sampled_at":imported,"source":"shahan_manual"
            })
        return result
    except (ValueError,KeyError,OSError,TypeError):
        return {}

def _wss_status_data(request:_wss_Request,db:_wss_Session=_wss_Depends(get_db)):
    # The dashboard's existing session middleware protects operator GET routes.
    maya,available=_wss_maya(db)
    shahan=_wss_shahan()
    for sid,items in shahan.items():
        maya.setdefault(sid,[]).extend(items)
    # Return only accounts that are currently in the waiting workflow.
    waiting={int(sid) for sid,state in _followup_states(db).items() if state=="waiting"}
    filtered={str(sid):items for sid,items in maya.items() if sid in waiting}
    return _wss_JSON({
      "ok":True,"statuses":filtered,"maya_samples_available":available,
      "shahan_manual_report":bool(_WSS_SHAHAN.is_file())
    },headers={"Cache-Control":"private, no-store"})

app.add_api_route("/followups/connection-status",_wss_status_data,methods=["GET"])

_WSS_STYLE=r'''
<style>
/* Strictly single-line, no card height increase, no column-width change. */
.waiting-head-name>small .wss-summary{
 display:inline-block;vertical-align:middle;max-width:min(22vw,265px);
 min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
 margin-inline-start:8px;direction:rtl;font-size:10px;line-height:1.2
}
.wss-summary:empty{display:none}
.wss-pill{font:inherit;font-size:10px;white-space:nowrap;vertical-align:baseline}
.wss-pill+.wss-pill:before{content:" · ";color:#66748d}
.wss-active{color:#72d4a4}.wss-blocked{color:#ff9fa9}
.wss-unknown{color:#a6adbf}.wss-reported{color:#e4c487}
.waiting-identity>span .wss-child{
 display:inline-block;max-width:min(55vw,390px);white-space:nowrap;
 overflow:hidden;text-overflow:ellipsis;vertical-align:middle;
 margin-inline-start:5px;font-size:10px;line-height:1.2
}
@media(max-width:1200px){.waiting-head-name>small .wss-summary{max-width:170px}}
@media(max-width:650px){.waiting-head-name>small .wss-summary{max-width:55vw}}
</style>
'''

_WSS_JS=r'''
<script>
(function(){
  "use strict";
  const list=document.querySelector(".waiting-list");
  if(!list||window.__hesabWaitingStatusV1)return;
  window.__hesabWaitingStatusV1=true;
  let cache=null,lastLoaded=0,busy=false;
  const names={
    active:"فعال",blocked:"مسدود",unknown:"نامشخص",
    reported_active:"فعال*",reported_blocked:"مسدود*"
  };
  const cls=s=>s==="active"?"wss-active":s==="blocked"?"wss-blocked":
   s.startsWith("reported_")?"wss-reported":"wss-unknown";
  function compact(items){
    if(!items||!items.length)return [{server:"—",status:"unknown",detail:"برای این حساب اتصال تأییدشده‌ای ثبت نشده"}];
    return items;
  }
  function write(slot,entries,prefix){
    if(!slot)return;
    slot.replaceChildren();
    const labels=[];
    entries.forEach((c,i)=>{
      const el=document.createElement("span");
      el.className="wss-pill "+cls(c.status);
      el.textContent=c.server+" "+(names[c.status]||"نامشخص");
      const when=c.source==="shahan_manual"?" (گزارش دستی، غیرزنده)":"";
      const detail=c.detail||"";
      el.title=(prefix?prefix+" · ":"")+c.server+" / "+(c.username||"")+
        ": "+detail+when;
      slot.append(el);
      labels.push(el.title);
    });
    slot.title=labels.join("\n");
  }
  function apply(){
    if(!cache)return;
    const statuses=cache.statuses||{};
    list.querySelectorAll("[data-waiting-group]").forEach(group=>{
      const all=[];
      group.querySelectorAll("[data-wss-sid]").forEach(child=>{
        const sid=child.getAttribute("data-wss-sid");
        const name=child.querySelector(".waiting-identity a")?.textContent?.trim()||("#"+sid);
        const entries=compact(statuses[sid]);
        write(child.querySelector(".wss-child"),entries,name);
        entries.forEach(c=>all.push({...c,accountName:name}));
      });
      // Distinct server+state labels; full per-child details stay in hover.
      const shown=new Map();
      const full=[];
      all.forEach(c=>{
        const key=c.server+"|"+c.status;
        if(!shown.has(key))shown.set(key,c);
        full.push(c.accountName+" · "+c.server+" · "+(c.username||"")+" : "+(c.detail||""));
      });
      const slot=group.querySelector(".wss-summary");
      write(slot,[...shown.values()],"");
      if(slot)slot.title=full.join("\n")||
        "برای این پرداخت‌کننده هنوز اطلاعات اتصال ثبت نشده";
    });
  }
  async function refresh(force){
    if(busy)return;
    if(!force&&cache&&Date.now()-lastLoaded<60000){apply();return;}
    busy=true;
    try{
      const res=await fetch("/followups/connection-status",{
        credentials:"same-origin",cache:"no-store"
      });
      if(!res.ok)throw Error("HTTP "+res.status);
      const data=await res.json();
      if(!data.ok||!data.statuses)throw Error("Invalid reply");
      cache=data;lastLoaded=Date.now();
      apply();
    }catch(_){
      cache={statuses:{}};apply();
    }finally{busy=false;}
  }
  // The existing waiting page swaps only the list's direct children after a
  // payment. Watch those replacements without introducing extra XUI requests.
  new MutationObserver(()=>refresh(false)).observe(list,{childList:true});
  refresh(true);
})();
</script>
'''

_wss_tpl=TEMPLATES.get("followups.html","")
if _wss_tpl.count('<div class="waiting-head-name">')!=1:
    raise RuntimeError("Waiting compact name cell missing or changed")
if _wss_tpl.count('<div class="waiting-service"')!=1:
    raise RuntimeError("Waiting child row marker missing")
if _wss_tpl.count('<span>انقضا {{ s.expiry_date|jdate }}</span>')!=1:
    raise RuntimeError("Waiting child expiry marker missing")
_wss_tpl=_wss_tpl.replace(
  '<div class="waiting-head-name">\n        <small>نام</small>',
  '<div class="waiting-head-name">\n        <small>نام <span class="wss-summary" title=""></span></small>',
  1)
if '<span class="wss-summary"' not in _wss_tpl:
    raise RuntimeError("Waiting summary anchor missing")
_wss_tpl=_wss_tpl.replace(
  '<div class="waiting-service"',
  '<div data-wss-sid="{{ s.id }}" class="waiting-service"',1)
_wss_tpl=_wss_tpl.replace(
  '<span>انقضا {{ s.expiry_date|jdate }}</span>',
  '<span>انقضا {{ s.expiry_date|jdate }} <span class="wss-child"></span></span>',1)
_wss_tpl=_wss_tpl.replace("{% block content %}","{% block content %}"+_WSS_STYLE,1)
_wss_head,_wss_tail=_wss_tpl.rsplit("{% endblock %}",1)
_wss_tpl=_wss_head+_WSS_JS+"\n{% endblock %}"+_wss_tail
TEMPLATES["followups.html"]=_wss_tpl
if hasattr(env.loader,"mapping"):env.loader.mapping.update(TEMPLATES)
