# HESAB_CONTROL_ROOM_MANUAL_PATH_TEST_V1
# Add separate "تست مسیر" button for the explicitly initiated real 512KiB downloads.
# No tunnel edits, no cron, no new access to dashboard SSH private keys.
import json as _pt_json
import re as _pt_re
import socket as _pt_socket
from pathlib import Path as _pt_Path
from fastapi import Request as _pt_Request
from fastapi.responses import JSONResponse as _pt_JSON
from jinja2 import Environment as _pt_Jinja

_PT_SOCK="/srv/maya-live/path_transfer_v1.sock"
_PT_STATUS=_pt_Path("/srv/maya-live/path_transfer_v1/status.json")
_PT_ORIGIN="https://hesab.filmjadiid.ir"
_PT_NAMES=("maya1","maya-s3","maya4")
_PT_PATHS=("backhaul","mieru","haproxy")

def _pt_start(request:_pt_Request):
    if (not _dh1_auth(request)
        or request.headers.get("origin")!=_PT_ORIGIN
        or request.headers.get("sec-fetch-site") not in (None,"same-origin")):
        return _pt_JSON({"ok":False,"error":"Forbidden"},status_code=403)
    try:
        with _pt_socket.socket(_pt_socket.AF_UNIX,_pt_socket.SOCK_STREAM) as sock:
            sock.settimeout(5)
            sock.connect(_PT_SOCK)
            sock.sendall(b'{"op":"start"}\n')
            sock.shutdown(_pt_socket.SHUT_WR)
            raw=b""
            while len(raw)<1024 and not raw.endswith(b"\n"):
                chunk=sock.recv(1024-len(raw))
                if not chunk:break
                raw+=chunk
        if not raw.endswith(b"\n"):
            raise ValueError("Incomplete broker response")
        result=_pt_json.loads(raw)
        if result.get("ok") is not True or result.get("accepted") is not True:
            return _pt_JSON({"ok":False,"error":"Test unavailable or cooldown"},
                            status_code=429)
        run_id=result.get("run_id")
        if not isinstance(run_id,str) or not _pt_re.fullmatch(r"[0-9a-f]{24}",run_id):
            raise ValueError("Invalid job token")
        return _pt_JSON({"ok":True,"run_id":run_id},status_code=202,
                        headers={"Cache-Control":"private, no-store"})
    except (OSError,ValueError,TypeError,_pt_socket.timeout):
        return _pt_JSON({"ok":False,"error":"Local test service unavailable"},
                        status_code=503)

def _pt_status(request:_pt_Request):
    if not _dh1_auth(request):
        return _pt_JSON({"ok":False},status_code=403)
    try:
        if (not _PT_STATUS.is_file() or _PT_STATUS.is_symlink()
            or not 0<_PT_STATUS.stat().st_size<=20000):
            raise OSError("No test data")
        doc=_pt_json.loads(_PT_STATUS.read_text(encoding="utf8"))
        run_id=doc.get("run_id")
        state=doc.get("state")
        if (doc.get("format")!="HESAB_PATH_TEST_ACCOUNT_V1"
            or not isinstance(run_id,str)
            or not _pt_re.fullmatch(r"[0-9a-f]{24}",run_id)
            or state not in ("running","completed","failed")):
            raise ValueError("Invalid job data")
        if state=="running":
            return _pt_JSON({"ok":True,"run_id":run_id,"state":"running"},
                          headers={"Cache-Control":"private, no-store"})
        result={}
        items=doc.get("servers")
        if not isinstance(items,dict):
            items={}
        for name in _PT_NAMES:
            server=items.get(name,{})
            paths=server.get("paths",{}) if isinstance(server,dict) else {}
            result[name]={}
            for role in _PT_PATHS:
                value=paths.get(role,{}) if isinstance(paths,dict) else {}
                healthy=(state=="completed" and isinstance(server,dict) and
                         server.get("state")=="completed" and isinstance(value,dict) and
                         value.get("state")=="healthy")
                result[name][role]="healthy" if healthy else "warning"
        overall="healthy" if all(result[name][role]=="healthy"
              for name in _PT_NAMES for role in _PT_PATHS) else "warning"
        return _pt_JSON({"ok":True,"run_id":run_id,"state":state,
                         "summary":overall,"servers":result},
                         headers={"Cache-Control":"private, no-store"})
    except (OSError,ValueError,TypeError,UnicodeError,AttributeError):
        return _pt_JSON({"ok":False,"error":"No verified result"},
                        status_code=503)

for _pt_path in ("/control-room/path-test/start","/control-room/path-test/status"):
    if any(getattr(route,"path",None)==_pt_path for route in app.router.routes):
        raise RuntimeError("Duplicate manual path test route")
app.add_api_route("/control-room/path-test/start",_pt_start,methods=["POST"])
app.add_api_route("/control-room/path-test/status",_pt_status,methods=["GET"])

