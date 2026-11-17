#!/usr/bin/env bash
# MAYA_NIC_TRAFFIC_V11_READONLY_DIAG
# Run only on VPN management host. No writes, service restarts or SSH trust changes.
set -u
cd /opt/vpn-control-center || exit 2
printf '%s\n' '=== METER AND HISTORY SCHEDULES ==='
for unit in hesab-maya-net-meter-v2.timer hesab-maya-daily-v10.timer \
            hesab-maya-traffic-history-v11.timer; do
 printf '%s: ' "$unit"
 systemctl is-active "$unit" 2>/dev/null || true
done
printf '%s\n' '=== VERIFIED METER CONFIG AND LATEST SNAPSHOTS (NO KEYS SHOWN) ==='
python3 - <<'PY'
import json,time
from pathlib import Path
expected={"maya1":"94.184.4.38","maya-s3":"185.215.230.221",
          "maya4":"5.10.249.206"}
paths={
 "settings":Path("/root/.config/hesab-maya-net-meter-v2.json"),
 "status":Path("/opt/vpn-control-center/maya_extra_sync/phase1/status.json"),
 "state":Path("/var/lib/hesab-maya-net-meter-v2/state.json"),
 "history":Path("/opt/vpn-control-center/maya_extra_sync/phase1/traffic_history_v11.json"),
}
docs={}
for k,p in paths.items():
 try:docs[k]=json.loads(p.read_text())
 except Exception as e:print("FILE",k,"MISSING_OR_UNREADABLE",type(e).__name__)
config=docs.get("settings",{}).get("servers",{})
status=docs.get("status",{})
raw=docs.get("state",{})
history=docs.get("history",{})
print("METER_STATUS_AGE_SECONDS",round(time.time()-status.get("collected_at",0)) if status else "—")
print("TRAFFIC_HISTORY_AGE_SECONDS",round(time.time()-history.get("generated_at",0)) if history else "—")
for name in ("maya1","maya-s3","maya4"):
 c=config.get(name,{})
 s=status.get("servers",{}).get(name,{})
 r=raw.get(name,{})
 h=history.get("servers",{}).get(name,{})
 print(name,
       "nic_configured",bool(c),
       "mapped_host",c.get("host","—"),
       "expected_host",expected[name],
       "host_matches_reference",c.get("host")==expected[name],
       "interface",c.get("interface","—"),
       "status",s.get("state","—"),
       "quota_state",s.get("traffic_state","—"),
       "reset_uncertain",s.get("counter_uncertain","—"),
       "sample_age_sec",round(time.time()-r["sample_at"]) if isinstance(r.get("sample_at"),int) else "—",
       "history_state",h.get("state","—"),
       "rx_today_gb",h.get("rx_today_gb","—"))
PY
printf '%s\n' '=== RESTRICTED SENSOR SSH READ (NO SSH CONFIG CHANGES) ==='
for name in maya1 maya-s3 maya4;do
 echo "--- $name ---"
 if timeout 26 python3 scripts/maya_net_meter_manage_v2.py verify "$name";then
  echo "SENSOR_CHECK=PASS"
 else
  echo "SENSOR_CHECK=FAILED"
 fi
done
printf '%s\n' '=== RECENT NIC METER FAILURES ==='
journalctl -u hesab-maya-net-meter-v2.service --no-pager -n 35 2>/dev/null |
 grep -E 'METER_(OK|FAILED|COLLECTOR_STOP|DASHBOARD_UPDATED)|restricted SSH|Server' |
 tail -n 22 || true
echo "DIAGNOSTIC_COMPLETE=READ_ONLY"
