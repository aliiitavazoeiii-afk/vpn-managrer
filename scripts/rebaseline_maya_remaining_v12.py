#!/usr/bin/env python3
"""Maya operator-reported remaining balance rebaseline (V12, NIC-only).

Use: python3 scripts/rebaseline_maya_remaining_v12.py --check 364 434 214
     python3 scripts/rebaseline_maya_remaining_v12.py --apply 364 434 214

Updates ONLY the V6 non-live provider reference and V7 provisional RX baseline.
Leaves V9 purchase journal intact; its old-epoch purchases are intentionally
excluded from the NEW reported remaining, which is assumed to include ALL
previous purchases. New V9 purchases continue to count against the new epoch.
No XUI, SSH, VPN tunnels, meter state, quota periods, DB, timer or app restarts.
The NIC direction is NOT provider-verified. Disable hard 10GB quota actions.
"""
import argparse
import fcntl
import json
import math
import os
import shutil
import stat
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path("/opt/vpn-control-center")
PHASE = ROOT / "maya_extra_sync/phase1"
REF = PHASE / "provider_balance_reference_v1.json"
BASE = PHASE / "provisional_meter_baseline_v7.json"
SAMPLE = PHASE / "status.json"
CFG = Path("/root/.config/hesab-maya-net-meter-v2.json")
LOCK = Path("/var/lib/hesab-maya-net-meter-v2/rebaseline-remaining-v12.lock")
UI = ROOT / "patches/maya1_control.py"
NAMES = ("maya1", "maya-s3", "maya4")
HOSTS = {
    "maya1": ("94.184.4.38", "ens160"),
    "maya-s3": ("185.215.230.221", "eth0"),
    "maya4": ("5.10.249.206", "ens160"),
}

def stop(msg):
    raise RuntimeError(msg)

def read_doc(path, required=True):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        stop("UNSAFE_FILE " + str(path))
    if not path.is_file():
        if required: stop("MISSING_FILE " + str(path))
        return None
    if not 0 < path.stat().st_size < 80000:
        stop("INVALID_FILE_SIZE " + str(path))
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict): stop("INVALID_JSON " + str(path))
    return result

