#!/usr/bin/env python3
"""Offline guard: no mass deletion, no automatic sends, only old Azar1 texts."""
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
p=ROOT/"scripts/clean_unsent_azar1_whatsapp_drafts_v1.py"
s=p.read_text(encoding="utf8")
tree=ast.parse(s)
vals={}
for n in tree.body:
    if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name):
        if n.targets[0].id in ("NEW","OLD_MESSAGES"):
            vals[n.targets[0].id]=ast.literal_eval(n.value)
assert len(vals)==2
new=vals["NEW"]
old=vals["OLD_MESSAGES"]
assert len(old)==2 and all(x!=new and x.startswith("سلام") for x in old)
assert all("usersmanager.ir" in x for x in old)
assert new.endswith("usersmanager.ir")
assert "فرصت هست" in new and "اکانت های پرداخت نشده حذف" in new
canonical=ast.parse((ROOT/"patches/sms_aban_default.py").read_text(encoding="utf8"))
src=[n for n in canonical.body if isinstance(n,ast.Assign)
    and len(n.targets)==1 and isinstance(n.targets[0],ast.Name)
    and n.targets[0].id=="_ABAN_SMS_PATTERN"]
assert len(src)==1 and ast.literal_eval(src[0].value)==new
native=(ROOT/"patches/sms_native_v2.py").read_text(encoding="utf8")
assert '"cancelled","operator_opened","sent","delivered"' in native or (
    '"cancelled","operator_opened","sent","delivered"' in native.replace(" ",""))
assert "PREVIOUS_SMS_UNCERTAIN_OR_PENDING_REVIEW" in native
assert 'status <> ' in native
assert "ONLY" in s and "NO_RECORDS_CHANGED" in s
assert "WHERE status='queued' AND message IN " in s
assert "NEW_APPROVED_DRAFT_ALREADY_QUEUED" in s
assert "UNRELATED_PENDING_DRAFTS_EXIST" in s
assert "CLAIMED_OR_OPENED_ROW_CHANGED" in s
assert "status='cancelled'" in s
assert "pg_dump" in s and "pg_restore" in s
assert "WITH old_drafts AS" in s
for forbidden in ("DELETE FROM native_sms_v2_jobs","TRUNCATE ","UPDATE subscriptions",
                  "UPDATE payments","docker compose down","psql -c DELETE"):
    assert forbidden not in s,forbidden
print("OLD_AZAR1_UNSENT_WHATSAPP_QUEUE_CLEAN_TEST=PASS")
