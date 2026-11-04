#!/usr/bin/env python3
"""Regression for Azar notice when navigating into the existing payment view.

Evaluates only the boolean expression in the V2 payment dashboard render call;
does not connect to the database or exercise actual billing/payment functions.
"""
import ast
from pathlib import Path
import types
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"customer_portal/v2.py"
TEMPLATE=ROOT/"customer_portal/dashboard_v2.html"
INSTALL=ROOT/"scripts/fix_portal_azar_notice_on_payment_v1.sh"

def flag(query):
    root=ast.parse(SOURCE.read_text(encoding="utf8"))
    func=next(x for x in root.body if isinstance(x,ast.FunctionDef) and x.name=="v2_home")
    calls=[n for n in ast.walk(func) if isinstance(n,ast.Call)
           and isinstance(n.func,ast.Name) and n.func.id=="_v2_render"]
    matching=[]
    for call in calls:
        if call.args and isinstance(call.args[0],ast.Name) and call.args[0].id=="_V2_DASH":
            matching += [k.value for k in call.keywords if k.arg=="show_welcome"]
    assert len(matching)==1
    expression=ast.Expression(body=matching[0])
    request=types.SimpleNamespace(query_params=query)
    return eval(compile(ast.fix_missing_locations(expression),str(SOURCE),"eval"),
                {"request":request},{})

class PaymentNoticeTests(unittest.TestCase):
    def test_notice_on_each_payment_page_open(self):
        self.assertTrue(flag({"view":"payments"}))
        self.assertTrue(flag({"view":"payments","other":"1"}))
    def test_old_login_welcome_is_preserved(self):
        self.assertTrue(flag({"welcome":"1"}))
        self.assertTrue(flag({"view":"payments","welcome":"1"}))
    def test_other_pages_do_not_get_popup(self):
        self.assertFalse(flag({}))
        self.assertFalse(flag({"view":"home"}))
        self.assertFalse(flag({"payment_error":"1"}))
    def test_same_original_azar_message_and_modal(self):
        html=TEMPLATE.read_text(encoding="utf8")
        self.assertEqual(html.count("تمامی اکانت‌ها تا تاریخ یکم آذر محاسبه می‌شوند."),1)
        self.assertEqual(html.count("از این پس سررسید اکانت شما یکم هر ماه خواهد بود."),1)
        self.assertEqual(html.count("{% if show_welcome %}"),1)
        self.assertEqual(html.count('id="entryModal"'),1)
        self.assertIn('onclick="dismissEntryNotice()"',html)
    def test_only_existing_boolean_condition_changed(self):
        text=SOURCE.read_text(encoding="utf8")
        new='show_welcome=(request.query_params.get("welcome") == "1" or request.query_params.get("view") == "payments"),'
        old='show_welcome=request.query_params.get("welcome") == "1",'
        self.assertEqual(text.count(new),1)
        self.assertNotIn(old,text)
        self.assertIn('response = RedirectResponse("/?welcome=1"',text)
        self.assertIn('@app.post("/pay-all")',text)
        self.assertIn('@app.post("/pay/{sid}")',text)
    def test_installer_scoped_to_customer_portal_only(self):
        script=INSTALL.read_text(encoding="utf8")
        for expected in ("SOURCE_PREFLIGHT=PASS",
                         "RUNNING_PORTAL_PREFLIGHT=PASS",
                         "DATABASE_BACKUP_FAILED",
                         "BACKUP=",
                         "ROLLING_BACK_AZAR_NOTICE",
                         "SUCCESS=AZAR_NOTICE_RESTORED_ON_PAYMENT_ENTRY"):
            self.assertIn(expected,script)
        self.assertIn("compose build customer-portal",script)
        self.assertIn("compose up -d --no-deps --no-build --force-recreate customer-portal",script)
        for forbidden in ("UPDATE subscriptions","UPDATE payments","DROP TABLE",
                          "DELETE FROM payments","systemctl restart",
                          "docker compose down","-d --no-deps --no-build --force-recreate app"):
            self.assertNotIn(forbidden,script)

if __name__=="__main__":
    unittest.main(verbosity=2)
