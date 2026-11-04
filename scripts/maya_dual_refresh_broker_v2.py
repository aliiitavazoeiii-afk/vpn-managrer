#!/usr/bin/env python3
"""Local-only Dual cached-status refresh broker. No TCP port, no arbitrary commands.
The browser never receives an SSH key. Existing dedicated forced-command SSH
identity is used by the fixed hourly collector. Does not run 'dual health'.
"""
import json
import os
from pathlib import Path
import socketserver
import stat
import subprocess
import threading
import time

ROOT = Path("/opt/vpn-control-center")
SOCK = ROOT / "maya_extra_sync/dual_refresh_v2.sock"
SNAP = ROOT / "maya_extra_sync/dual_hourly_v1.json"
COLLECTOR = ROOT / "scripts/maya_dual_hourly_collect_v1.py"
LIMIT = 15
STATE_LOCK = threading.Lock()
RUNNING = False
LAST_STARTED = 0.0

def snapshot_time():
    try:
        doc = json.loads(SNAP.read_text(encoding="utf8"))
        timestamp = doc.get("collected_at")
        if doc.get("format") == "HESAB_DUAL_HOURLY_V1" and type(timestamp) is int:
            return int(SNAP.stat().st_mtime * 1000)
    except (OSError, ValueError, TypeError):
        pass
    return 0

def run_job():
    global RUNNING
    try:
        proc = subprocess.run(
            ["/usr/bin/python3", str(COLLECTOR)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, check=False, timeout=85,
        )
        print("DUAL_MANUAL_COLLECTOR_EXIT", proc.returncode, flush=True)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print("DUAL_MANUAL_COLLECTOR_ERROR", type(exc).__name__, flush=True)
    finally:
        with STATE_LOCK:
            RUNNING = False

def handle(message):
    global RUNNING, LAST_STARTED
    if message != {"op": "refresh"}:
        return {"ok": False, "error": "Unsupported operation"}
    before = snapshot_time()
    with STATE_LOCK:
        now = time.monotonic()
        if RUNNING:
            return {"ok": True, "accepted": True, "already_running": True,
                    "before": before}
        if LAST_STARTED and now - LAST_STARTED < LIMIT:
            return {"ok": False, "error": "Refresh cooldown"}
        if not COLLECTOR.is_file():
            return {"ok": False, "error": "Collector not installed"}
        RUNNING = True
        LAST_STARTED = now
        threading.Thread(target=run_job, name="manual-dual-refresh",
                         daemon=True).start()
    return {"ok": True, "accepted": True, "already_running": False, "before": before}

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            raw = self.rfile.readline(161)
            if not raw.endswith(b"\n") or len(raw) > 160:
                raise ValueError("Invalid request")
            payload = json.loads(raw)
            reply = handle(payload)
        except (ValueError, UnicodeError, TypeError):
            reply = {"ok": False, "error": "Invalid request"}
        self.wfile.write(json.dumps(reply, separators=(",", ":")).encode("utf8") + b"\n")

class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True

def main():
    if os.geteuid() != 0:
        raise PermissionError("Root required")
    SOCK.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    if os.path.lexists(str(SOCK)):
        mode = SOCK.lstat().st_mode
        if not stat.S_ISSOCK(mode):
            raise RuntimeError("Refusing to replace non-socket entry")
        SOCK.unlink()
    with Server(str(SOCK), Handler) as server:
        os.chmod(SOCK, 0o660)
        print("DUAL_REFRESH_BROKER=LISTENING_LOCAL_SOCKET", flush=True)
        try:
            server.serve_forever(poll_interval=0.2)
        finally:
            try:
                SOCK.unlink()
            except FileNotFoundError:
                pass

if __name__ == "__main__":
    main()
