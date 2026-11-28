#!/usr/bin/env python3
"""Offline verification of distinct admin-only permanent-delete profile action."""
import ast
from pathlib import Path
root=Path(__file__).resolve().parents[1]
patch=(root/"patches/profile_hard_delete_v1.py").read_text(encoding="utf-8")
script=(root/"scripts/install_profile_hard_delete_v1.sh").read_text(encoding="utf-8")
life=(root/"patches/user_lifecycle.py").read_text(encoding="utf-8")
ast.parse(patch)
assert "# HESAB_PROFILE_HARD_DELETE_GUARDED_V1" in patch
assert 'TEMPLATES["user_detail.html"]' in patch
assert '"hd-erase-user"' in patch
assert "request.path_params['sid']" in patch
assert "permanent-delete" in patch
assert '"GET"' in patch and '"POST"' in patch
assert 'db.query(Subscription)' in patch
assert ".with_for_update()" in patch
assert 'db.commit()' in patch and 'db.rollback()' in patch
assert "pg_advisory_xact_lock" in patch
assert "APP_SECRET_KEY" in patch and "_hd_hmac.compare_digest" in patch
assert 'not _hd_valid_origin(request)' in patch
assert "payments" in patch and "ayria_payment_allocations" in patch
assert "native_sms_v2_jobs" in patch
assert "account_ids" in patch
assert "information_schema.columns" in patch and "pg_constraint" in patch
assert "sms_jobs" not in patch or "phone_tables" in patch
assert "status_code=303" in patch
assert "UPDATE payments" not in patch and "db.delete(s)" in patch
assert "TEMPLATES[\"user_status.html\"]" in patch
assert "/manage/users/{sid}/delete" in life
assert '"POST", _lc_archive_one' in life
assert "pre-enable-postgres.dump" in script and "pg_dump" in script
assert "pg_restore --list" in script
assert "RESTART_ONLY_ADMIN_APP=YES" in script
assert "ROLLBACK=RESTORE_COMPOSE_AND_DISABLE_PROFILE_ACTION" in script
assert "profile_hard_delete_v1.py:/sms-patch/profile_hard_delete_v1.py:ro" in script
assert "USER_OR_PAYMENT_ROWS_CHANGED=NO" in script
assert "docker compose down" not in script
print("PROFILE_HARD_DELETE_V1_STATIC_SAFETY=PASS")
