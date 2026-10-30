#!/usr/bin/env python3
"""HESAB_MAYA_NET_METER_SENSOR_V2
Local read-only physical-interface meter, intended for restricted SSH command.
Does not require X-UI access, iptables, tcpdump, a daemon, or open TCP ports.
"""
import json, re, sys, time
from pathlib import Path

def capture(iface):
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,24}", iface) or iface == "lo":
        raise ValueError("invalid interface")
    base = Path("/sys/class/net") / iface
    if not base.is_dir():
        raise ValueError("network interface not found")
    stats=base / "statistics"
    def number(name):
        n=int((stats/name).read_text().strip())
        if n<0 or n>2**64-1:raise ValueError("invalid counter")
        return n
    rx=number("rx_bytes")
    tx=number("tx_bytes")
    index=int((base/"ifindex").read_text().strip())
    boot=Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", boot):
        raise ValueError("invalid boot id")
    uptime=int(float(Path("/proc/uptime").read_text().split()[0]))
    return {"format":"HESAB_MAYA_NET_SENSOR_V2", "iface":iface,
            "ifindex":index,"boot_id":boot,
            "rx_bytes":rx,"tx_bytes":tx,"uptime_s":uptime,
            "sample_time":int(time.time())}

def main():
    if len(sys.argv)!=2:
        raise ValueError("usage: hesab-net-meter <physical-nic>")
    print(json.dumps(capture(sys.argv[1]),separators=(",",":")))

if __name__=="__main__":
    try:main()
    except Exception as error:
        print("SENSOR_ERROR",type(error).__name__,file=sys.stderr)
        raise SystemExit(1)
