from __future__ import annotations
import json
from datetime import datetime
from typing import Any
import httpx
from .security import decrypt_secret

class XUIError(RuntimeError):
    pass

class XUIClientAPI:
    def __init__(self, server):
        self.server = server
        self.base = server.base_url.rstrip("/")
        self.client = httpx.Client(timeout=httpx.Timeout(12.0, connect=6.0), verify=server.verify_ssl, follow_redirects=True, headers={"User-Agent": "VPN-Control-Center/1.0"})

    def _unwrap(self, response: httpx.Response) -> Any:
        if response.status_code >= 400:
            raise XUIError(f"HTTP {response.status_code}")
        try:
            data = response.json()
        except Exception as exc:
            raise XUIError("پاسخ پنل JSON نبود") from exc
        if isinstance(data, dict) and data.get("success") is False:
            raise XUIError(str(data.get("msg") or "خطای پنل"))
        if isinstance(data, dict) and "obj" in data:
            return data.get("obj")
        return data

    def login(self):
        url = f"{self.base}/login"
        payload = {"username": self.server.username, "password": decrypt_secret(self.server.password_encrypted)}
        resp = self.client.post(url, data=payload)
        data = self._unwrap(resp)
        if not self.client.cookies:
            try:
                raw = resp.json()
                if isinstance(raw, dict) and raw.get("success") is False:
                    raise XUIError(str(raw.get("msg") or "ورود ناموفق"))
            except ValueError:
                pass
        return data

    def get(self, path: str): return self._unwrap(self.client.get(f"{self.base}{path}"))
    def post(self, path: str, data: dict | None = None): return self._unwrap(self.client.post(f"{self.base}{path}", data=data or {}))

    def collect(self) -> dict:
        self.login()
        inbounds = self.get("/panel/api/inbounds/list") or []
        status = self.get("/panel/api/server/status") or {}
        try: onlines_raw = self.post("/panel/api/inbounds/onlines") or []
        except Exception: onlines_raw = []
        try: last_online_raw = self.post("/panel/api/inbounds/lastOnline") or []
        except Exception: last_online_raw = []
        return {"inbounds": inbounds if isinstance(inbounds, list) else [], "status": status if isinstance(status, dict) else {}, "onlines": normalize_online(onlines_raw), "last_online": normalize_last_online(last_online_raw)}

def normalize_online(raw: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str): out.add(item.lower())
            elif isinstance(item, dict):
                for key in ("email", "client", "name"):
                    if item.get(key): out.add(str(item[key]).lower()); break
    elif isinstance(raw, dict):
        for k, v in raw.items():
            if v: out.add(str(k).lower())
    return out

def normalize_last_online(raw: Any) -> dict[str, datetime]:
    result: dict[str, datetime] = {}; items = raw if isinstance(raw, list) else []
    if isinstance(raw, dict): items = [{"email": k, "lastOnline": v} for k, v in raw.items()]
    for item in items:
        if not isinstance(item, dict): continue
        email = item.get("email") or item.get("client") or item.get("name")
        value = item.get("lastOnline") or item.get("last_online") or item.get("time")
        if not email or not value: continue
        try:
            ts = float(value)
            if ts > 10_000_000_000: ts /= 1000
            result[str(email).lower()] = datetime.utcfromtimestamp(ts)
        except Exception: pass
    return result

def parse_clients(inbounds: list[dict], onlines: set[str], last_online: dict[str, datetime]) -> list[dict]:
    result: list[dict] = []
    for inbound in inbounds:
        if not isinstance(inbound, dict): continue
        inbound_id = inbound.get("id"); protocol = str(inbound.get("protocol") or ""); stats = inbound.get("clientStats") or []
        if not isinstance(stats, list): stats = []
        settings = inbound.get("settings") or "{}"; clients_cfg = []
        try:
            parsed = json.loads(settings) if isinstance(settings, str) else settings
            clients_cfg = parsed.get("clients", []) if isinstance(parsed, dict) else []
        except Exception: clients_cfg = []
        cfg_by_email = {}
        for cfg in clients_cfg:
            if isinstance(cfg, dict):
                e = cfg.get("email") or cfg.get("name") or cfg.get("id")
                if e: cfg_by_email[str(e).lower()] = cfg
        seen = set()
        for st in stats:
            if not isinstance(st, dict): continue
            email = str(st.get("email") or st.get("name") or st.get("id") or "").strip()
            if not email: continue
            key = email.lower(); cfg = cfg_by_email.get(key, {}); seen.add(key)
            result.append({"inbound_id": inbound_id, "client_key": f"{inbound_id}:{cfg.get('id') or st.get('id') or email}", "email": email, "protocol": protocol, "enabled": bool(cfg.get("enable", st.get("enable", True))), "online": key in onlines, "up": int(st.get("up") or 0), "down": int(st.get("down") or 0), "total": int(st.get("total") or cfg.get("totalGB") or 0), "expiry_time": int(st.get("expiryTime") or cfg.get("expiryTime") or 0), "last_online": last_online.get(key)})
        for cfg in clients_cfg:
            if not isinstance(cfg, dict): continue
            email = str(cfg.get("email") or cfg.get("name") or cfg.get("id") or "").strip()
            if not email or email.lower() in seen: continue
            key = email.lower()
            result.append({"inbound_id": inbound_id, "client_key": f"{inbound_id}:{cfg.get('id') or email}", "email": email, "protocol": protocol, "enabled": bool(cfg.get("enable", True)), "online": key in onlines, "up": 0, "down": 0, "total": int(cfg.get("totalGB") or 0), "expiry_time": int(cfg.get("expiryTime") or 0), "last_online": last_online.get(key)})
    return result