_PT_BUTTON='<button id="ocs-transfer-check" type="button">تست مسیر</button>'
_PT_PANEL=r'''
<div id="ocs-transfer-box" class="ocs-status" role="status" aria-live="polite" hidden></div>
<div id="ocs-transfer-grid" class="ocs-grid" hidden></div>
'''
_PT_STYLE=r'''
<style id="pt-ui-style">
#c2-root #ocs-transfer-check{
 font:inherit;background:#20274c;border:1px solid #787fbd;
 color:#f3f3ff;padding:10px 14px;font-size:12px;font-weight:800;
 border-radius:10px;cursor:pointer
}
#c2-root #ocs-transfer-check:disabled{opacity:.6;cursor:wait}
#c2-root #ocs-transfer-box[hidden],#c2-root #ocs-transfer-grid[hidden]{display:none!important}
</style>
'''
_PT_SCRIPT=r'''
<script id="pt-ui-script">
(function(){
"use strict";
if(window.__HESAB_MANUAL_PATH_TEST_V1)return;
window.__HESAB_MANUAL_PATH_TEST_V1=true;
const button=document.getElementById("ocs-transfer-check");
const box=document.getElementById("ocs-transfer-box");
const grid=document.getElementById("ocs-transfer-grid");
if(!button||!box||!grid)return;
const csrf="{{ ctrl_csrf }}";
const ids=["maya1","maya-s3","maya4"];
const names={"maya1":"مایا ۱","maya-s3":"مایا ۳","maya4":"مایا ۴"};
const roles=["backhaul","mieru","haproxy"];
const delay=ms=>new Promise(done=>setTimeout(done,ms));
const opts={credentials:"same-origin",cache:"no-store",
 headers:{"X-Control-CSRF":csrf}};
function element(parent,tag,value,cls){
 const node=document.createElement(tag);
 if(cls)node.className=cls;
 if(value!=null)node.textContent=String(value);
 parent.appendChild(node);return node;
}
function message(label,warning){
 box.hidden=false;
 box.textContent=label;
 box.className="ocs-status "+(warning?"warning":"ok");
}
function draw(servers){
 grid.hidden=false;
 grid.replaceChildren();
 let all=true;
 for(const id of ids){
  const card=element(grid,"div",null,"ocs-server");
  element(card,"div",names[id],"ocs-name");
  for(const role of roles){
   const ok=servers?.[id]?.[role]==="healthy";
   if(!ok)all=false;
   const row=element(card,"div",null,"ocs-line");
   element(row,"span",role==="backhaul"?"Backhaul":
                      role==="mieru"?"Mieru":"HAProxy");
   element(row,"span",ok?"سالم":"هشدار","ocs-pill "+(ok?"ok":"warning"));
  }
 }
 message(all?"تست انتقال داده: سالم":"تست انتقال داده: هشدار",!all);
}
button.addEventListener("click",async()=>{
 if(button.disabled)return;
 button.disabled=true;button.textContent="در حال تست...";
 grid.hidden=true;grid.replaceChildren();
 box.hidden=false;box.textContent="در حال آزمایش دانلود ۵۱۲KiB از ۹ مسیر...";
 box.className="ocs-status";
 try{
  const reply=await fetch("/control-room/path-test/start",{...opts,method:"POST"});
  const start=await reply.json();
  if(!reply.ok||!start.ok||!start.run_id){
   throw Error(reply.status===429?"تست آماده نیست یا فاصله تست‌ها رعایت نشده":
     "امکان شروع تست وجود ندارد");
  }
  let done=false;
  for(let i=0;i<65;i++){
   await delay(2000);
   const res=await fetch("/control-room/path-test/status",opts);
   if(!res.ok)throw Error("دریافت نتیجه آزمایش ناموفق بود");
   const data=await res.json();
   if(data.run_id!==start.run_id)continue;
   if(data.state==="running")continue;
   if(data.state==="completed"||data.state==="failed"){
    draw(data.servers||{});done=true;break;
   }
  }
  if(!done)throw Error("مهلت دریافت نتیجه تمام شد");
 }catch(error){
  grid.hidden=true;
  grid.replaceChildren();
  message("تست مسیر: هشدار — "+(error.message||"نتیجه قابل تأیید نیست"),true);
 }finally{
  button.disabled=false;button.textContent="تست مسیر";
 }
});
})();
</script>
'''
_PT_TEMPLATE=TEMPLATES.get("control_room.html","")
_PT_ORIGINAL='<button id="ocs-check" type="button">بررسی وضعیت</button>'
_PT_GRID='<div id="ocs-grid" class="ocs-grid"></div>'
if (_PT_TEMPLATE.count(_PT_ORIGINAL)!=1 or _PT_TEMPLATE.count(_PT_GRID)!=1
    or _PT_TEMPLATE.count('<script id="ocs-js">')!=1
    or "t10-compact-css" not in _PT_TEMPLATE):
    raise RuntimeError("Manual path test requires deployed one-click status UI")
if 'id="ocs-transfer-check"' in _PT_TEMPLATE:
    raise RuntimeError("Manual path test UI already installed")
_PT_TEMPLATE=_PT_TEMPLATE.replace(_PT_ORIGINAL,_PT_ORIGINAL+_PT_BUTTON,1)
_PT_TEMPLATE=_PT_TEMPLATE.replace(_PT_GRID,_PT_GRID+_PT_PANEL,1)
pt_start=_PT_TEMPLATE.index('<script id="ocs-js">')
pt_end=_PT_TEMPLATE.index("</script>",pt_start)+len("</script>")
_PT_TEMPLATE=_PT_TEMPLATE[:pt_end]+_PT_STYLE+_PT_SCRIPT+_PT_TEMPLATE[pt_end:]
if "{#" in _PT_TEMPLATE:
    raise RuntimeError("Unexpected Jinja comment tag")
_pt_Jinja().parse(_PT_TEMPLATE)
TEMPLATES["control_room.html"]=_PT_TEMPLATE
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)
