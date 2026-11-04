# HESAB_DUAL_HOURLY_MANUAL_REFRESH_V2
# Extra admin-only POST to request a new host-side cached 'dual status' pull.
# Uses a local Unix socket (no new public TCP route or host SSH credentials in app).
import json as _dm2_json
import socket as _dm2_socket
from pathlib import Path as _dm2_Path
from fastapi import Request as _dm2_Request
from fastapi.responses import JSONResponse as _dm2_JSON
from jinja2 import Environment as _dm2_Jinja

_DM2_SOCKET="/srv/maya-live/dual_refresh_v2.sock"
_DM2_SNAPSHOT=_dm2_Path("/srv/maya-live/dual_hourly_v1.json")
_DM2_ORIGIN="https://hesab.filmjadiid.ir"

def _dm2_meta(request:_dm2_Request):
    if not _dh1_auth(request):
        return _dm2_JSON({"ok":False},status_code=403)
    stamp=0
    try:
        if _DM2_SNAPSHOT.is_file() and 0 < _DM2_SNAPSHOT.stat().st_size <=16000:
            stamp=int(_DM2_SNAPSHOT.stat().st_mtime*1000)
    except OSError:
        pass
    return _dm2_JSON({"ok":True,"snapshot_mtime_ms":stamp},
                     headers={"Cache-Control":"private, no-store"})

def _dm2_trigger(request:_dm2_Request):
    if (not _dh1_auth(request) or request.headers.get("origin")!=_DM2_ORIGIN
        or request.headers.get("sec-fetch-site") not in (None,"same-origin")):
        return _dm2_JSON({"ok":False,"error":"Forbidden"},status_code=403)
    try:
        with _dm2_socket.socket(_dm2_socket.AF_UNIX,_dm2_socket.SOCK_STREAM) as sock:
            sock.settimeout(5)
            sock.connect(_DM2_SOCKET)
            sock.sendall(b'{"op":"refresh"}\n')
            sock.shutdown(_dm2_socket.SHUT_WR)
            payload=b""
            while len(payload)<2048 and not payload.endswith(b"\n"):
                part=sock.recv(2048-len(payload))
                if not part:break
                payload+=part
        if not payload.endswith(b"\n"):
            raise ValueError("Incomplete local broker response")
        result=_dm2_json.loads(payload)
        if result.get("ok") is not True:
            return _dm2_JSON({"ok":False,"error":"Wait before another refresh"},status_code=429)
        if result.get("accepted") is not True:
            raise ValueError("Unexpected broker reply")
        previous=result.get("before")
        if type(previous) is not int or previous < 0:
            raise ValueError("Unexpected snapshot version")
        return _dm2_JSON({"ok":True,"accepted":True,
                          "already_running":result.get("already_running") is True,
                          "previous_snapshot_mtime_ms":previous},
                         status_code=202,headers={"Cache-Control":"private, no-store"})
    except (OSError,ValueError,TypeError,_dm2_socket.timeout):
        return _dm2_JSON({"ok":False,"error":"Refresh worker unavailable"},
                         status_code=503)

for _dm2_path in ("/control-room/dual-hourly/refresh",
                  "/control-room/dual-hourly/refresh-meta"):
    if any(getattr(r,"path",None)==_dm2_path for r in app.router.routes):
        raise RuntimeError("Manual Dual refresh route already installed")
app.add_api_route("/control-room/dual-hourly/refresh",_dm2_trigger,methods=["POST"])
app.add_api_route("/control-room/dual-hourly/refresh-meta",_dm2_meta,methods=["GET"])

