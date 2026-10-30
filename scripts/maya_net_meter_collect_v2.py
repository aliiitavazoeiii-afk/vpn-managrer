#!/usr/bin/env python3
"""HESAB_MAYA_NET_METER_COLLECTOR_V2
Independent SSH-forced-command NIC RX/TX polling; local persistent quota ledger.
No X-UI calls, firewall changes, billing writes, or inbound web endpoints.
The provider-billed direction MUST be explicitly confirmed before quota display.
"""
import fcntl, ipaddress, json, math, os, re, subprocess, sys, tempfile, time
from pathlib import Path

ROOT=Path("/opt/vpn-control-center")
CONFIG=Path("/root/.config/hesab-maya-net-meter-v2.json")
STATE=Path("/var/lib/hesab-maya-net-meter-v2/state.json")
LOCK=Path("/var/lib/hesab-maya-net-meter-v2/poll.lock")
OUT=ROOT/"maya_extra_sync/phase1/status.json"
NAMES=("maya1","maya-s3","maya4")
VERSION="HESAB_MAYA_NET_SENSOR_V2"
GB=1_000_000_000
WARNING_GB=10.0

def safe_float(v, low, high):
    if type(v) not in (int,float) or not math.isfinite(v):
        raise ValueError("invalid numeric configuration")
    n=float(v)
    if not low<=n<=high:raise ValueError("numeric value outside safe range")
    return n

def load(path,default=None):
    if not path.exists():
        if default is not None:return default
        raise FileNotFoundError("protected meter configuration missing")
    if path.is_symlink() or path.stat().st_mode&0o077:
        raise PermissionError("meter configuration/state must be private (chmod 600)")
    data=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data,dict):raise ValueError("invalid config/state object")
    return data

def atomic(path,value):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,temporary=tempfile.mkstemp(prefix=".meter-",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(value,f,ensure_ascii=False,separators=(",",":"))
            f.write("\n")
            f.flush();os.fsync(f.fileno())
        os.chmod(temporary,0o600 if path==STATE else 0o640)
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)

def validate_connection(name,config):
    ip=str(config["host"])
    addr=ipaddress.ip_address(ip)
    if addr.version!=4 or not addr.is_global:raise ValueError("public host IPv4 required")
    port=int(config.get("ssh_port",22))
    nic=str(config["interface"])
    if not 1<=port<=65535 or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,24}",nic) or nic=="lo":
        raise ValueError("invalid ssh port or NIC")
    key=Path("/root/.ssh")/("hesab_meter_"+name.replace("-","_"))
    if not key.is_file() or key.is_symlink() or key.stat().st_mode&0o077:
        raise PermissionError("dedicated restricted SSH private key missing/insecure")
    return ip,port,nic,str(key)

def poll(name,config):
    ip,port,nic,key=validate_connection(name,config)
    cmd=["ssh","-F","/dev/null","-i",key,"-p",str(port),
         "-o","BatchMode=yes","-o","IdentitiesOnly=yes",
         "-o","StrictHostKeyChecking=yes",
         "-o","UserKnownHostsFile=/root/.ssh/known_hosts",
         "-o","ConnectTimeout=7","-o","ConnectionAttempts=1",
         "-o","ControlMaster=no","-o","ClearAllForwardings=yes",
         "-o","ForwardAgent=no","-T",f"hesab-meter@{ip}","meter"]
    reply=subprocess.run(cmd,capture_output=True,text=True,timeout=19,check=False)
    if reply.returncode:raise RuntimeError("restricted SSH sensor unavailable")
    if len(reply.stdout)>4096:raise ValueError("unexpected large sensor output")
    data=json.loads(reply.stdout)
    if data.get("format")!=VERSION or data.get("iface")!=nic:
        raise ValueError("unexpected sensor format or network interface")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}",str(data.get("boot_id",""))):
        raise ValueError("invalid boot identity")
    for key in ("rx_bytes","tx_bytes","ifindex","uptime_s"):
        if type(data.get(key)) is not int or not 0<=data[key]<=2**64-1:
            raise ValueError("invalid network sample")
    when=data.get("sample_time")
    if type(when) is not int or abs(time.time()-when)>180:
        raise ValueError("server time is not synchronized")
    return data

def basis(config):
    return "|".join([str(config["host"]),str(config["interface"]),
                     str(config.get("period_id","") or ""),
                     str(config.get("direction","") or ""),
                     str(config.get("initial_provider_used_gb","") or "")])

