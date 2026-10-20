# HESAB_MAYA_EXTRA_DASHBOARD_V1
# Additional read-only snapshots displayed below existing Maya1 monitoring.
# No X-UI control endpoints and no modification to Maya1 approval mapping.
from pathlib import Path as _mx_Path
from datetime import datetime as _mx_datetime,timezone as _mx_timezone,timedelta as _mx_timedelta
from zoneinfo import ZoneInfo as _mx_ZoneInfo
import json as _mx_json

_MX_PATH=_mx_Path("/srv/maya-extra-sync")
_MX_TEHRAN=_mx_ZoneInfo("Asia/Tehran")
_MX_NAMES={"maya-s3":"مایا S3","maya4":"مایا ۴"}

def _mx_report():
    report=[]
    now=_mx_datetime.now(_mx_timezone.utc)
    for key,title in _MX_NAMES.items():
        summary={"key":key,"title":title,"available":False,"stale":True,
                 "synced":"—","total":0,"linked":0,"unmatched":0,"enabled":0,"users":[]}
        try:
            path=_MX_PATH/(key+".json")
            if not path.is_file() or path.stat().st_size>3000000:
                raise ValueError("Snapshot missing")
            data=_mx_json.loads(path.read_text(encoding="utf8"))
            if data.get("format")!="HESAB_MAYA_EXTRA_V1" or data.get("server")!=key:
                raise ValueError("Format mismatch")
            users=data["clients"]
            if not isinstance(users,list) or len(users)>5000:
                raise ValueError("Invalid roster")
            stamp=_mx_datetime.fromisoformat(data["synced_at"].replace("Z","+00:00"))
            if not stamp.tzinfo:raise ValueError("Missing timezone")
            summary.update({"available":True,
                "stale":now-stamp>_mx_timedelta(minutes=15),
                "synced":stamp.astimezone(_MX_TEHRAN).strftime("%Y-%m-%d %H:%M"),
                "total":len(users),"linked":sum(bool(c.get("sid")) for c in users),
                "unmatched":sum(not c.get("sid") for c in users),
                "enabled":sum(bool(c.get("enabled")) for c in users)})
            for c in users:
                if not isinstance(c,dict):continue
                text=str(c.get("email") or "")[:150]
                if not text:continue
                def integer(x):
                    try:return int(x or 0)
                    except (ValueError,TypeError):return 0
                used=integer(c.get("up_bytes"))+integer(c.get("down_bytes"))
                summary["users"].append({
                  "email":text,"sid":c.get("sid"),"name":str(c.get("name") or "")[:150],
                  "enabled":bool(c.get("enabled")),"usage":f"{used/1073741824:,.2f} GB",
                  "state":str(c.get("dashboard_state") or "")[:35],
                  "search":(text+" "+str(c.get("name") or "")+" "+str(c.get("sid") or "")).casefold()
                })
        except (OSError,ValueError,KeyError,TypeError):
            pass
        report.append(summary)
    return report

env.globals["maya_extra_reports"]=_mx_report

