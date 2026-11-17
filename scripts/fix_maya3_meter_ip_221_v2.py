#!/usr/bin/env python3
"""MAYA_S3_METER_IP_CORRECTION_V2: management-host NIC meter config ONLY.

The operator's Maya 3 console (root@maya11, 2026-11-17) reported
eth0=185.215.230.221/24. Previous assumed IP .214 is stale.
This script does NOT change X-UI, Xray, VPN tunnels, port 443, SSH config,
SSH trust/keys, finance, Docker, customer accounts or remote hosts.
Only a prior misattributed LOCAL NIC counter baseline may be invalidated.

Use --check first and then --apply. No implicit sensor enrollment.
"""
import argparse
import fcntl
import json
import os
import shutil
import stat
import sys
import tempfile
import time
from pathlib import Path

CFG = Path("/root/.config/hesab-maya-net-meter-v2.json")
STATE = Path("/var/lib/hesab-maya-net-meter-v2/state.json")
LOCK = Path("/var/lib/hesab-maya-net-meter-v2/poll.lock")
DAY = Path("/var/lib/hesab-maya-daily-v10/state.json")
DAYOUT = Path("/opt/vpn-control-center/maya_extra_sync/phase1/daily_nic_v10.json")
DAYLOCK = Path("/var/lib/hesab-maya-daily-v10/collector.lock")
HISTORY = Path("/var/lib/hesab-maya-traffic-history-v11/state.json")
HISTORY_OUT = Path("/opt/vpn-control-center/maya_extra_sync/phase1/traffic_history_v11.json")
SERVER = "maya-s3"
OLD_IP, NEW_IP = "185.215.230.214", "185.215.230.221"
MAYA4_IP = "5.10.249.206"
NAMES = {CFG: "meter-config.json", STATE: "meter-state.json",
         DAY: "daily-state.json", DAYOUT: "daily-export.json"}

def stop(msg):
    raise RuntimeError(msg)

def load(path, required=False):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        stop("INVALID_PATH " + str(path))
    if not path.exists():
        if required:
            stop("MISSING_FILE " + str(path))
        return None
    doc = json.loads(path.read_text(encoding="utf8"))
    if not isinstance(doc, dict):
        stop("INVALID_JSON " + str(path))
    return doc

def atomic(path, data):
    info = path.stat()
    fd, tmp = tempfile.mkstemp(prefix=".maya3-ip-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf8") as out:
            json.dump(data, out, ensure_ascii=False, separators=(",", ":"))
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.chmod(tmp, stat.S_IMODE(info.st_mode))
        os.chown(tmp, info.st_uid, info.st_gid)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def main():
    p = argparse.ArgumentParser()
    x = p.add_mutually_exclusive_group(required=True)
    x.add_argument("--check", action="store_true")
    x.add_argument("--apply", action="store_true")
    a = p.parse_args()
    if os.geteuid() != 0:
        stop("ROOT_ON_MANAGEMENT_HOST_REQUIRED")
    if not Path("/opt/vpn-control-center/docker-compose.yml").is_file():
        stop("NOT_HESAB_MANAGEMENT_HOST")
    if HISTORY.exists() or HISTORY_OUT.exists():
        stop("HISTORY_V11_ALREADY_EXISTS: inspect before changing identities")
    # Shared lock with live meter and daily collector. No timer reconfiguration.
    with open(LOCK, "a+") as lm, open(DAYLOCK, "a+") as ld:
        fcntl.flock(lm, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(ld, fcntl.LOCK_EX | fcntl.LOCK_NB)
        cfg = load(CFG, required=True)
        state = load(STATE, required=True)
        daily = load(DAY)
        daily_out = load(DAYOUT)
        servers = cfg.get("servers")
        if not isinstance(servers, dict) or not isinstance(servers.get(SERVER), dict):
            stop("MAYA3_METER_NOT_CONFIGURED")
        s3 = servers[SERVER]
        m4 = servers.get("maya4")
        if not isinstance(m4, dict) or (m4.get("host"), m4.get("interface")) != (MAYA4_IP, "ens160"):
            stop("MAYA4_REFERENCE_CHANGED: refusing to touch config")
        if s3.get("interface") != "eth0" or str(s3.get("ssh_port", 22)) != "22":
            stop("MAYA3_INTERFACE_OR_PORT_UNEXPECTED")
        if any(s3.get(k) not in (None, "", 0) for k in
               ("period_id", "direction", "initial_provider_used_gb", "quota_gb")):
            stop("MAYA3_HAS_BILLING_PERIOD: manual audit required")
        if s3.get("host") == NEW_IP:
            print("MAYA3_IP=ALREADY_CORRECT")
            print("SENSOR_STILL_NEEDS_RESTRICTED_SSH_VERIFICATION")
            return
        if s3.get("host") != OLD_IP:
            stop("UNEXPECTED_MAYA3_IP: refusing to guess")
        prior = state.get(SERVER)
        if prior is not None:
            if not isinstance(prior, dict) or prior.get("identity") != OLD_IP + "|eth0":
                stop("UNKNOWN_MAYA3_COUNTER_IDENTITY: preserve ledger")
        print("MAYA3_IP", OLD_IP, "=>", NEW_IP)
        print("MAYA3_NIC=eth0; MAYA4_UNCHANGED=" + MAYA4_IP)
        print("XUI_TUNNELS_SSH_SETTINGS_DATABASE_CHANGED=NO")
        if a.check:
            print("CHECK_ONLY=PASS NO_CHANGES")
            return
        targets = [f for f in NAMES if f.exists()]
        backup = Path("/root/maya3-meter-ip-backup-" +
                      time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) +
                      "-" + str(os.getpid()))
        backup.mkdir(mode=0o700)
        for f in targets:
            shutil.copy2(f, backup / NAMES[f])
            os.chmod(backup / NAMES[f], 0o600)
        print("BACKUP=" + str(backup))
        s3["host"] = NEW_IP
        state.pop(SERVER, None)  # no history from wrong host belongs to Maya3
        if daily and isinstance(daily.get("servers"), dict):
            daily["servers"].pop(SERVER, None)
        if daily_out and isinstance(daily_out.get("servers"), dict):
            daily_out["servers"][SERVER] = {"state": "unavailable"}
        changes = [(CFG, cfg), (STATE, state)]
        if daily is not None:
            changes.append((DAY, daily))
        if daily_out is not None:
            changes.append((DAYOUT, daily_out))
        try:
            for f, doc in changes:
                atomic(f, doc)
            assert load(CFG, required=True)["servers"][SERVER]["host"] == NEW_IP
        except BaseException:
            for f in targets:
                shutil.copy2(backup / NAMES[f], f)
            print("ROLLBACK=RESTORED_FROM_BACKUP")
            raise
    print("MAYA3_METER_IP_CORRECTED=YES")
    print("NOTE=SENSOR_PAIRING_NOT_AUTOMATIC; NO_XUI_CHANGES")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("MAYA3_REPAIR_STOP", type(exc).__name__, str(exc)[:180], file=sys.stderr)
        sys.exit(1)
