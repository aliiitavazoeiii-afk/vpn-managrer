#!/usr/bin/env python3
"""MAYA_METER_IDENTITY_REPAIR_V1

Management-host-only correction of two reversed NIC-meter targets.
User-confirmed physical identities (2026-11-17):
  maya-s3 = 185.215.230.214 (eth0, as recorded for that host)
  maya4   = 5.10.249.206 (ens160, as recorded for that host)

Scope: ONLY the NIC-meter configuration and its *local* misattributed
read-only counter baselines. Does NOT touch X-UI, tunneling, SSH settings,
authorized_keys, client accounts, billing, provider quota, Docker or Caddy.
Requires explicit --apply. All original files are backed up, mode 0600.

Connectivity still requires the correct restricted SSH key, port and remote
sensor to work. Never weaken StrictHostKeyChecking to make a probe pass.
"""
import argparse
import fcntl
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CFG = Path("/root/.config/hesab-maya-net-meter-v2.json")
METER = Path("/var/lib/hesab-maya-net-meter-v2/state.json")
DAY = Path("/var/lib/hesab-maya-daily-v10/state.json")
DAY_OUT = Path("/opt/vpn-control-center/maya_extra_sync/phase1/daily_nic_v10.json")
METER_LOCK = Path("/var/lib/hesab-maya-net-meter-v2/poll.lock")
DAY_LOCK = Path("/var/lib/hesab-maya-daily-v10/collector.lock")
V11_STATE = Path("/var/lib/hesab-maya-traffic-history-v11/state.json")
V11_OUT = Path("/opt/vpn-control-center/maya_extra_sync/phase1/traffic_history_v11.json")
BEFORE = {
    "maya-s3": ("5.10.249.206", "ens160"),
    "maya4": ("185.215.230.214", "eth0"),
}
AFTER = {
    "maya-s3": ("185.215.230.214", "eth0"),
    "maya4": ("5.10.249.206", "ens160"),
}
TARGETS = tuple(BEFORE)

def fail(message):
    raise RuntimeError(message)