def write_atomic(path, doc):
    metadata = path.stat()
    fd, temp = tempfile.mkstemp(prefix=".v12-remaining-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(doc, stream, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, stat.S_IMODE(metadata.st_mode))
        os.chown(temp, metadata.st_uid, metadata.st_gid)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def valid_gb(value):
    if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 1e9:
        stop("INVALID_METER_VALUE")
    return float(value)

def main():
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--apply", action="store_true")
    parser.add_argument("balances", type=float, nargs=3, metavar=("MAYA1_GB", "MAYA3_GB", "MAYA4_GB"),
                        help="Latest total remaining GB for Maya1, Maya3, Maya4, inclusive of prior purchases")
    args = parser.parse_args()
    values = {name: round(valid_gb(v), 3) for name, v in zip(NAMES, args.balances)}
    if os.geteuid() != 0 or not (ROOT / "docker-compose.yml").is_file():
        stop("MANAGEMENT_HOST_ROOT_REQUIRED")
    if not UI.is_file() or UI.is_symlink():
        stop("LIVE_UI_MISSING")
    ui_source = UI.read_text(encoding="utf-8")
    for marker in ("# HESAB_CONTROL_ROOM_PROVIDER_REFERENCE_V6",
                   "# HESAB_MAYA_PROVISIONAL_REMAINING_V7",
                   "# HESAB_CONTROL_ROOM_TRAFFIC_TOPUP_V9",
                   "# HESAB_CONTROL_ROOM_COMPACT_V10"):
        if marker not in ui_source:
            stop("LIVE_UI_MISSING_REQUIRED_COMPONENT " + marker)
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        cfg = read_doc(CFG)
        old_ref = read_doc(REF)
        old_base = read_doc(BASE)
        sample = read_doc(SAMPLE)
        now = int(time.time())
        if (old_ref.get("format") != "HESAB_PROVIDER_BALANCE_REFERENCE_V1" or
            old_base.get("format") != "HESAB_MAYA_PROVISIONAL_BASELINE_V7" or
            sample.get("format") != "HESAB_PHASE1_V1" or
            old_base.get("direction_assumption") != "rx" or
            old_base.get("alert_eligible") is not False or
            old_base.get("provider_observation_time_known") is not False):
            stop("UNEXPECTED_EXISTING_REFERENCE_FORMAT")
        if type(old_base.get("created_at")) is not int:
            stop("OLD_BASELINE_HAS_NO_EPOCH")
        if not 0 <= now - sample.get("collected_at", -1) <= 120:
            stop("SENSOR_SNAPSHOT_NOT_FRESH")
        if not now > old_base["created_at"]:
            stop("OLD_EPOCH_NOT_IN_PAST: retry a moment later, no changes")
        rows = {}
        for name in NAMES:
            config = cfg.get("servers", {}).get(name, {})
            health = sample.get("servers", {}).get(name, {})
            if (config.get("host"), config.get("interface")) != HOSTS[name]:
                stop("UNEXPECTED_SERVER_IDENTITY " + name)
            if any(config.get(k) not in (None, "", 0) for k in
                   ("period_id", "direction", "quota_gb", "initial_provider_used_gb")):
                stop("PROVIDER_QUOTA_ALREADY_CONFIGURED " + name)
            if (health.get("state") != "ok" or
                health.get("traffic_state") != "direction_unconfirmed" or
                health.get("counter_uncertain") is not False):
                stop("NIC_SENSOR_NOT_SAFELY_CALIBRATABLE " + name)
            if name not in old_base.get("servers", {}) or name not in old_ref.get("servers", {}):
                stop("PREVIOUS_REFERENCE_SERVER_MISSING " + name)
            rx = valid_gb(health.get("rx_period_gb"))
            tx = valid_gb(health.get("tx_period_gb"))
            rows[name] = {
                "starting_reported_remaining_gb": values[name],
                "rx_baseline_gb": rx,
                "tx_baseline_gb": tx,
                "baseline_meter_time": sample["collected_at"],
            }
            print("PLAN", name, "remaining_gb", values[name],
                  "new_rx_baseline_gb", rx)
        print("BALANCES_INCLUDE_PREVIOUS_PURCHASES=ASSUMED")
        print("OLD_V9_PURCHASE_JOURNAL=RETAINED_NOT_RECREDITED")
        print("RX_BILLING_DIRECTION=UNCONFIRMED")
        print("XUI_TUNNELS_FINANCE_METER_LEDGER_QUOTA=UNCHANGED")
        if args.check:
            print("DRY_RUN=PASS NO_CHANGES")
            return

        # Ensure old-epoch purchases cannot match the new V9 epoch.
        for name in NAMES:
            old_epoch = str(old_base["created_at"]) + "|" + str(
                old_base["servers"][name].get("rx_baseline_gb"))
            new_epoch = str(now) + "|" + str(rows[name]["rx_baseline_gb"])
            if old_epoch == new_epoch:
                stop("TOPUP_EPOCH_COLLISION " + name)
        backup = Path("/root/maya-remaining-v12-backup-" +
                      time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) +
                      "-" + str(os.getpid()))
        backup.mkdir(mode=0o700)
        for file, name in ((REF, "old-provider-reference.json"),
                           (BASE, "old-provisional-baseline.json")):
            shutil.copy2(file, backup / name)
            os.chmod(backup / name, 0o600)
        print("BACKUP=" + str(backup))
        new_ref = {
            "format": "HESAB_PROVIDER_BALANCE_REFERENCE_V1",
            "recorded_at": now,
            "provider_observed_at_known": False,
            "source": "operator_report",
            "servers": {n: {"remaining_gb": values[n]} for n in NAMES},
        }
        new_base = {
            "format": "HESAB_MAYA_PROVISIONAL_BASELINE_V7",
            "created_at": now,
            "direction_assumption": "rx",
            "provider_observation_time_known": False,
            "alert_eligible": False,
            "servers": rows,
        }
        try:
            write_atomic(REF, new_ref)
            write_atomic(BASE, new_base)
            if (read_doc(REF) != new_ref or read_doc(BASE) != new_base):
                stop("POST_WRITE_VALIDATION_FAILED")
        except BaseException:
            print("REBASE_FAILED_RESTORING_BACKUP")
            shutil.copy2(backup / "old-provider-reference.json", REF)
            shutil.copy2(backup / "old-provisional-baseline.json", BASE)
            raise
        print("SUCCESS=MAYA_REMAINING_V12_REBASE")
        print("NO_APP_RESTART_REQUIRED=YES")
        print("V9_FUTURE_TOPUPS_USE_NEW_EPOCH=YES")
        print("NOTE=Provisional RX estimate; not authoritative provider billing")

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("REBASE_STOP", type(error).__name__, str(error)[:200], file=sys.stderr)
        sys.exit(1)
