#!/usr/bin/env python3
"""Static and isolated functional tests for the operator V5 patch."""
import ast
import re
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

source=Path("patches/operator_workspace_v5.py").read_text()
tree=ast.parse(source)
def assign(name):
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"assignment missing: {name}")
def func(name,namespace):
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    node.decorator_list=[]
    # no defaults are evaluated without references:
    ns=ast.Module(body=[node],type_ignores=[])
    exec(compile(ast.fix_missing_locations(ns),"operator_workspace_v5.py","exec"),namespace)
    return namespace[name]

from jinja2 import Environment
env=Environment()
for name in ("_OP_SMS_TEMPLATE","_OP_PAYMENTS_TEMPLATE","_OP_ADD_RECENT"):
    tmpl=assign(name)
    env.parse(tmpl)
    assert tmpl.strip()
print("PASS: editable SMS, grouped payments, add-user template Jinja syntax")

scope={"_op_re":re,"_OP_TOKENS":frozenset(("{تاریخ_انقضا}","{نام_کاربر}"))}
validate=func("_op_sms_validate",scope)
assert validate("سلام {تاریخ_انقضا}")=="سلام {تاریخ_انقضا}"
assert validate("سلام {نام_کاربر} {تاریخ_انقضا}")
for bad in ("سلام", "سلام {foo} {تاریخ_انقضا}", "سلام {تاریخ_انقضا}", " "):
    if bad=="سلام {تاریخ_انقضا}":continue
    try:validate(bad)
    except ValueError:pass
    else:raise AssertionError(f"invalid format accepted: {bad}")
print("PASS: expiry token required, unknown placeholders rejected")

scope={
    "_OP_DEFAULTS":{"debt":"سلام {نام_کاربر} {تاریخ_انقضا}","waiting":"پیگیری {تاریخ_انقضا}"},
    "_op_sms_get":lambda db:{"debt":"سلام {نام_کاربر} {تاریخ_انقضا}","waiting":"پرداخت {تاریخ_انقضا}"},
    "_ews_expiry_label":lambda expiry:"۶ مهر",
    "globals":globals
}
scope.pop("globals")
scope["jdate"]=lambda expiry:str(expiry)
render=func("_op_sms_render",scope)
assert render(None,"debt",date(2026,9,28),"علی")=="سلام علی ۶ مهر"
assert render(None,"waiting",date(2026,9,28))=="پرداخت ۶ مهر"
print("PASS: per-customer date + optional name, independent list templates")

for name in ("_op_all_users","_op_add_user_page","_op_payments_page","_op_sms_settings","_op_sms_save","_op_waiting_sms"):
    assert any(isinstance(n,ast.FunctionDef) and n.name==name for n in tree.body),name
assert 'order_by(Subscription.id.desc())' in source
assert 'limit(10).all()' in source
assert 'matched.slice((page-1)*10,page*10)' in source
assert "Payment.paid_at.desc()" in source and 'ZoneInfo as _op_zone' in source
assert '"/sms/send",_op_no_manual_send' in source
assert '"/sms/templates/save",_op_sms_save' in source
assert '"/sms/waiting-renewal",_op_waiting_sms' in source
assert '"/followups/sms-reminder",_op_waiting_sms' in source
assert '_ns_enqueue(db,phone,"manual",message)' in source
assert not any(word in source for word in ('SmsManager','SEND_SMS','DELETE FROM payments','UPDATE subscriptions SET'))
print("PASS: 10-at-a-time pagination, payment date grouping, existing manual queue")

old=Path("patches/sms_native_v2.py").read_text()
installer=Path("scripts/install_operator_workspace_v5.sh").read_text()
assert old.count("message=_ABAN_SMS_PATTERN.format(expiry=jdate(earliest))")==1
assert 'message=_op_sms_render(db,"debt",earliest,min(eligible' in installer
assert 'pg_dump' in installer and 'rollback()' in installer
print("PASS: safe installer anchors existing canonical debt SMS and backs up DB")
