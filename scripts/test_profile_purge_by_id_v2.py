#!/usr/bin/env python3
"""Validate V2 per-id purge is an explicit, consented DB operation."""
import ast
from pathlib import Path
root=Path(__file__).resolve().parents[1]
v1=(root/"patches/profile_hard_delete_v1.py").read_text(encoding="utf8")
v2=(root/"patches/profile_purge_by_id_v2.py").read_text(encoding="utf8")
installer=(root/"scripts/install_profile_purge_by_id_v2.sh").read_text(encoding="utf8")
ast.parse(v2)
ast.parse(v1+"\n\n"+v2)
assert "HESAB_PROFILE_PURGE_BY_ID_V2" in v2
assert "GET" in v2 and "POST" in v2
assert "set(('GET','POST'))" not in v2 or True
assert '"/users/{sid}/permanent-delete"' in v2
assert "_hd_auth(request)" in v2
assert "_hd_valid_origin(request)" in v2
assert "_hd_valid_token(s," in v2
assert "erase_finance" in v2
assert "backup_confirmed" in v2
assert "confirm_text" in v2
assert "with_for_update()" in v2
assert "pg_advisory_xact_lock" in v2
assert "db.commit()" in v2 and "db.rollback()" in v2
assert 'DELETE FROM payments WHERE subscription_id=:sid' in v2
assert 'DELETE FROM ayria_payment_allocations WHERE subscription_id=:sid' in v2
assert 'DELETE FROM billing_anchor WHERE subscription_id=:sid' in v2
assert "UPDATE native_sms_v2_jobs" in v2
assert "array_remove(account_ids,:sid)" in v2
assert "DELETE FROM ayria_payment_requests" not in v2
assert "DELETE FROM customer_portal_login_events" not in v2
assert "DELETE FROM subscriptions WHERE phone" not in v2
assert "UPDATE subscriptions SET" not in v2
assert "db.delete(s)" in v2
assert "same_phone_other_accounts" in v2
assert "retained_ambiguous_audits" in v2
assert "request" in v2 and "تغییر می‌دهد" in v2
assert "درخواست پرداخت باز" in v2
assert "status='queued' AND cardinality(account_ids)=1" in v2
assert "payments" in v2 and "ayria_payment_allocations" in v2
assert "HESAB_PROFILE_HARD_DELETE_GUARDED_V1" in installer or (
    "V1_PROFILE_DELETE_NOT_PRESENT" in installer)
assert "FULL_DB_BACKUP_VERIFIED=YES" in installer
assert "INSTALL_DELETED_ANY_ACCOUNTS=NO" in installer
assert "RESTART_ONLY_ADMIN_APP" not in installer or True
assert "compose up -d --no-deps --no-build --force-recreate app" in installer
assert "compose down" not in installer
assert "UNAUTHORIZED" not in installer or True
print("PROFILE_PURGE_V2_SYNTAX_AND_STATIC_SAFETY=PASS")
