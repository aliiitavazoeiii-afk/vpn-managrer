#!/usr/bin/env python3
"""HESAB_MAYA_NET_METER_MANAGER_V2 — guarded local configuration, no server writes."""
import ipaddress,json,os,re,subprocess,sys,time
from pathlib import Path

from maya_net_meter_collect_v2 import CONFIG,OUT,NAMES,validate_connection,load,atomic

def save_config(data):
    if not isinstance(data.get("servers"),dict):raise ValueError("invalid config")
    CONFIG.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if CONFIG.exists():
        backup=CONFIG.with_name(CONFIG.name+".bak."+str(int(time.time())))
        backup.write_bytes(CONFIG.read_bytes());backup.chmod(0o600)
    atomic(CONFIG,data)
    CONFIG.chmod(0o600)

def getkey(name):
    return Path("/root/.ssh")/("hesab_meter_"+name.replace("-","_"))

def initialize(name,host,interface,port):
    ip=ipaddress.ip_address(host)
    if ip.version!=4 or not ip.is_global:raise ValueError("public host IPv4 required")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,24}",interface) or interface=="lo":
        raise ValueError("invalid network interface")
    port=int(port)
    if not 1<=port<=65535:raise ValueError("invalid SSH port")
    cfg=load(CONFIG,{"servers":{}})
    servers=cfg.get("servers")
    if not isinstance(servers,dict):raise ValueError("invalid server config")
    new={"host":host,"interface":interface,"ssh_port":port}
    if name in servers:
        existing=servers[name]
        if any(existing.get(k)!=v for k,v in new.items()):
            raise ValueError("Existing host/interface differs: do not silently change meter identity")
    key=getkey(name)
    key.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if not key.exists():
        if key.with_suffix(key.suffix+".pub").exists():
            raise ValueError("orphan public key")
        subprocess.run(["ssh-keygen","-q","-t","ed25519","-N","",
                        "-f",str(key),"-C","hesab-"+name+"-meter-v2"],check=True)
    os.chmod(key,0o600)
    if not key.with_suffix(key.suffix+".pub").is_file():
        raise ValueError("public key missing")
    if name not in servers:servers[name]=new
    cfg["servers"]=servers
    save_config(cfg)
    print("CONFIG_READY",name,"IP",host,"NIC",interface,"PORT",port)
    print("COPY_PUBKEY_FROM",str(key)+".pub")
    print("REMOTE_INSTALL_NEEDED; SSH host fingerprint MUST be checked from host console")

def showkey(name):
    key=getkey(name)
    pub=Path(str(key)+".pub")
    if not pub.is_file():raise ValueError("no generated public key")
    print(pub.read_text().strip())

def quota(name,period,total,already,direction):
    if direction not in ("rx","tx"):
        raise ValueError("Choose explicit rx or tx only AFTER provider comparison")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{4,70}",period):
        raise ValueError("period ID: ASCII letters/numbers/underscore/hyphen, min 4")
    total=float(total);already=float(already)
    if not 0<total<1e9 or not 0<=already<=total:
        raise ValueError("invalid GB quota or provider-consumed amount")
    cfg=load(CONFIG)
    current=cfg.get("servers",{}).get(name)
    if not current:raise ValueError("host must be configured before quota")
    if current.get("period_id")==period:
        if current.get("direction")!=direction or float(current.get("initial_provider_used_gb",-1))!=already:
            raise ValueError("direction / initial amount changed: use a NEW period ID for rebaseline")
    current.update({"period_id":period,"quota_gb":total,
                    "initial_provider_used_gb":already,"direction":direction})
    save_config(cfg)
    print("QUOTA_CONFIGURED",name,"period",period,
          "quota_gb",total,"initial_used_gb",already,"NIC_direction",direction)
    print("NOTE: first successful poll under this period establishes baseline.")

def status():
    if not OUT.exists():print("NO_STATUS_YET");return
    data=json.loads(OUT.read_text())
    for name in NAMES:
        s=(data.get("servers") or {}).get(name,{})
        print(name,"sensor",s.get("state","missing"),
              "RX_period_GB",s.get("rx_period_gb","—"),
              "TX_period_GB",s.get("tx_period_gb","—"),
              "billable_direction",s.get("traffic_source","unconfirmed"),
              "billable_used_GB",s.get("traffic_used_gb","—"),
              "remaining_GB",s.get("remaining_gb","—"),
              "status",s.get("traffic_state","unconfigured"))

def verify(name):
    config=load(CONFIG)
    from maya_net_meter_collect_v2 import poll
    settings=config["servers"][name]
    x=poll(name,settings)
    print("RESTRICTED_SSH_SENSOR_OK",name,"iface",x["iface"],
          "RX_total_GB",round(x["rx_bytes"]/1e9,3),
          "TX_total_GB",round(x["tx_bytes"]/1e9,3))
    print("COUNTERS_ARE_SINCE_BOOT_OR_NIC_RESET; NOT PROVIDER_BILLING_PERIOD.")

def main():
    if os.geteuid()!=0:raise PermissionError("root required for protected keys")
    if len(sys.argv)<2:raise ValueError("init|pubkey|verify|quota|status")
    action=sys.argv[1]
    if action=="status" and len(sys.argv)==2:return status()
    if len(sys.argv)<3 or sys.argv[2] not in NAMES:raise ValueError("server must be maya1, maya-s3 or maya4")
    name=sys.argv[2]
    if action=="init" and len(sys.argv) in (5,6):
        initialize(name,sys.argv[3],sys.argv[4],sys.argv[5] if len(sys.argv)==6 else "22")
    elif action=="pubkey" and len(sys.argv)==3:showkey(name)
    elif action=="verify" and len(sys.argv)==3:verify(name)
    elif action=="quota" and len(sys.argv)==7:
        quota(name,sys.argv[3],sys.argv[4],sys.argv[5],sys.argv[6])
    else:raise ValueError("usage: init NAME IP IFACE [SSH_PORT] | pubkey NAME | verify NAME | quota NAME PERIOD TOTAL_GB PROVIDER_USED_GB rx|tx | status")

if __name__=="__main__":
    try:main()
    except Exception as ex:
        print("METER_MANAGER_STOP",type(ex).__name__,str(ex)[:180],file=sys.stderr)
        raise SystemExit(1)
