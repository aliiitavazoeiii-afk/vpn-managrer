#!/usr/bin/env python3
"""Temporary loopback-only signed HTTP receiver integration check (V11).

Standalone Python standard library. No external DNS or HTTP, no Docker
containers created, no Caddy changes, no Maya/HAProxy/Xray access and no
production database. All keys are randomly generated in memory. SQLite
is created only in an automatically removed OS temporary directory.
The test HTTP server uses an OS-assigned 127.0.0.1 port and is stopped.
"""
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import secrets
import sqlite3
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

PATH = Path(__file__).resolve().with_name("receiver.py")


def load_receiver():
    spec = importlib.util.spec_from_file_location("hesab_v11_smoketest_receiver", PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def synthetic_payload(timestamp, nonce):
    # Intentionally UNKNOWN/not-tested: never fabricate live data or quotas.
    return {
        "schema": "hesab-tunnel-v11",
        "server_id": "maya4",  # fixture ID only; no Maya host contacted
        "sent_at": timestamp, "nonce": nonce,
        "tunnel_type": "unidentified",
        "system": {
            "cpu_pct": None, "ram_pct": None, "disk_pct": None,
            "uptime_s": None, "interface": "synthetic",
            "rx_bytes": None, "tx_bytes": None,
            "tcp443_listen": "unknown",
        },
        "services": {},
        "controller": {"state": "unavailable", "age_s": None, "paths": {}},
        "haproxy": {}, "foreign_ips": {},
        "quota": {"state": "unknown", "remaining_gb": None},
        "xui_online": None, "vpn_end_to_end": "not_tested",
    }


def request(opener, url, body, headers):
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with opener.open(req, timeout=3) as res:
            return res.status
    except urllib.error.HTTPError as exc:
        exc.close()
        return exc.code


def main():
    if not PATH.is_file():
        print("SMOKETEST_BLOCKED=RECEIVER_SOURCE_NOT_FOUND")
        return 2
    receiver = load_receiver()
    with tempfile.TemporaryDirectory(prefix="hesab-v11-http-smoke-") as temp:
        db = Path(temp) / "sqlite" / "ephemeral.sqlite3"
        receiver.initialize(db)
        key = secrets.token_bytes(32)
        # Handler has class variables; only this in-process temporary server uses them.
        class TestHandler(receiver.Handler):
            keys = {"maya4": key}
            storage = db
            peer_mode = "loopback"

        server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        server.daemon_threads = True
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            assert server.server_address[0] == "127.0.0.1"
            endpoint = "http://127.0.0.1:" + str(server.server_address[1]) + receiver.PATH
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            timestamp = int(time.time())
            data = synthetic_payload(timestamp, secrets.token_hex(16))
            body = json.dumps(data, separators=(",", ":")).encode("utf-8")
            signature = hmac.new(key, str(timestamp).encode()+b"."+body,
                                 hashlib.sha256).hexdigest()
            headers = {
                "Content-Type": "application/json",
                "X-Forwarded-Proto": "https",
                "X-Hesab-Server": data["server_id"],
                "X-Hesab-Time": str(timestamp),
                "X-Hesab-Nonce": data["nonce"],
                "X-Hesab-Signature": "sha256=" + signature,
            }
            accepted = request(opener, endpoint, body, headers)
            assert accepted == 202, "valid signed payload rejected"
            replay = request(opener, endpoint, body, headers)
            assert replay in (409, 429), "signed replay was not rejected"
            bad_hmac = dict(headers)
            bad_hmac["X-Hesab-Signature"] = "sha256="+"0"*64
            invalid = request(opener, endpoint, body, bad_hmac)
            assert invalid == 401, "invalid HMAC accepted"
            plain = dict(headers)
            plain["X-Forwarded-Proto"] = "http"
            downgrade = request(opener, endpoint, body, plain)
            assert downgrade == 403, "non-HTTPS proxy header accepted"

            with sqlite3.connect(db) as sql:
                samples = sql.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
                replays = sql.execute("SELECT COUNT(*) FROM replays").fetchone()[0]
                state = sql.execute("SELECT effective_state FROM server_state WHERE server_id='maya4'").fetchone()[0]
                alerts = sql.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
            assert (samples,replays,state,alerts)==(1,1,"unknown",0), "unexpected SQLite state"
            print("HESAB_V11_TEMPORARY_HTTP_INTEGRATION")
            print("LISTEN_INTERFACE=127.0.0.1_ONLY")
            print("VALID_SIGNED_POST=202")
            print("REPLAY=REJECTED")
            print("INVALID_SIGNATURE=401")
            print("NON_HTTPS_FORWARD_HEADER=403")
            print("EPHEMERAL_SQLITE_SAMPLES=1")
            print("SYNTHETIC_VPN_HEALTH=UNKNOWN")
            print("PRODUCTION_CADDY_OR_DB_CHANGED=NO")
            print("MAYA_TUNNELS_CONTACTED=NO")
            print("TEST_RECEIVER_STOPPED_AND_TEMP_FILES_REMOVED=ON_EXIT")
            return 0
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, ValueError) as exc:
        print("HESAB_V11_TEMPORARY_HTTP_INTEGRATION=FAIL",
              type(exc).__name__)
        raise SystemExit(1)
