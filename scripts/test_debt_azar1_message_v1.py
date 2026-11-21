#!/usr/bin/env python3
"""Verify canonical, operator-approved 1 Azar debt reminder without a running app."""
import ast
from pathlib import Path

root=Path(__file__).resolve().parents[1]
src=(root/"patches/sms_aban_default.py").read_text(encoding="utf-8")
native=(root/"patches/sms_native_v2.py").read_text(encoding="utf-8")
waiting=(root/"patches/waiting_expiry_sms_v2.py").read_text(encoding="utf-8")

expected=(
    "سلام، امروز اکانت شما تموم می‌شه.\n\n"
    "تا ساعت ۱۸ امروز برای پرداخت فرصت هست و بعد از این ساعت، اکانت شما قطع خواهد شد.\n\n"
    "امکان پرداخت تا ساعت ۱۲ ظهر روز ۲ آذر وجود داره و بعد از اون اکانت های پرداخت نشده حذف خواهد شد.\n\n"
    "اکانت شما به محض پرداخت مجدداً متصل خواهد شد.\n\n"
    "usersmanager.ir"
)
nodes=[node for node in ast.parse(src).body if isinstance(node,ast.Assign)
       and len(node.targets)==1 and isinstance(node.targets[0],ast.Name)
       and node.targets[0].id=="_ABAN_SMS_PATTERN"]
assert len(nodes)==1,"ambiguous canonical reminder"
text=ast.literal_eval(nodes[0].value)
assert text==expected,"canonical text differs from operator-approved message"
assert text.endswith("usersmanager.ir")
assert text.count("usersmanager.ir")==1
assert "\n\n" in text
assert "{expiry}" not in text
assert len(text)<1000
assert '_aban_display_text = _ABAN_SMS_PATTERN.replace(' in src
assert 'body = _ABAN_SMS_PATTERN.format(expiry=jdate(earliest))' in src
assert 'message=_ABAN_SMS_PATTERN.format(expiry=jdate(earliest))' in native
assert 'return _ABAN_SMS_PATTERN' in waiting
for name in ("patches/sms_aban_default.py","patches/sms_native_v2.py",
             "patches/waiting_expiry_sms_v2.py"):
    compile((root/name).read_text(encoding="utf-8"),name,"exec")
print("AZAR1_DEBT_MESSAGE_AND_USERSMANAGER_IR=PASS")
print("SHARED_DEBT_AND_WAITING_TEXT_PATH=PASS")
print("TEXT_LENGTH=",len(text))
