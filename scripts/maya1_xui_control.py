#!/usr/bin/env python3
"""MAYA1_XUI_CONTROL_V1: forced-command SSH bridge for one-client enable/disable.

Never edits x-ui SQLite directly. Preserves every field of the selected VLESS
client and sends a normal authenticated 3x-ui updateClient request to the
LOCAL panel only. Credentials never leave maya1.
"""
import copy
import getpass
import http.cookiejar
import json
import os
from pathlib import Path
import re
import sqlite3
import ssl
import sys
import tempfile
import time
from urllib import error, parse, request

DB = "file:/etc/x-ui/x-ui.db?mode=ro"
CONFIG = Path("/etc/hesab-maya1/xui-auth.json")
ALLOW = Path("/etc/hesab-maya1/allowed-clients.json")
MAX_JSON = 2000000

def _fail(message):
    raise RuntimeError(message)

def _load(path, maximum=MAX_JSON):
    if not path.is_file() or path.stat().st_size > maximum:
        _fail("Missing/oversized local configuration")
    return json.loads(path.read_text(encoding="utf8"))

def _save(path, obj):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, tmp = tempfile.mkstemp(prefix=".xui-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf8") as f:
            json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def _xui_db():
    db = sqlite3.connect(DB, uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db

def _panel_address():
    db = _xui_db()
    try:
        settings = dict(db.execute("SELECT key, value FROM settings"))
    finally:
        db.close()
    port = int(settings.get("webPort") or 0)
    if port < 1 or port > 65535:
        _fail("Invalid local x-ui web port")
    base = str(settings.get("webBasePath") or "/").strip()
    if not re.fullmatch(r"/?[a-zA-Z0-9_./-]{0,180}", base) or ".." in base:
        _fail("Unsupported x-ui base path")
    base = "/" + base.strip("/") if base.strip("/") else ""
    scheme = "https" if settings.get("webCertFile") and settings.get("webKeyFile") else "http"
    return scheme + "://127.0.0.1:" + str(port) + base

class Panel:
    def __init__(self, auth):
        self.base = _panel_address()
        self.jar = http.cookiejar.CookieJar()
        # The only destination is hardcoded loopback. Panel TLS cert commonly
        # names a public domain, so hostname verification is inappropriate here.
        handler = request.HTTPSHandler(context=ssl._create_unverified_context())
        self.opener = request.build_opener(handler, request.HTTPCookieProcessor(self.jar))
        self.auth = auth
        if auth.get("mode") == "login":
            login = parse.urlencode({"username": auth["username"], "password": auth["password"]}).encode()
            result = self._fetch("/login", login, "application/x-www-form-urlencoded", authenticated=False)
            if result.get("success") is not True or not list(self.jar):
                _fail("Local panel login rejected or no session cookie")
        elif auth.get("mode") != "token":
            _fail("Unsupported authentication mode")

    def _fetch(self, path, payload=None, mime="application/json", authenticated=True):
        if not path.startswith("/") or "//" in path or "://" in path:
            _fail("Invalid API path")
        uri = self.base + path
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = mime
        if authenticated and self.auth.get("mode") == "token":
            headers["Authorization"] = "Bearer " + self.auth["token"]
        req = request.Request(uri, data=payload, headers=headers)
        try:
            with self.opener.open(req, timeout=10) as response:
                if response.geturl().split("?", 1)[0] != uri:
                    _fail("Unexpected panel API redirect")
                raw = response.read(MAX_JSON + 1)
                if len(raw) > MAX_JSON:
                    _fail("Panel API response too large")
                obj = json.loads(raw)
                if not isinstance(obj, dict):
                    _fail("Unexpected panel API response type")
                return obj
        except (error.HTTPError, error.URLError):
            _fail("Local panel API request failed")

    def list_inbounds(self):
        doc = self._fetch("/panel/api/inbounds/list")
        if doc.get("success") is not True or not isinstance(doc.get("obj"), list):
            _fail("Panel API list denied or incompatible")
        return doc["obj"]

    def update_client(self, inbound_id, uuid, client):
        value = json.dumps({"clients": [client]}, ensure_ascii=False, separators=(",", ":"))
        payload = json.dumps({"id": inbound_id, "settings": value}, ensure_ascii=False).encode()
        safe_id = parse.quote(uuid, safe="")
        result = self._fetch("/panel/api/inbounds/updateClient/" + safe_id, payload)
        if result.get("success") is not True:
            _fail("Panel API rejected client update")

def _extract_client(inbounds, email):
    hits = []
    for inbound in inbounds:
        if str(inbound.get("protocol", "")).lower() != "vless":
            continue
        settings = inbound.get("settings") or {}
        if isinstance(settings, str):
            settings = json.loads(settings)
        if not isinstance(settings, dict):
            _fail("Unexpected inbound settings")
        for client in settings.get("clients", []):
            if str(client.get("email") or "").strip().casefold() == email.casefold():
                hits.append((inbound, client))
    if len(hits) != 1:
        _fail("Client not unique in panel API")
    return hits[0]

def _db_client(email):
    db = _xui_db()
    try:
        hits = []
        for row in db.execute("SELECT id, protocol, settings FROM inbounds"):
            if row["protocol"] != "vless":
                continue
            for c in json.loads(row["settings"] or "{}").get("clients", []):
                if str(c.get("email") or "").strip().casefold() == email.casefold():
                    hits.append((int(row["id"]), c))
        if len(hits) != 1:
            _fail("Client not unique in x-ui SQLite")
        return hits[0]
    finally:
        db.close()

def configure():
    print("Maya1 local panel API setup (secrets stay on maya1).")
    print("Mode: [p] panel username/password; [t] existing API bearer token")
    mode = input("Choose p or t: ").strip().lower()
    if mode == "p":
        username = input("x-ui username: ").strip()
        password = getpass.getpass("x-ui password (hidden): ")
        if not username or not password:
            _fail("Missing credentials")
        auth = {"mode": "login", "username": username, "password": password}
    elif mode == "t":
        token = getpass.getpass("x-ui API token (hidden): ").strip()
        if not token:
            _fail("Missing token")
        auth = {"mode": "token", "token": token}
    else:
        _fail("Unknown mode")
    # A non-mutating login+list probe proves the configured local API works.
    result = Panel(auth).list_inbounds()
    if len(result) != 1:
        _fail("Unexpected inbound count; cannot enable controls")
    _save(CONFIG, auth)
    print("SUCCESS: X-UI LOCAL API VERIFIED AND SAVED (no client altered)")

def check_configured():
    """Verify saved login and read-only API without changing any client."""
    auth = _load(CONFIG, 10000)
    result = Panel(auth).list_inbounds()
    if len(result) != 1:
        _fail("Unexpected local inbound count")
    allow = _load(ALLOW, 50000)
    if allow.get("format") != "MAYA1_ALLOWED_CLIENTS_V1" or len(allow.get("emails", [])) != 141:
        _fail("Approved client allowlist missing")
    print("SUCCESS: MAYA1 PANEL AUTH READY (READ ONLY)")

def execute():
    body = sys.stdin.buffer.read(2049)
    if len(body) > 2048:
        _fail("Control request too large")
    cmd = json.loads(body)
    if set(cmd) != {"email", "target", "expected"}:
        _fail("Unexpected control request")
    email = cmd["email"]
    target = cmd["target"]
    expected = cmd["expected"]
    if not isinstance(email, str) or len(email) > 180 or not email.strip():
        _fail("Invalid client label")
    if type(target) is not bool or type(expected) is not bool or target == expected:
        _fail("Invalid desired/current state")
    allow = _load(ALLOW, 50000)
    if allow.get("format") != "MAYA1_ALLOWED_CLIENTS_V1" or len(allow.get("emails", [])) != 141:
        _fail("Unverified control allowlist")
    allowed = allow["emails"]
    if len(allowed) != len(set(allowed)) or email.casefold() not in allowed:
        _fail("Client is not approved for remote control")
    inbound_id, original = _db_client(email)
    if bool(original.get("enable", True)) != expected:
        _fail("Client state changed since dashboard snapshot")
    panel = Panel(_load(CONFIG, 10000))
    inbound, api_client = _extract_client(panel.list_inbounds(), email)
    if int(inbound.get("id", -1)) != inbound_id:
        _fail("Inbound ID mismatch between local panel and SQLite")
    if bool(api_client.get("enable", True)) != expected:
        _fail("Panel client state changed before update")
    uuid = str(api_client.get("id") or "")
    if not re.fullmatch(r"[0-9a-fA-F-]{32,40}", uuid):
        _fail("Unexpected VLESS client ID")
    if uuid != str(original.get("id") or ""):
        _fail("VLESS client UUID mismatch")
    updated = copy.deepcopy(original)
    updated["enable"] = target
    panel.update_client(inbound_id, uuid, updated)
    for attempt in range(6):
        time.sleep(1)
        fresh_inbound, fresh_client = _extract_client(panel.list_inbounds(), email)
        new_db_id, db_client = _db_client(email)
        unchanged = all(db_client.get(k) == v for k, v in original.items() if k != "enable")
        if (int(fresh_inbound["id"]) == inbound_id and new_db_id == inbound_id
                and bool(fresh_client.get("enable", True)) == target
                and bool(db_client.get("enable", True)) == target
                and unchanged):
            print(json.dumps({"ok": True, "email": email, "enabled": target}, separators=(",", ":")))
            return
    _fail("Uncertain result: re-check target in x-ui before retrying")

if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            _fail("Usage: --configure, --check or --execute")
        if sys.argv[1] == "--configure":
            configure()
        elif sys.argv[1] == "--check":
            check_configured()
        elif sys.argv[1] == "--execute":
            execute()
        else:
            _fail("Unsupported command")
    except Exception as exc:
        # Do not echo credentials, UUID, custom panel base path, or API responses.
        print("MAYA1 CONTROL STOP: " + str(exc)[:160], file=sys.stderr)
        sys.exit(1)
