#!/usr/bin/env python3
"""HESAB_PHASE1_IRAN_METRICS_COLLECTOR_V1.
Root-host, optional SSH sensor with strict host key checks. NO billing/XUI writes.
No automatic claim that interface counters equal hosting-provider quota.
"""
import ipaddress,json,os,re,subprocess,sys,tempfile,time
from pathlib import Path

ROOT=Path("/opt/vpn-control-center")
CONFIG=Path("/root/.config/hesab-phase1.json")
SENSOR=ROOT/"scripts/phase1_iran_remote_sensor_v1.py"
OUT=ROOT/"maya_extra_sync/phase1/status.json"
STATE=Path("/var/lib/hesab-phase1/traffic-state.json")
SERVERS=("maya1","maya-s3","maya4")

def atomic(path,obj,mode=0o600):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o750)
    fd,name=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(obj,f,ensure_ascii=False,separators=(",",":"))
            f.flush();os.fsync(f.fileno())
        os.chmod(name,mode)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def protected(path):
    if not path.is_file():raise ValueError("missing protected configuration")
    if path.stat().st_mode & 0o077:raise ValueError("configuration must be chmod 600")
    data=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data,dict):raise ValueError("configuration format")
    return data

def sensor(name,item):
    host=str(item["host"])
    ipaddress.ip_address(host)
    port=int(item.get("ssh_port",22))
    user=str(item.get("ssh_user","root"))
    interface=str(item["interface"])
    identity=Path(str(item["ssh_identity"]))
    if not 1<=port<=65535:raise ValueError("invalid ssh port")
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}",user):raise ValueError("invalid SSH user")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,25}",interface) or interface=="lo":
        raise ValueError("invalid interface")
    if identity.parent!=Path("/root/.ssh") or not identity.is_file():
        raise ValueError("dedicated SSH identity missing")
    if identity.stat().st_mode&0o077:raise ValueError("SSH identity must be private")
    if not SENSOR.is_file():raise ValueError("sensor source missing")
    cmd=["ssh","-F","/dev/null","-i",str(identity),"-p",str(port),
         "-o","IdentitiesOnly=yes","-o","BatchMode=yes",
         "-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6",
         "-o","ConnectionAttempts=1","-o","ControlMaster=no",
         "-o","ForwardAgent=no","-o","ClearAllForwardings=yes",
         f"{user}@{host}",f"python3 -I - {interface}"]
    result=subprocess.run(cmd,input=SENSOR.read_text(encoding="utf-8"),
                          capture_output=True,text=True,timeout=22,check=False)
    if result.returncode:raise RuntimeError("SSH sensor failed (check key, host fingerprint and NIC)")
    if len(result.stdout)>8192:raise ValueError("sensor output too large")
    response=json.loads(result.stdout)
    if response.get("format")!="HESAB_PHASE1_IRAN_SENSOR_V1":
        raise ValueError("sensor format error")
    if response.get("interface")!=interface:raise ValueError("sensor interface mismatch")
    for k in ("cpu_pct","ram_pct","rx_bytes","tx_bytes","observed_at"):
        if not isinstance(response.get(k),(int,float)) or response[k]<0:raise ValueError("invalid sensor reading")
    if not 0<=time.time()-response["observed_at"]<=120:raise ValueError("stale server clock")
    if not re.fullmatch(r"[0-9a-f-]{36}",str(response.get("boot_id",""))):
        raise ValueError("boot-id invalid")
    return response

def calculate(item,now,reading,previous):
    output={"role":"iran","state":"ok","cpu_pct":reading["cpu_pct"],
            "ram_pct":reading["ram_pct"],"traffic_source":"interface_estimate",
            "traffic_state":"not_configured","probe_state":"not_configured"}
    total=int(reading["rx_bytes"])+int(reading["tx_bytes"])
    boot=reading["boot_id"]
    keep={"boot_id":boot,"counter":total,"measured_at":now,
          "accumulated_bytes":0,"basis":None,"rebooted":False}
    quota=item.get("quota_gb");used=item.get("used_at_start_gb")
    try:
        quota=float(quota);used=float(used)
        if not 0<quota<=1e7 or not 0<=used<=quota:raise ValueError("budget mismatch")
    except (TypeError,ValueError):
        return output,keep
    # Operator-provided budget parameters define the counter baseline.
    # Changing quota or initial-used requires a NEW deliberate start of billing period;
    # never silently reuse old tracked bytes under different parameters.
    basis=f"{quota:.6f}|{used:.6f}|{item['host']}|{item['interface']}"
    keep["basis"]=basis
    old=(previous or {})
    if old.get("basis")==basis:
        keep["accumulated_bytes"]=max(0,int(old.get("accumulated_bytes",0)))
        if old.get("boot_id")!=boot or total<int(old.get("counter",0)):
            keep["rebooted"]=True
        elif old.get("rebooted") is True:
            keep["rebooted"]=True
        else:
            keep["accumulated_bytes"]+=total-int(old["counter"])
    # When counters reset, the unobserved bytes cannot be reconstructed safely.
    consumed=used+keep["accumulated_bytes"]/1e9
    output.update({"traffic_quota_gb":quota,"traffic_used_gb":round(consumed,3),
                   "remaining_gb":round(max(0,quota-consumed),3),
                   "traffic_state":"uncertain_reset" if keep["rebooted"] else "estimated"})
    # This value is only an interface estimate until provider counters are compared.
    return output,keep

def run():
    if os.geteuid()!=0:raise PermissionError("run as root")
    cfg=protected(CONFIG)
    opts=cfg.get("servers") or {}
    if not isinstance(opts,dict):raise ValueError("invalid servers")
    if not set(opts).issubset(SERVERS):raise ValueError("unexpected server name")
    state=protected(STATE) if STATE.exists() else {}
    if not isinstance(state,dict):raise ValueError("corrupted usage state")
    result={}
    now=int(time.time())
    updated=dict(state)
    for name in SERVERS:
        item=opts.get(name,{})
        if not item or item.get("role")!="iran":
            result[name]={"role":item.get("role","unknown") if isinstance(item,dict) else "unknown",
                          "state":"not_configured","probe_state":"not_configured"}
            continue
        try:
            data=sensor(name,item)
            summary,updated[name]=calculate(item,now,data,state.get(name))
            result[name]=summary
            print("SENSOR_OK",name,"CPU",summary["cpu_pct"],"RAM",summary["ram_pct"],
                  "quota_state",summary["traffic_state"])
        except Exception as e:
            result[name]={"role":"iran","state":"unavailable",
                          "traffic_state":"unavailable","probe_state":"not_configured"}
            print("SENSOR_FAIL",name,type(e).__name__,file=sys.stderr)
    atomic(STATE,updated,0o600)
    atomic(OUT,{"format":"HESAB_PHASE1_V1","collected_at":now,"servers":result},0o640)
    print("PHASE1_STATUS_UPDATED",str(OUT),"METRICS_ONLY; NO PHONE PUSH")

if __name__=="__main__":
    try:run()
    except Exception as e:
        print("PHASE1_COLLECTOR_STOP",type(e).__name__,str(e)[:100],file=sys.stderr)
        sys.exit(1)
