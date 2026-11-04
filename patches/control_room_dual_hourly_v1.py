# HESAB_CONTROL_ROOM_DUAL_HOURLY_SIMPLE_V1
# Read-only, small V10 add-on: two foreign paths per Maya server, hourly snapshot.
# No shared Caddy route, agent, receiver, tunnel/probe/XUI/finance mutation.
import ipaddress as _dh1_ip
import json as _dh1_json
import secrets as _dh1_sec
import time as _dh1_time
from pathlib import Path as _dh1_Path
from fastapi import Request as _dh1_Request
from fastapi.responses import JSONResponse as _dh1_JSON
from jinja2 import Environment as _dh1_Jinja

_DH1_PATH = _dh1_Path("/srv/maya-live/dual_hourly_v1.json")
_DH1_NAMES = ("maya1", "maya-s3", "maya4")
_DH1_ROLES = ("backhaul", "mieru")
_DH1_MAX_AGE = 4500  # 75 minutes: 1h run plus tolerance

def _dh1_auth(request):
    token = request.session.get("maya1_control_csrf")
    header = request.headers.get("x-control-csrf", "")
    return bool(isinstance(token, str) and len(token) >= 30
                and _dh1_sec.compare_digest(token, header)
                and request.headers.get("sec-fetch-site") in (None, "same-origin"))

def _dh1_clean_path(data):
    if not isinstance(data, dict):
        return {"state": "unknown"}
    state = data.get("state")
    if state not in ("healthy", "down", "stale", "unknown"):
        state = "unknown"
    ip = data.get("ip")
    try:
        if not isinstance(ip, str):
            raise ValueError("invalid")
        ip = str(_dh1_ip.IPv4Address(ip))
        if not _dh1_ip.ip_address(ip).is_global:
            ip = None
    except ValueError:
        ip = None
    ms = data.get("https_avg_ms")
    if type(ms) is not int or not 0 <= ms <= 120000:
        ms = None
    passed, total = data.get("https_passed"), data.get("https_total")
    if type(passed) is not int or type(total) is not int or total != 3 or not 0 <= passed <= total:
        passed, total = None, None
    return {"ip": ip, "state": state, "https_avg_ms": ms,
            "https_passed": passed, "https_total": total}

def _dh1_status(request: _dh1_Request):
    if not _dh1_auth(request):
        return _dh1_JSON({"ok": False}, status_code=403)
    output = {sid: {"state": "not_configured"} for sid in _DH1_NAMES}
    now = int(_dh1_time.time())
    try:
        if not _DH1_PATH.is_file() or _DH1_PATH.stat().st_size > 16000:
            raise OSError("no valid snapshot")
        doc = _dh1_json.loads(_DH1_PATH.read_text(encoding="utf8"))
        collected = doc.get("collected_at")
        if doc.get("format") != "HESAB_DUAL_HOURLY_V1" or type(collected) is not int:
            raise ValueError("format")
        age = now - collected
        if age < -60 or age > _DH1_MAX_AGE:
            output = {sid: {"state": "stale"} for sid in _DH1_NAMES}
        else:
            for sid in _DH1_NAMES:
                info = doc.get("servers", {}).get(sid, {})
                state = info.get("state")
                if state not in ("ok", "stale", "unavailable", "not_configured"):
                    state = "unavailable"
                if state in ("ok", "stale"):
                    paths = info.get("paths", {})
                    if not isinstance(paths, dict):
                        paths = {}
                    output[sid] = {
                        "state": state, "age_s": age,
                        "paths": {role: _dh1_clean_path(paths.get(role))
                                  for role in _DH1_ROLES},
                    }
                else:
                    output[sid] = {"state": state}
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        output = {sid: {"state": "unavailable"} for sid in _DH1_NAMES}
    return _dh1_JSON({"ok": True, "servers": output},
                     headers={"Cache-Control": "private, no-store"})

if any(getattr(r, "path", None) == "/control-room/dual-hourly/status"
       for r in app.router.routes):
    raise RuntimeError("Dual hourly route already installed")
app.add_api_route("/control-room/dual-hourly/status", _dh1_status, methods=["GET"])

