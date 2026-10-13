#!/usr/bin/env python3
"""MAYA1_CONTROL_GATEWAY_V1: local Unix socket -> restricted SSH forced command.

No TCP listener, no API tokens in the dashboard, no financial mutations.
"""
import json
import os
from pathlib import Path
import socketserver
import subprocess
import sys
import stat
from datetime import datetime, timezone

ROOT = Path("/opt/vpn-control-center")
DIR = ROOT / "maya1_sync"
SOCKET = DIR / "control.sock"
AUDIT = DIR / "actions.jsonl"
MAP = DIR / "mapping.json"
SNAPSHOT = DIR / "snapshot.json"
KEY = Path("/root/.ssh/hesab_maya1_control")
HOST = "94.184.4.38"
EXPECTED_SHA = "8e1509674cf0c06d1e8015064c8c3b69b76931311bce4489b1bbda49d50f37fb"

def _read(path):
    if not path.is_file() or path.stat().st_size > 3000000:
        raise ValueError("Missing or oversized approved Maya1 mapping/snapshot")
    return json.loads(path.read_text(encoding="utf8"))

def _audit(event):
    payload = dict(event)
    payload["at"] = datetime.now(timezone.utc).isoformat()
    data = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    fd = os.open(AUDIT, os.O_APPEND | os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)

def _verify(payload):
    if set(payload) != {"email", "sid", "target", "expected"}:
        raise ValueError("Unexpected toggle request")
    email, sid = payload["email"], payload["sid"]
    if not isinstance(email, str) or not email.strip() or len(email) > 180:
        raise ValueError("Invalid email label")
    if type(sid) is not int or sid <= 0:
        raise ValueError("Invalid dashboard subscription id")
    target, expected = payload["target"], payload["expected"]
    if type(target) is not bool or type(expected) is not bool or target == expected:
        raise ValueError("Invalid requested state transition")
    mapping = _read(MAP)
    snapshot = _read(SNAPSHOT)
    if (mapping.get("format") != "MAYA1_CONTROL_MAPPING_V1" or
        mapping.get("expected_sha") != EXPECTED_SHA or
        snapshot.get("format") != "MAYA1_CONTROL_SNAPSHOT_V1"):
        raise ValueError("Mapping fingerprint invalid")
    links = mapping["mapping"]
    clients = snapshot["clients"]
    if len(links) != 145 or len(clients) != 145:
        raise ValueError("Maya1 roster changed; stop controls")
    item = links.get(email.casefold())
    if not isinstance(item, dict) or item.get("id") != sid:
        raise ValueError("Not an approved dashboard link")
    if item.get("reason") not in ("confirmed", "exact_approved"):
        raise ValueError("Excluded from financial mapping")
    hits = [c for c in clients if str(c.get("email") or "").strip().casefold() == email.casefold()]
    if len(hits) != 1 or hits[0].get("enabled") is not expected:
        raise ValueError("Dashboard snapshot does not match requested change")
    dt = datetime.fromisoformat(snapshot["source_generated_at"].replace("Z", "+00:00"))
    if not dt.tzinfo or abs((datetime.now(timezone.utc) - dt).total_seconds()) > 900:
        raise ValueError("Maya1 inventory is stale; refresh first")
    if not KEY.is_file():
        raise ValueError("Control SSH key not installed")
    return {"email": email, "sid": sid, "expected": expected, "target": target}

def _execute(payload):
    event = {"email": payload["email"], "sid": payload["sid"],
             "target": payload["target"], "previous": payload["expected"]}
    try:
        work = _verify(payload)
        command = [
            "ssh", "-T", "-i", str(KEY), "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=5",
            "-o", "ServerAliveCountMax=2",
            "root@" + HOST, "hesab-maya1-control"
        ]
        proc = subprocess.run(
            command,
            input=json.dumps({"email": work["email"], "target": work["target"],
                              "expected": work["expected"]}),
            capture_output=True, text=True, timeout=40
        )
        if proc.returncode:
            raise RuntimeError("x-ui control operation rejected; verify the client in x-ui before retrying")
        if len(proc.stdout) > 2048:
            raise RuntimeError("Unexpected remote control response")
        output = json.loads(proc.stdout)
        if (output.get("ok") is not True or
            output.get("email", "").casefold() != work["email"].casefold() or
            output.get("enabled") is not work["target"]):
            raise RuntimeError("Remote control result not verified")
        event["result"] = "confirmed"
        # Force one refreshed snapshot so the UI reflects the new status promptly.
        refresh = subprocess.run(
            [sys.executable, str(ROOT/"scripts/maya1_readonly_sync.py"), "--sync"],
            cwd=ROOT, capture_output=True, text=True, timeout=55
        )
        event["snapshot_refreshed"] = refresh.returncode == 0
        _audit(event)
        return {"ok": True, "enabled": work["target"],
                "refreshed": event["snapshot_refreshed"]}
    except Exception as ex:
        event["result"] = "failed_or_uncertain"
        event["error_type"] = type(ex).__name__
        _audit(event)
        return {"ok": False,
                "message": "عملیات تأیید نشد. وضعیت کاربر را در x-ui بررسی کن و بعد دوباره تلاش کن."}

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        line = self.rfile.readline(2049)
        try:
            if len(line) > 2048 or not line.endswith(b"\n"):
                raise ValueError("Invalid request size")
            data = json.loads(line)
            if not isinstance(data, dict):
                raise ValueError("Expected request object")
            result = _execute(data)
        except Exception:
            result = {"ok": False, "message": "درخواست کنترل نامعتبر بود."}
        self.wfile.write((json.dumps(result, ensure_ascii=False) + "\n").encode())
        self.wfile.flush()

class Server(socketserver.UnixStreamServer):
    allow_reuse_address = True

def main():
    DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(DIR, 0o750)
    if SOCKET.exists():
        if not stat.S_ISSOCK(SOCKET.lstat().st_mode):
            raise RuntimeError("Socket path occupied by non-socket")
        SOCKET.unlink()
    with Server(str(SOCKET), Handler) as server:
        os.chmod(SOCKET, 0o660)
        server.serve_forever(poll_interval=0.2)

if __name__ == "__main__":
    main()
