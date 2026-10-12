"""Offline stress regression: 120 unique subscription cards render completely.

Uses synthetic names/IDs. No DB calls, login, real PII or billing mutations.
Run with: python scripts/test_portal_large_accounts.py
"""
from pathlib import Path
import os
from jinja2 import Environment
from html import unescape
from datetime import date

ROOT = Path(os.environ.get("PORTAL_TEST_BASE") or Path(__file__).resolve().parent.parent)
PORTAL = ROOT / "customer_portal" if (ROOT / "customer_portal").is_dir() else ROOT
template = (PORTAL / "dashboard_v2.html").read_text(encoding="utf-8")
overlay = PORTAL / "v2_performance.css"
style = (overlay if overlay.is_file() else PORTAL / "v2_polish.css").read_text(encoding="utf-8")
env = Environment(autoescape=True)
env.filters["fa"] = str
env.filters["money"] = lambda value: f"{int(value or 0):,}"
accounts = []
for n in range(120):
    accounts.append({
        "id": 900000 + n,
        "initial": "آ",
        "display_name": f"آزمایش-پرفورمنس-{n:03d}-Test-Mixed-Farsi-English-Server",
        "verified_payment": None,
        "debt": 125000 if n % 2 else 0,
        "followup_state": "waiting" if n % 5 == 0 else None,
        "transition_original_jalali": "۱۴۰۵/۰۷/۲۰",
        "transition_target_jalali": "۱۴۰۵/۰۸/۰۱",
        "transition_status": "first_day",
        "expiry_jalali": "۱۴۰۵/۰۷/۲۰",
        "monthly_fee": 200000,
    })
html = env.from_string(template).render(
    accounts=accounts, phone="09000000000", total_debt=7500000,
    total_payable=7500000, csrf="synthetic", message=None,
    message_is_error=False, show_welcome=False,
)
assert html.count('class="account-card ') == 120, "Some account cards were omitted"
for account in accounts:
    assert html.count(account["display_name"]) == 1, (
        f"Name missing or duplicated: {account['id']}"
    )
    assert html.count(f"/pay/{account['id']}") == (1 if account["debt"] else 0)
assert "PORTAL_PERFORMANCE_LITE_V1" in style
assert "animation:none!important" in style
assert "backdrop-filter:none!important" in style
print("PASS: 120 cards, all 120 names, account IDs and payment actions match.")
print("NO REAL CUSTOMER DATA WAS ACCESSED.")
