#!/usr/bin/env bash
# HESAB_V11_IRAN_TUNNEL_AUDIT_V1 — read-only, no secrets.
# Usage on EACH Iran VPS: sudo bash audit_iran_tunnel_readonly.sh maya1|maya-s3|maya4
set -Eeuo pipefail
[[ $# -eq 1 ]] || { echo 'Usage: sudo bash audit_iran_tunnel_readonly.sh maya1|maya-s3|maya4';exit 2; }
case "$1" in maya1|maya-s3|maya4) ;; *) echo 'Unknown server ID';exit 2;; esac
echo "=== HESAB V11 IRAN TUNNEL HOST SURVEY ==="
echo "SERVER_ID=$1"
printf 'UTC=';date -u '+%Y-%m-%dT%H:%M:%SZ'
python3 - <<'PY'
import csv,datetime,io,json,os,subprocess,socket,time
from pathlib import Path
services=["x-ui","dual-ha-v2-gateway","dual-ha-v2-health","dual-ha-v2-router",
"dual-ha-backhaul","dual-ha-mieru","dual-ha-router","dual-ha-tls",
"naive","naiveproxy","mieru","sing-box","mihomo","haproxy","stunnel4"]
def state(unit):
 try:
  p=subprocess.run(["systemctl","is-active",unit],capture_output=True,text=True,timeout=3)
  return p.stdout.strip() if p.stdout.strip() in ("active","inactive","failed","activating") else "unknown"
 except (OSError,subprocess.TimeoutExpired):return "unknown"
print("SERVICES")
for name in services:
 print(name,state(name))
health=Path("/run/dual-ha-v2/health.json")
sock=Path("/run/dual-ha-v2/haproxy.sock")
print("DUAL_HA_V2_HEALTH_PRESENT",health.is_file())
print("DUAL_HA_V2_STATS_SOCKET_PRESENT",sock.is_socket())
try:
 if health.stat().st_size<=16384:
  obj=json.loads(health.read_text())
  ts=datetime.datetime.fromisoformat(obj["updated_utc"].replace("Z","+00:00"))
  age=(datetime.datetime.now(datetime.timezone.utc)-ts).total_seconds()
  print("DUAL_HA_HEALTH_AGE_S",round(age,1))
  if isinstance(obj.get("paths"),dict):
   for lane in ("backhaul","mieru"):
    a=obj["paths"].get(lane)
    if isinstance(a,dict):
     print("DUAL_PATH",lane,"available",a.get("available"),
          "probes",a.get("passed_probes"),"/",a.get("total_probes"),
          "latency_s",a.get("latency_average_s"),
          "consecutive_fail",a.get("consecutive_fail"))
except (OSError,ValueError,KeyError,TypeError):
 print("DUAL_HA_HEALTH_READABLE",False)
if sock.is_socket():
 try:
  with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
   s.settimeout(2)
   s.connect(str(sock))
   s.sendall(b"show stat\n")
   s.shutdown(socket.SHUT_WR)
   data=b""
   while len(data)<1048576:
    x=s.recv(32768)
    if not x:break
    data+=x
  lines=data.decode("utf8","replace").splitlines()
  cols=lines[0].lstrip("# ").split(",")
  for item in csv.DictReader(io.StringIO("\n".join(lines[1:])),fieldnames=cols):
   if item.get("pxname")=="dual_egress" and item.get("svname") in ("backhaul","mieru","BACKEND"):
    print("HA_STATS",item["svname"],"status",item.get("status"),
          "active_connections",item.get("scur"),
          "total_connections",item.get("stot"),
          "bytes_in",item.get("bin"),"bytes_out",item.get("bout"))
 except (OSError,IndexError,ValueError,csv.Error):
  print("HA_STATS_UNAVAILABLE")
try:
 r=subprocess.run(["ss","-H","-lnt"],capture_output=True,text=True,timeout=4)
 if r.returncode==0:
  wanted={"443","18080","18443","2095","21001","21002"}
  opened=set()
  for line in r.stdout.splitlines():
   v=line.split()
   if len(v)>=4:
    last=v[3].rsplit(":",1)[-1]
    if last in wanted:opened.add(last)
  print("LOCAL_LISTENERS_RELEVANT",",".join(sorted(opened)) or "NONE")
except (OSError,subprocess.TimeoutExpired): print("LOCAL_LISTENERS_UNAVAILABLE")
try:
 rows=subprocess.run(["ip","-br","link"],capture_output=True,text=True,timeout=5)
 if rows.returncode==0:
  print("NETWORK_INTERFACES")
  for line in rows.stdout.splitlines():
   pieces=line.split()
   if len(pieces)>=2:print("INTERFACE",pieces[0],"STATE",pieces[1])
except (OSError,subprocess.TimeoutExpired):print("NETWORK_INTERFACES_UNAVAILABLE")
print("CLASSIFICATION",("DUAL_HA_V2_PRESENT" if health.is_file() and sock.is_socket() else "TUNNEL_TYPE_UNVERIFIED"))
PY
echo "END: no service was restarted, no passwords or user data were read."