def calculate(config,sample,previous,now):
    """Returns dashboard summary and persistent ledger (NOT XUI totals)."""
    rx=int(sample["rx_bytes"]);tx=int(sample["tx_bytes"])
    boot=sample["boot_id"];index=sample["ifindex"]
    identity=f"{config['host']}|{config['interface']}"
    last=previous or {}
    if last and last.get("identity")!=identity:
        # Do not guess a new host/interface is the same traffic epoch.
        raise ValueError("meter host/NIC changed: explicit new period required")
    old_rx=last.get("last_rx");old_tx=last.get("last_tx")
    accum_rx=int(last.get("accum_rx",0))
    accum_tx=int(last.get("accum_tx",0))
    uncertain=bool(last.get("uncertain",False))
    gaps=int(last.get("gaps",0))
    reason=last.get("uncertain_reason","")
    if old_rx is not None and old_tx is not None:
        reset=(last.get("boot_id")!=boot or last.get("ifindex")!=index or
               rx<int(old_rx) or tx<int(old_tx))
        if reset:
            # Preserve the amount already measured, but it is a lower bound.
            uncertain=True;gaps+=1;reason="counter_reset_or_reboot"
        else:
            accum_rx+=rx-int(old_rx)
            accum_tx+=tx-int(old_tx)
    first=last.get("first_sample_at",now)
    stored={"identity":identity,"boot_id":boot,"ifindex":index,
            "last_rx":rx,"last_tx":tx,"accum_rx":accum_rx,"accum_tx":accum_tx,
            "first_sample_at":first,"sample_at":now,
            "uncertain":uncertain,"uncertain_reason":reason,"gaps":gaps,
            "epoch":last.get("epoch","")}
    data={"role":"iran","state":"ok","traffic_source":"physical_nic",
          "probe_state":"not_configured",
          "sample_age_s":0,
          "traffic_state":"direction_unconfirmed"}
    direction=config.get("direction")
    period=config.get("period_id")
    quota=config.get("quota_gb")
    initial=config.get("initial_provider_used_gb")
    if not period or direction not in ("rx","tx") or quota is None or initial is None:
        data["rx_period_gb"]=round(accum_rx/GB,3)
        data["tx_period_gb"]=round(accum_tx/GB,3)
        return data,stored
    if not isinstance(period,str) or not re.fullmatch(r"[A-Za-z0-9_.-]{4,70}",period):
        raise ValueError("invalid provider period_id")
    quota=safe_float(quota,0.01,1e9)
    initial=safe_float(initial,0,quota)
    epoch=f"{period}|{direction}|{initial:.6f}|{identity}"
    # On a new period the first current sample becomes the new baseline.
    # Never silently reset counters within an existing period.
    if stored["epoch"]!=epoch:
        if stored["epoch"] and stored["epoch"]!=epoch:
            # Explicit new period id (or a confirmed provider rebaseline).
            old_period=stored["epoch"].split("|",1)[0]
            if old_period==period:
                raise ValueError("existing period parameters changed; new period_id required")
        stored.update({"epoch":epoch,"last_rx":rx,"last_tx":tx,
                       "accum_rx":0,"accum_tx":0,"first_sample_at":now,
                       "uncertain":False,"uncertain_reason":"","gaps":0})
        accum_rx=accum_tx=0;uncertain=False
    data["rx_period_gb"]=round(accum_rx/GB,3)
    data["tx_period_gb"]=round(accum_tx/GB,3)
    measured=accum_rx if direction=="rx" else accum_tx
    used=initial+measured/GB
    remaining=max(0,quota-used)
    data.update({"traffic_source":"NIC_RX" if direction=="rx" else "NIC_TX",
                 "traffic_quota_gb":round(quota,3),
                 "traffic_used_gb":round(used,3),
                 "remaining_gb":round(remaining,3),
                 "traffic_state":"uncertain_reset" if uncertain else "estimated",
                 "sample_age_s":0})
    if uncertain:
        # Suppress potentially misleading precise remaining quota.
        data.pop("remaining_gb",None)
        data["traffic_used_gb"]=round(used,3)
    data["warning_10gb"]=bool(not uncertain and remaining<=WARNING_GB)
    return data,stored

def run():
    if os.geteuid()!=0:raise PermissionError("root required for local meter config")
    config=load(CONFIG)
    servers=config.get("servers",{})
    if not isinstance(servers,dict) or not set(servers).issubset(NAMES):
        raise ValueError("invalid server list")
    LOCK.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with open(LOCK,"a+") as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        prior=load(STATE,{})
        next_state=dict(prior)
        result={}
        for name in NAMES:
            settings=servers.get(name)
            if not settings:
                result[name]={"role":"iran","state":"not_configured",
                              "traffic_state":"not_configured"}
                continue
            try:
                if not isinstance(settings,dict):raise ValueError("invalid host config")
                sample=poll(name,settings)
                output,stored=calculate(settings,sample,prior.get(name),int(time.time()))
                result[name]=output
                next_state[name]=stored
                print("METER_OK",name,"RX_GB",output["rx_period_gb"],
                      "TX_GB",output["tx_period_gb"],
                      "quota",output["traffic_state"],flush=True)
            except Exception as exc:
                result[name]={"role":"iran","state":"unavailable",
                              "traffic_state":"unavailable"}
                print("METER_FAILED",name,type(exc).__name__,str(exc)[:100],
                      file=sys.stderr,flush=True)
        # Save counter state before rendering dashboard. Never reset on a failed poll.
        atomic(STATE,next_state)
        atomic(OUT,{"format":"HESAB_PHASE1_V1","collected_at":int(time.time()),
                    "servers":result})
        print("METER_DASHBOARD_UPDATED",OUT,flush=True)

if __name__=="__main__":
    try:run()
    except Exception as error:
        print("METER_COLLECTOR_STOP",type(error).__name__,str(error)[:100],
              file=sys.stderr)
        raise SystemExit(1)