_DH1_HTML = r'''
<style id="dh1-style">
#c2-root .dh1-root{margin:14px 0 20px;direction:rtl}
#c2-root .dh1-heading{display:flex;align-items:center;justify-content:space-between;
  flex-wrap:wrap;gap:8px;margin-bottom:10px;color:#ecebff}
#c2-root .dh1-heading h2{font-size:15px!important;font-weight:800!important;margin:0!important}
#c2-root .dh1-note{font-size:11px;color:#b4b9dc}
#c2-root .dh1-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
#c2-root .dh1-card{padding:13px;border-radius:15px;border:1px solid #55547888;
  background:#16192e;color:#eceeff;min-width:0}
#c2-root .dh1-name{font-weight:800;font-size:13px;margin:0 0 9px}
#c2-root .dh1-row{display:grid;grid-template-columns:68px minmax(0,1fr) auto;
  align-items:center;column-gap:8px;row-gap:3px;padding:9px 0;
  border-top:1px solid #ffffff17;font-size:11px}
#c2-root .dh1-role{font-weight:750;color:#e4e1fa}
#c2-root .dh1-ip{direction:ltr;unicode-bidi:isolate;font-variant-numeric:tabular-nums;
  text-align:left;overflow:hidden;text-overflow:ellipsis}
#c2-root .dh1-pill{font-weight:800;font-size:10px;border:1px solid #6e729077;
  padding:3px 5px;border-radius:7px;white-space:nowrap}
#c2-root .dh1-pill.ok{color:#84dfac;border-color:#5ab57f77}
#c2-root .dh1-pill.down{color:#ffa1aa;border-color:#eb708977}
#c2-root .dh1-meta{font-size:10px;color:#aeb5d2;margin-top:8px}
@media(max-width:920px){#c2-root .dh1-grid{grid-template-columns:1fr}}
</style>
<section id="dh1-root" class="dh1-root" aria-label="وضعیت مسیرهای خارجی">
  <div class="dh1-heading">
    <h2>وضعیت دو مسیر خارجی</h2>
    <span class="dh1-note">بررسی خودکار هر ساعت · زمان پاسخ HTTPS، نه پینگ ICMP</span>
  </div>
  <div id="dh1-grid" class="dh1-grid"></div>
</section>
'''
_DH1_JS = r'''
<script id="dh1-script">
(function(){
"use strict";
if(window.__HESAB_DUAL_HOURLY_V1)return;
window.__HESAB_DUAL_HOURLY_V1=true;
const grid=document.getElementById("dh1-grid");
if(!grid)return;
const names={maya1:"مایا ۱","maya-s3":"مایا ۳",maya4:"مایا ۴"};
const csrf="{{ ctrl_csrf }}";
function add(parent,tag,content,cls){
 const node=document.createElement(tag);
 if(cls)node.className=cls;
 if(content!=null)node.textContent=String(content);
 parent.appendChild(node);return node;
}
function label(s){
 return s==="healthy"?"Healthy":s==="down"?"Down":"نامشخص";
}
function render(doc){
 grid.replaceChildren();
 for(const sid of ["maya1","maya-s3","maya4"]){
  const item=(doc&&doc[sid])||{state:"unavailable"};
  const card=add(grid,"div",null,"dh1-card");
  add(card,"div",names[sid],"dh1-name");
  for(const role of ["backhaul","mieru"]){
   const raw=item.paths&&item.paths[role]||{};
   const valid=item.state==="ok";
   const state=valid?raw.state:"unknown";
   const row=add(card,"div",null,"dh1-row");
   add(row,"span",role==="backhaul"?"Backhaul":"Mieru","dh1-role");
   add(row,"span",valid&&raw.ip?raw.ip:"—","dh1-ip");
   add(row,"span",label(state),"dh1-pill "+(state==="healthy"?"ok":state==="down"?"down":""));
   const latency=valid&&Number.isFinite(raw.https_avg_ms)?raw.https_avg_ms+" ms":"—";
   add(card,"div",role+" · میانگین HTTPS: "+latency,"dh1-meta");
  }
  const age=Number.isFinite(item.age_s)?Math.floor(item.age_s/60):null;
  const note=item.state==="not_configured"?"تنظیم نشده":
    item.state==="stale"?"اطلاعات قدیمی":
    item.state==="unavailable"?"اتصال به سرور ناموفق":
    item.state==="ok"&&age!=null?"آخرین بررسی: "+age+" دقیقه پیش":"در انتظار دریافت";
  add(card,"div",note,"dh1-meta");
 }
}
async function refresh(){
 try{
  const response=await fetch("/control-room/dual-hourly/status",{
   credentials:"same-origin",cache:"no-store",
   headers:{"X-Control-CSRF":csrf}
  });
  if(!response.ok)throw Error("unavailable");
  const doc=await response.json();
  if(!doc.ok)throw Error("invalid");
  render(doc.servers);
 }catch(_){render(null);}
}
render(null);refresh();
setInterval(refresh,60000);
})();
</script>
'''
_DH1_TEMPLATE = TEMPLATES.get("control_room.html", "")
_ANCHOR = '<div id="c2-cards" class="c2-cards"></div>'
if _DH1_TEMPLATE.count(_ANCHOR) != 1 or "t10-compact-css" not in _DH1_TEMPLATE:
    raise RuntimeError("Requires currently reviewed V10 Control Room")
if "dh1-root" in _DH1_TEMPLATE:
    raise RuntimeError("Dual hourly UI already loaded")
_DH1_TEMPLATE = _DH1_TEMPLATE.replace(_ANCHOR, _ANCHOR + _DH1_HTML, 1)
_DH1_TEMPLATE = _DH1_TEMPLATE.replace("{% endblock %}",
                                      _DH1_JS + "\n{% endblock %}", 1)
_dh1_Jinja().parse(_DH1_TEMPLATE)
TEMPLATES["control_room.html"] = _DH1_TEMPLATE
if hasattr(env.loader, "mapping"):
    env.loader.mapping.update(TEMPLATES)
