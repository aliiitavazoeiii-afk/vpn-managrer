#!/usr/bin/env python3
"""HESAB mobile v12 regression: code execution in mocked templates, mobile CSS,
JavaScript syntax, original links/routes preserved, no backend mutations."""
import re
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from jinja2 import Environment, DictLoader
import tinycss2

ROOT=Path(__file__).resolve().parents[1]
ADMIN=ROOT/"patches/mobile_dashboard_admin_v12.py"
CUSTOMER=ROOT/"customer_portal/mobile_dashboard_customer_v12.py"
INSTALL=ROOT/"scripts/install_mobile_dashboard_v12.sh"

BASE='''<!doctype html><html lang="fa" dir="rtl"><head>
<title>{% block title %}مدیریت{% endblock %}</title>
</head><body><div class="app"><aside class="sidebar"><nav>
<a href="/">داشبورد</a><a href="/debts">بدهی‌ها</a>
<a href="/payments">پرداخت‌ها</a><a href="/control-room">اتاق کنترل</a>
</nav></aside><main class="main">{% block content %}{% endblock %}</main>
</div></body></html>'''
HOME='''<!doctype html><html lang="fa" dir="rtl"><head>
<title>{{ phone }}</title></head><body><main><h1>{{ heading }}</h1>
<section class="sv-box sv-support"><h2>پشتیبانی</h2></section></main></body></html>'''
LOGIN='''<!doctype html><html><head><title>ورود</title></head><body>
<form action="/login"><input name="phone"></form></body></html>'''
DASH='''<!doctype html><html><head><title>پرداخت</title></head><body>
<form action="/pay-all"><button>پرداخت</button></form></body></html>'''

class FakeApp:
    def __init__(self):self.router=types.SimpleNamespace(routes=[])
    def get(self,path,include_in_schema=False):
        def decorator(fn):
            self.router.routes.append(types.SimpleNamespace(path=path,endpoint=fn))
            return fn
        return decorator

def extract(source,id):
    reg=r'<(style|script) id="'+re.escape(id)+r'">([\s\S]*?)</\1>'
    match=re.search(reg,source)
    assert match is not None,id
    return match.group(2)

def run_admin():
    templates={"base.html":BASE,"control_room.html":
        '<div id="c2-root"><div id="c2-cards" class="c2-cards"></div></div>'}
    env=Environment(loader=DictLoader(templates),autoescape=True)
    ns={"TEMPLATES":templates,"env":env}
    exec(compile(ADMIN.read_text(encoding="utf8"),str(ADMIN),"exec"),ns)
    return ns

def run_customer():
    ns={"_SV2_HTML":HOME,"_V2_DASH":DASH,"_V2_LOGIN":LOGIN,
        "_V2_PAYMENT_RETURN":DASH,"_V2_SAFARI":LOGIN,
        "app":FakeApp()}
    exec(compile(CUSTOMER.read_text(encoding="utf8"),str(CUSTOMER),"exec"),ns)
    return ns

