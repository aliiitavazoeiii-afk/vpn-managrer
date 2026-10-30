#!/usr/bin/env python3
"""HESAB_PHASE1_IRAN_REMOTE_SENSOR_V1 — installed read-only Linux sensor.
On the Iran host via restricted SSH: /usr/local/sbin/hesab-phase1-sensor <interface>.
No XUI process, configuration or user data touched.
"""
import json,os,re,sys,time
from pathlib import Path

def read_cpu():
    line=Path("/proc/stat").read_text().splitlines()[0].split()
    nums=[int(x) for x in line[1:]]
    idle=nums[3]+(nums[4] if len(nums)>4 else 0)
    return sum(nums),idle

def read_memory():
    values={}
    for line in Path("/proc/meminfo").read_text().splitlines():
        name,rest=line.split(":",1)
        if name in ("MemTotal","MemAvailable"):
            values[name]=int(rest.strip().split()[0])
    return values

def main():
    if len(sys.argv)!=2 or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,25}",sys.argv[1]):
        raise ValueError("invalid interface")
    interface=sys.argv[1]
    base=Path("/sys/class/net")/interface
    if not base.is_dir() or interface=="lo":raise ValueError("interface unavailable")
    before=read_cpu()
    time.sleep(0.35)
    after=read_cpu()
    total=after[0]-before[0];idle=after[1]-before[1]
    m=read_memory()
    cpu=round(100*(1-idle/max(1,total)),1)
    ram=round(100*(1-m["MemAvailable"]/m["MemTotal"]),1)
    rx=int((base/"statistics/rx_bytes").read_text())
    tx=int((base/"statistics/tx_bytes").read_text())
    boot=Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    print(json.dumps({"format":"HESAB_PHASE1_IRAN_SENSOR_V1",
      "cpu_pct":max(0,min(cpu,100)), "ram_pct":max(0,min(ram,100)),
      "rx_bytes":rx,"tx_bytes":tx,"boot_id":boot,
      "observed_at":int(time.time()),"interface":interface},separators=(",",":")))

if __name__=="__main__":main()
