"""No-database regression tests for the shared first-day invoice calculator.

For pre-deploy testing using the currently running portal image:
    { cat customer_portal/billing_policy.py; cat customer_portal/billing_policy_test.py; } |
      docker compose -f docker-compose.yml -f docker-compose.sms.yml exec -T customer-portal python -
"""
from datetime import date as _test_date
import jdatetime as _test_jdatetime


def _jd(value):
    year, month, day = map(int, value.split("/"))
    return _test_jdatetime.date(year, month, day).togregorian()


def _start(value):
    j = _test_jdatetime.date.fromgregorian(date=value)
    return _test_jdatetime.date(j.year, j.month, 1).togregorian()


def _next(value):
    j = _test_jdatetime.date.fromgregorian(date=value)
    year, month = (j.year + 1, 1) if j.month == 12 else (j.year, j.month + 1)
    return _test_jdatetime.date(year, month, 1).togregorian()


def _invoice(expiry, fee, today):
    return calculate_invoice(_jd(expiry) if expiry else None, fee, _jd(today), _start, _next)


assert _invoice("1405/07/20", 300000, "1405/07/20") == {
    "due": True, "target": _jd("1405/08/01"), "amount": 110000,
}
assert _invoice("1405/07/21", 300000, "1405/07/20") == {
    "due": False, "target": _jd("1405/08/01"), "amount": 0,
}
assert _invoice("1405/07/21", 300000, "1405/07/21") == {
    "due": True, "target": _jd("1405/08/01"), "amount": 100000,
}
assert _invoice("1405/08/01", 300000, "1405/07/20") == {
    "due": False, "target": _jd("1405/09/01"), "amount": 0,
}
assert _invoice("1405/08/01", 300000, "1405/08/01") == {
    "due": True, "target": _jd("1405/09/01"), "amount": 300000,
}
assert _invoice("1405/08/05", 300000, "1405/07/20") == {
    "due": False, "target": _jd("1405/09/01"), "amount": 0,
}
assert _invoice("1405/08/05", 300000, "1405/08/05") == {
    "due": True, "target": _jd("1405/09/01"), "amount": 260000,
}
assert _invoice("1405/03/29", 300000, "1405/07/20")["target"] == _jd("1405/08/01")
assert _invoice("1405/07/20", 0, "1405/07/20")["amount"] == 0
assert _invoice(None, 300000, "1405/07/20")["amount"] == 0
print("BILLING POLICY: 10 TESTS PASSED, NO DATA CHANGED")