class Tests(unittest.TestCase):
    def test_admin_adds_mobile_menu_without_removing_any_navigation_or_routes(self):
        ns=run_admin();s=ns["TEMPLATES"]["base.html"]
        self.assertEqual(s.count("hm12-admin-menu"),1)
        self.assertEqual(s.count("hm12-admin-mobile"),1)
        self.assertEqual(s.replace(ns["_HM12_CSS"],"").replace(ns["_HM12_JS"],"").replace('<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n',""),BASE)
        for href in ('href="/"','href="/debts"','href="/payments"','href="/control-room"'):
            self.assertIn(href,s)
        self.assertIn('aria-expanded',ns["_HM12_JS"])
        self.assertIn('aria-controls',ns["_HM12_JS"])
        self.assertIn('ev.key==="Escape"',ns["_HM12_JS"])
        self.assertIn('sidebar.inert=true',ns["_HM12_JS"])
        self.assertIn('MutationObserver',ns["_HM12_JS"])
        self.assertIn('if(!isMobile())return;',ns["_HM12_JS"])
        self.assertIn('function unwrapTables()',ns["_HM12_JS"])
        self.assertIn('close();unwrapTables();',ns["_HM12_JS"])
    def test_admin_responsive_css_and_control_room_are_explicit(self):
        css=extract(run_admin()["TEMPLATES"]["base.html"],"hm12-admin-mobile")
        for marker in ("@media (max-width: 860px)","@media(max-width:390px)",
            "@media (min-width: 861px)",".hm12-top",".hm12-backdrop",
            "#c2-root #c2-cards.c2-cards",".c2-table-wrap",
            ".t10-purchase",".c4-center",".c4-bottom",
            ".c2-kpis","#c3-table-controls",
            ".debt-head-v3",".waiting-head",".pla-kpis"):
            self.assertIn(marker,css,marker)
        self.assertIn('grid-template-columns:minmax(0,1fr)!important',css)
        self.assertIn('overflow-x:auto!important',css)
        self.assertNotIn('button{display:none',css)
        self.assertNotIn('.sidebar nav{display:none',css)
        self.assertNotIn('.c2-table-wrap{display:none',css)
    def test_admin_inline_javascript_valid(self):
        js=extract(run_admin()["TEMPLATES"]["base.html"],"hm12-admin-menu")
        result=subprocess.run(["node","--check"],input=js,text=True,
            capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_admin_mobile_css_valid(self):
        css=extract(run_admin()["TEMPLATES"]["base.html"],"hm12-admin-mobile")
        entries=tinycss2.parse_stylesheet(css,skip_whitespace=True,skip_comments=True)
        errors=[e for e in entries if e.type=="error"]
        self.assertFalse(errors,errors)
    def test_customer_links_only_head_and_registers_css_asset(self):
        ns=run_customer()
        for key,original in (("_SV2_HTML",HOME),("_V2_DASH",DASH),("_V2_LOGIN",LOGIN)):
            updated=ns[key]
            self.assertEqual(updated.count(ns["_HCM12_LINK"]),1)
            self.assertEqual(updated.replace(ns["_HCM12_LINK"]+"\n","",1),original)
        self.assertEqual([r.path for r in ns["app"].router.routes],
                         ["/assets/mobile-dashboard-v12.css"])
        response=ns["_hcm12_asset"]()
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers["cache-control"],"public,max-age=86400")
        self.assertIn("nosniff",response.headers["x-content-type-options"])
        self.assertIn(b".sv-top-grid",response.body)
    def test_customer_css_preserves_every_major_customer_section(self):
        css=run_customer()["_HCM12_STYLE"]
        for marker in (".sv-top-grid",".sv-feature-grid",".sv-duo",
                       ".sv-support",".sv-feature",".sv-speed-panel",
                       ".sv-private-file",".sv-file-action",".sv-history-row",
                       ".entry-modal-card",".login-shell",".account-meta",
                       ".account-actions",".renew-all","@media (max-width:390px)"):
            self.assertIn(marker,css,marker)
        self.assertNotIn('.sv-support{display:none',css)
        self.assertNotIn('.sv-private-file{display:none',css)
        self.assertNotIn('.account-actions{display:none',css)
        errors=[e for e in tinycss2.parse_stylesheet(css,
              skip_whitespace=True,skip_comments=True) if e.type=="error"]
        self.assertFalse(errors,errors)
    def test_production_installer_scoped_and_rollback(self):
        s=INSTALL.read_text(encoding="utf8")
        for marker in ("ADMIN_MOBILE_PREFLIGHT=PASS","CUSTOMER_MOBILE_PREFLIGHT=PASS",
          "BACKUP=","CHANGED=1","rollback()",
          "--no-deps --no-build --force-recreate app customer-portal",
          "SUCCESS=MOBILE_DASHBOARD_V12_INSTALLED"):
            self.assertIn(marker,s,marker)
        for prohibited in ("compose build","pip install","UPDATE subscriptions",
            "DROP TABLE","systemctl restart haproxy","xui.service"):
            self.assertNotIn(prohibited,s)
        self.assertIn('ADMIN=patches/maya1_control.py',s)
        self.assertIn('CUSTOMER=customer_portal/login_activity.py',s)
    def test_manual_rollback_refuses_unrelated_later_changes(self):
        rollback=(ROOT/"scripts/rollback_mobile_dashboard_v12.sh").read_text()
        self.assertIn('sha256sum -c "$BACKUP/installed-sha256.txt"',rollback)
        self.assertIn("STOP=PRODUCTION_CHANGED_AFTER_INSTALL_NO_AUTO_OVERWRITE",rollback)
        self.assertIn("SUCCESS=MOBILE_DASHBOARD_V12_ROLLED_BACK",rollback)
        self.assertIn('sha256sum "$ADMIN" "$CUSTOMER"',INSTALL.read_text())

    def test_duplicate_module_fail_closed(self):
        ns=run_admin()
        with self.assertRaises(RuntimeError):
            exec(compile(ADMIN.read_text(encoding="utf8"),str(ADMIN),"exec"),ns)
        ns=run_customer()
        with self.assertRaises(RuntimeError):
            exec(compile(CUSTOMER.read_text(encoding="utf8"),str(CUSTOMER),"exec"),ns)

if __name__=="__main__":unittest.main(verbosity=2)