_MX_TEMPLATE=r'''
<section class="mx-dashboard" dir="rtl">
<style>
.mx-dashboard{margin:28px 0;border-top:1px solid #385173;padding-top:18px;color:#e6f2ff}
.mx-dashboard h2{font-size:20px;margin:0 0 8px}
.mx-dashboard p{font-size:12px;color:#a9bcd2;line-height:2}
.mx-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.mx-card{border:1px solid #304963;border-radius:16px;padding:17px;background:#111f30;min-width:0}
.mx-card h3{font-size:17px;margin:0 0 11px}
.mx-alert{padding:12px;border:1px solid #99643f;background:#3d3025;color:#fbd2ac;border-radius:10px;margin:10px 0}
.mx-stats{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:15px}
.mx-stats span{font-size:12px;background:#1b3043;border-radius:9px;padding:6px 9px}
.mx-search{width:100%;box-sizing:border-box;background:#091a2a;border:1px solid #496581;
 padding:10px;border-radius:10px;color:#f4faff;font:inherit}
.mx-table-wrap{overflow:auto;max-height:480px}
.mx-table{width:100%;border-collapse:collapse;min-width:490px}
.mx-table td,.mx-table th{text-align:right;font-size:11px;border-bottom:1px solid #2b4057;padding:10px 6px}
.mx-table th{color:#a4bfdb}
.mx-table a{color:#b8daff;text-decoration:none}
.mx-off{color:#ffacaa}.mx-on{color:#a4e8bc}
@media(max-width:880px){.mx-grid{grid-template-columns:1fr}}
</style>
<h2>سرورهای جدید مایا · اتصال فقط‌خواندنی</h2>
<p>هر سرور مستقل سینک می‌شود. وضعیت قدیمی تأیید وضعیت فعلی نیست؛ کاربران نامنطبق بدون تأیید دستی به اکانت مالی متصل نمی‌شوند.</p>
<div class="mx-grid">
{% for server in maya_extra_reports() %}
<article class="mx-card" data-mx-card>
 <h3>{{ server.title }}</h3>
 {% if not server.available %}
 <div class="mx-alert">اتصال برقرار نشده یا هنوز گزارش معتبری از این سرور دریافت نشده است.</div>
 {% else %}
 {% if server.stale %}<div class="mx-alert">اطلاعات قدیمی است؛ وضعیت فعلی تأیید نشده.</div>{% endif %}
 <div class="mx-stats">
  <span>کل {{ server.total|fa }}</span><span>متصل به داشبورد {{ server.linked|fa }}</span>
  <span>نیازمند تطبیق {{ server.unmatched|fa }}</span><span>فعال {{ server.enabled|fa }}</span>
 </div>
 <p>آخرین گزارش: {{ server.synced }}</p>
 <input type="search" class="mx-search" placeholder="جست‌وجوی نام X-UI یا کاربر داشبورد" data-mx-search>
 <div class="mx-table-wrap">
 <table class="mx-table"><thead><tr><th>کاربر X-UI</th><th>اتصال به داشبورد</th><th>وضعیت</th><th>ترافیک ثبت‌شده</th></tr></thead><tbody>
 {% for c in server.users %}
 <tr data-mx-row data-search="{{ c.search|e }}">
 <td>{{ c.email }}</td>
 <td>{% if c.sid %}<a href="/users/{{ c.sid }}">{{ c.name }} · #{{ c.sid }}</a>
 {% else %}<span class="mx-off">نامنطبق؛ نیازمند تأیید</span>{% endif %}</td>
 <td><span class="{{ 'mx-on' if c.enabled else 'mx-off' }}">{{ 'فعال' if c.enabled else 'غیرفعال' }}</span></td>
 <td dir="ltr">{{ c.usage }}</td>
 </tr>{% else %}<tr><td colspan="4">کلاینتی ثبت نشده.</td></tr>{% endfor %}
 </tbody></table></div>
 {% endif %}
</article>
{% endfor %}
</div>
<script>
(function(){
 for(const card of document.querySelectorAll("[data-mx-card]")){
   const input=card.querySelector("[data-mx-search]");if(!input)continue;
   input.addEventListener("input",()=>{
      const q=input.value.trim().toLowerCase();
      for(const row of card.querySelectorAll("[data-mx-row]")){
        row.hidden=!row.dataset.search.includes(q);
      }
   });
 }
})();
</script>
</section>
'''
_mx_tpl=TEMPLATES.get("control_room.html","")
if not _mx_tpl or "{% endblock %}" not in _mx_tpl:
    raise RuntimeError("Maya extra dashboard: control-room view unavailable")
end=_mx_tpl.rfind("{% endblock %}")
_mx_tpl=_mx_tpl[:end]+_MX_TEMPLATE+_mx_tpl[end:]
TEMPLATES["control_room.html"]=_mx_tpl
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)