_DM2_BUTTON=r'''
<span class="dm2-controls">
  <button id="dm2-refresh" type="button">بروزرسانی لحظه‌ای</button>
  <small id="dm2-feedback" aria-live="polite"></small>
</span>
'''
_DM2_STYLE=r'''
<style id="dm2-style">
#c2-root .dm2-controls{display:inline-flex;align-items:center;gap:9px;flex-wrap:wrap}
#c2-root #dm2-refresh{background:#30275c;border:1px solid #8b7bea;
 border-radius:9px;color:#f5f2ff;padding:8px 13px;font:inherit;font-weight:800;
 font-size:11px;cursor:pointer}
#c2-root #dm2-refresh:disabled{cursor:wait;opacity:.65}
#c2-root #dm2-feedback{font-size:11px;color:#bdc9dd}
</style>
'''
_DM2_SCRIPT=r'''
<script id="dm2-script">
(function(){
"use strict";
const button=document.getElementById("dm2-refresh");
const feedback=document.getElementById("dm2-feedback");
if(!button||!feedback)return;
const token="{{ ctrl_csrf }}";
let busy=false;
const options={credentials:"same-origin",cache:"no-store",
 headers:{"X-Control-CSRF":token}};
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
button.addEventListener("click",async()=>{
 if(busy)return;
 busy=true;button.disabled=true;
 button.textContent="در حال بررسی...";
 feedback.textContent="در حال خواندن وضعیت واقعی از سه Maya";
 try{
  const r=await fetch("/control-room/dual-hourly/refresh",{
    ...options,method:"POST"
  });
  const response=await r.json();
  if(!r.ok||!response.ok||!response.accepted)
    throw Error(r.status===429?"چند لحظه دیگر دوباره امتحان کن":"شروع بررسی ناموفق بود");
  const previous=response.previous_snapshot_mtime_ms;
  let updated=false;
  for(let i=0;i<40;i++){
    await sleep(2000);
    const metaResponse=await fetch("/control-room/dual-hourly/refresh-meta",options);
    if(!metaResponse.ok)throw Error("دریافت زمان گزارش ناموفق بود");
    const meta=await metaResponse.json();
    if(meta.ok&&meta.snapshot_mtime_ms>previous){
      updated=true;break;
    }
  }
  if(!updated)throw Error("گزارش جدید دریافت نشد؛ وضعیت سرویس را بررسی کن");
  if(typeof window.__HESAB_DUAL_REFRESH_NOW==="function"){
    await window.__HESAB_DUAL_REFRESH_NOW();
  }
  feedback.textContent="گزارش تازه دریافت شد · "+new Date().toLocaleTimeString("fa-IR");
 }catch(err){
  feedback.textContent=err.message||"بروزرسانی ناموفق بود";
 }finally{
  busy=false;button.disabled=false;button.textContent="بروزرسانی لحظه‌ای";
 }
});
})();
</script>
'''

_DM2_TEMPLATE=TEMPLATES.get("control_room.html","")
_DM2_HEADING='<span class="dh1-note">بررسی خودکار هر ساعت · زمان پاسخ HTTPS، نه پینگ ICMP</span>'
_DM2_READY="render(null);refresh();\nsetInterval(refresh,60000);"
_DM2_SCRIPT_OPEN='<script id="dh1-script">'
if (_DM2_TEMPLATE.count(_DM2_HEADING)!=1 or _DM2_TEMPLATE.count(_DM2_READY)!=1
    or _DM2_TEMPLATE.count(_DM2_SCRIPT_OPEN)!=1 or "t10-compact-css" not in _DM2_TEMPLATE):
    raise RuntimeError("Manual refresh requires the deployed V1 Dual cards")
if "dm2-refresh" in _DM2_TEMPLATE:
    raise RuntimeError("Manual refresh already present")
_DM2_TEMPLATE=_DM2_TEMPLATE.replace(_DM2_HEADING,
                                    _DM2_HEADING+_DM2_BUTTON,1)
_DM2_TEMPLATE=_DM2_TEMPLATE.replace(_DM2_READY,
                                    "window.__HESAB_DUAL_REFRESH_NOW=refresh;\n"+_DM2_READY,1)
_dm2_at=_DM2_TEMPLATE.index(_DM2_SCRIPT_OPEN)
_dm2_end=_DM2_TEMPLATE.index("</script>",_dm2_at)+len("</script>")
_DM2_TEMPLATE=(_DM2_TEMPLATE[:_dm2_end]+_DM2_STYLE+_DM2_SCRIPT+
              _DM2_TEMPLATE[_dm2_end:])
if "{#" in _DM2_TEMPLATE:
    raise RuntimeError("Unexpected Jinja comment token")
_dm2_Jinja().parse(_DM2_TEMPLATE)
TEMPLATES["control_room.html"]=_DM2_TEMPLATE
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)
