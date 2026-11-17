# HESAB_MAYA_XUI_USER_DAILY_UI_V11
# Replace only today's *display* source from host NIC RX with XUI client
# cumulative up+down deltas. Keep NIC quota/remaining and all other routes
# untouched. Read-only XUI daily JSON is mounted under /srv/maya-live.
import json as _ux11_json
import time as _ux11_time
from datetime import datetime as _ux11_datetime
from pathlib import Path as _ux11_Path
from zoneinfo import ZoneInfo as _ux11_ZoneInfo
from fastapi import Request as _ux11_Request
from fastapi.responses import JSONResponse as _ux11_JSON
from jinja2 import Environment as _ux11_Jinja

_UX11_PATH=_ux11_Path("/srv/maya-live/phase1/maya_user_daily_v11.json")
_UX11_NAMES=("maya1","maya-s3","maya4")
_UX11_FORMAT="HESAB_MAYA_XUI_USER_DAILY_V11"
_UX11_TZ=_ux11_ZoneInfo("Asia/Tehran")

def _ux11_daily(request:_ux11_Request):
    if not _dh1_auth(request):
        return _ux11_JSON({"ok":False},status_code=403)
    output={name:{"state":"not_measured"} for name in _UX11_NAMES}
    try:
        if (_UX11_PATH.is_symlink() or not _UX11_PATH.is_file()
            or not 0<_UX11_PATH.stat().st_size<=20000):
            raise OSError("no XUI daily file")
        doc=_ux11_json.loads(_UX11_PATH.read_text(encoding="utf8"))
        today=_ux11_datetime.now(_UX11_TZ).date().isoformat()
        at=doc.get("collected_at")
        if doc.get("format")!=_UX11_FORMAT or type(at) is not int:
            raise ValueError("daily JSON format")
        if not -60<=_ux11_time.time()-at<=300 or doc.get("day")!=today:
            output={name:{"state":"stale"} for name in _UX11_NAMES}
        else:
            servers=doc.get("servers")
            if not isinstance(servers,dict):raise ValueError("missing servers")
            for name in _UX11_NAMES:
                item=servers.get(name,{})
                if not isinstance(item,dict):continue
                state=item.get("state")
                if state in ("not_measured","unavailable","stale"):
                    output[name]={"state":state}
                    continue
                value=item.get("total_bytes")
                last=item.get("last_sample_at")
                if (state not in ("partial","measured")
                    or type(value) is not int or not 0<=value<=2**63-1
                    or type(last) is not int
                    or not -30<=_ux11_time.time()-last<=360):
                    output[name]={"state":"stale"}
                    continue
                # Decimal GB; source is XUI per-client UP+DOWN, not Iran NIC RX.
                output[name]={"state":state,"usage_gb":round(value/1000000000,4),
                              "partial":state=="partial",
                              "last_sample_at":last,"source":"xui_clients_up_down"}
    except (OSError,ValueError,TypeError,KeyError,OverflowError,UnicodeError):
        output={name:{"state":"unavailable"} for name in _UX11_NAMES}
    return _ux11_JSON({"ok":True,"servers":output},
                      headers={"Cache-Control":"private,no-store"})

if any(getattr(route,"path",None)=="/control-room/v11/users-daily"
       for route in app.router.routes):
    raise RuntimeError("Daily XUI V11 route already installed")
app.add_api_route("/control-room/v11/users-daily",_ux11_daily,methods=["GET"])

_UX11_TEMPLATE=TEMPLATES.get("control_room.html","")
_UX11_SUBSTITUTIONS=(
  ('fetch("/control-room/v10/daily",\n    {credentials:"same-origin",cache:"no-store"});',
   'fetch("/control-room/v11/users-daily",\n    {credentials:"same-origin",cache:"no-store",'
   'headers:{"X-Control-CSRF":t10CSRF}});'),
  ('const today=day.state==="ok"?t10FormatGB(day.rx_today_gb):"—";',
   'const today=day.state==="measured"?t10FormatGB(day.usage_gb):'
   'day.state==="partial"?"≥ "+t10FormatGB(day.usage_gb):"—";'),
  ('c4CardLabel("ترافیک روز",today,values);',
   'c4CardLabel("مصرف کاربران امروز",today,values);'),
  ('if(day.partial_day===true){',
   'if(day.partial===true){'),
  ('values.lastElementChild.title="مصرف RX فقط از شروع ثبت در امروز است؛ کل روز نیست.";',
   'values.lastElementChild.title="حداقل مصرف ثبت‌شده کاربران از نمونه‌های 3x-ui؛'
   ' بازه شروع روز یا برخی بازه‌ها قابل بازسازی دقیق نیستند.";'),
  ('values.lastElementChild.title="مصرف RX کارت شبکه در روز تهران";',
   'values.lastElementChild.title="جمع تغییر شمارنده‌های UP و DOWN کاربران 3x-ui'
   ' در روز جاری به وقت تهران؛ نه مصرف کارت شبکه سرور.";'),
)
if "t10-compact-css" not in _UX11_TEMPLATE:
    raise RuntimeError("Maya V10 card source missing")
if "maya-user-traffic-v11-ui" in _UX11_TEMPLATE:
    raise RuntimeError("Maya V11 already present")
for before,after in _UX11_SUBSTITUTIONS:
    if _UX11_TEMPLATE.count(before)!=1:
        raise RuntimeError("Cannot safely replace daily display source: "+before[:65])
    _UX11_TEMPLATE=_UX11_TEMPLATE.replace(before,after,1)
# The old source remains available for provider/NIC diagnostics but is no
# longer used for the visible daily customer traffic card.
_UX11_TEMPLATE=_UX11_TEMPLATE.replace(
    '<style id="t10-compact-css">',
    '<!-- maya-user-traffic-v11-ui -->\n<style id="t10-compact-css">',1)
if "{#" in _UX11_TEMPLATE:raise RuntimeError("Jinja token in daily UI")
_ux11_Jinja().parse(_UX11_TEMPLATE)
TEMPLATES["control_room.html"]=_UX11_TEMPLATE
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)