def load(path, mandatory=False):
    if path.is_symlink():
        fail("SYMLINK_REFUSED " + str(path))
    if not path.exists():
        if mandatory:
            fail("REQUIRED_FILE_MISSING " + str(path))
        return None
    if not path.is_file():
        fail("NOT_A_FILE " + str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        fail("JSON_OBJECT_EXPECTED " + str(path))
    return data

def write_json_atomic(path, data):
    metadata = path.stat() if path.exists() else None
    fd, temp = tempfile.mkstemp(prefix=".maya-meter-identity-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, separators=(",", ":"))
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.chmod(temp, stat.S_IMODE(metadata.st_mode) if metadata else 0o600)
        if metadata is not None:
            os.chown(temp, metadata.st_uid, metadata.st_gid)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def sensor_probe(name, config):
    from importlib.util import spec_from_file_location, module_from_spec
    path = Path("/opt/vpn-control-center/scripts/maya_net_meter_collect_v2.py")
    if not path.is_file():
        print(name, "SENSOR=COLLECTOR_MISSING")
        return False
    spec = spec_from_file_location("meter_probe_v2", path)
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        result = mod.poll(name, config)
        correct = result.get("iface") == config["interface"]
        print(name, "SENSOR=" + ("OK" if correct else "NIC_MISMATCH"),
              "HOST=" + config["host"], "NIC=" + str(result.get("iface")))
        return correct
    except Exception as exc:
        # The meter intentionally redacts SSH stderr. Do not print keys.
        print(name, "SENSOR=UNAVAILABLE", "REASON=" + type(exc).__name__,
              "HOST=" + config["host"], "PORT=" + str(config.get("ssh_port", 22)))
        return False

def main():
    parser = argparse.ArgumentParser(description="Fix reversed Maya 3/4 NIC-meter targets only")
    args = parser.add_mutually_exclusive_group(required=True)
    args.add_argument("--check", action="store_true", help="show planned change; no writes")
    args.add_argument("--apply", action="store_true", help="apply verified local meter mapping")
    opts = parser.parse_args()
    if os.geteuid() != 0:
        fail("ROOT_ON_MANAGEMENT_HOST_REQUIRED")
    if not Path("/opt/vpn-control-center/docker-compose.yml").is_file():
        fail("MANAGEMENT_HOST_LAYOUT_MISSING")
    # The V11 history store cannot safely be relabelled; stop if it already exists.
    if V11_STATE.exists() or V11_OUT.exists():
        fail("V11_HISTORY_PRESENT: do not remap existing historical series automatically")
    for path in (METER_LOCK, DAY_LOCK):
        if not path.parent.is_dir():
            fail("METER_OR_DAILY_LOCK_DIRECTORY_MISSING")
    # Existing collectors take these same locks. No timer/service stop needed.
    with open(METER_LOCK, "a+") as mlock, open(DAY_LOCK, "a+") as dlock:
        fcntl.flock(mlock, fcntl.LOCK_EX)
        fcntl.flock(dlock, fcntl.LOCK_EX)
        config = load(CFG, mandatory=True)
        meter = load(METER, mandatory=True)
        daily = load(DAY)
        daily_out = load(DAY_OUT)
        servers = config.get("servers")
        if not isinstance(servers, dict) or any(n not in servers for n in TARGETS):
            fail("BOTH_SERVER_ENTRIES_REQUIRED")
        current = {}
        for name in TARGETS:
            item = servers[name]
            if not isinstance(item, dict):
                fail("INVALID_METER_CONFIG " + name)
            current[name] = (item.get("host"), item.get("interface"))
            if str(item.get("ssh_port", 22)) != "22":
                fail("NONDEFAULT_SSH_PORT: review host-specific port before applying")
            if any(item.get(key) not in (None, "", 0) for key in
                   ("period_id", "direction", "initial_provider_used_gb", "quota_gb")):
                fail("PROVIDER_QUOTA_PRESENT: manual period audit required " + name)
        if current == AFTER:
            print("MAPPING=ALREADY_CORRECT")
            for name in TARGETS:
                sensor_probe(name, servers[name])
            return
        if current != BEFORE:
            fail("UNEXPECTED_CURRENT_MAPPING: no changes applied")
        data = meter
        for name in TARGETS:
            raw = data.get(name)
            if raw is not None:
                if not isinstance(raw, dict):
                    fail("INVALID_METER_STATE " + name)
                expected_identity = "|".join(BEFORE[name])
                if raw.get("identity") != expected_identity:
                    fail("UNKNOWN_METER_IDENTITY " + name)
        for name in TARGETS:
            print("PLAN", name, "FROM", current[name][0], current[name][1],
                  "TO", AFTER[name][0], AFTER[name][1])
        print("PLAN: retain dedicated per-server SSH keys; backup and reset only two")
        print("      incorrectly labelled NIC-meter and daily RX baselines.")
        print("XUI_TUNNELS_FINANCE_SMS_CHANGED=NO")
        if opts.check:
            print("DRY_RUN=PASS NO_FILES_CHANGED")
            return
        files = [p for p in (CFG, METER, DAY, DAY_OUT) if p.exists()]
        backup = Path("/root/maya-meter-identity-backup-" +
                      time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) +
                      "-" + str(os.getpid()))
        backup.mkdir(mode=0o700)
        for path in files:
            shutil.copy2(path, backup / path.name)
            os.chmod(backup / path.name, 0o600)
        print("BACKUP=" + str(backup))
        for name in TARGETS:
            servers[name]["host"], servers[name]["interface"] = AFTER[name]
            meter.pop(name, None)  # NEVER reuse the wrong host's RX/TX counter identity
            if daily is not None:
                d = daily.get("servers")
                if isinstance(d, dict):
                    d.pop(name, None)
            if daily_out is not None:
                d = daily_out.get("servers")
                if isinstance(d, dict):
                    d[name] = {"state": "unavailable"}
        changes = [(CFG, config), (METER, meter)]
        if daily is not None:
            changes.append((DAY, daily))
        if daily_out is not None:
            changes.append((DAY_OUT, daily_out))
        try:
            for path, data in changes:
                write_json_atomic(path, data)
            validated = load(CFG, mandatory=True)["servers"]
            for name in TARGETS:
                assert (validated[name]["host"], validated[name]["interface"]) == AFTER[name]
        except BaseException:
            print("FAILED=RESTORING_LOCAL_METER_FILES")
            for path in files:
                shutil.copy2(backup / path.name, path)
            raise
    print("LOCAL_MAPPING_REPAIRED=YES")
    print("COUNTER_BASELINE=NEW_ON_NEXT_SUCCESSFUL_SENSOR_POLL")
    print("NOTE=Previous misattributed counters retained securely in backup only")
    for name in TARGETS:
        sensor_probe(name, servers[name])
    print("DONE=ONLY_MAYA_NIC_METER_FILES_CHANGED")

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("REPAIR_STOP", type(error).__name__, str(error)[:220], file=sys.stderr)
        sys.exit(1)
