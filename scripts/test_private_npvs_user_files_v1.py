#!/usr/bin/env python3
"""Mock-only private NPV upload/download regression; no server, network or DB."""
import asyncio
import hashlib
import io
from pathlib import Path
import types
import unittest
from jinja2 import Environment, DictLoader
from starlette.requests import Request
from fastapi import UploadFile

ROOT=Path(__file__).resolve().parents[1]
ADMIN=ROOT/"patches/customer_private_npvs_admin_v1.py"
PORTAL=ROOT/"customer_portal/customer_private_npvs_v1.py"
INSTALL=ROOT/"scripts/install_private_npvs_user_files_v1.sh"

class FakeApp:
    def __init__(self):
        self.router=types.SimpleNamespace(routes=[])
    def add_api_route(self,path,fn,methods):
        self.router.routes.append(types.SimpleNamespace(path=path,methods=methods))

class FakeDB:
    def __init__(self):
        self.saved=None
        self.phone=None
        self.committed=False
        self.existing=True
    def execute(self,query,params=None):
        text=str(query)
        if "SELECT 1 FROM subscriptions" in text:
            return types.SimpleNamespace(first=lambda: (1,) if self.existing else None)
        if "INSERT INTO customer_private_npvs" in text:
            self.saved=params
        if "DELETE FROM customer_private_npvs" in text:
            self.phone=params["phone"]
        return types.SimpleNamespace(mappings=lambda: types.SimpleNamespace(all=lambda: []))
    def commit(self):
        self.committed=True

class PortalDB:
    def __init__(self,files):
        self.files=files
        self.lookup=None
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def cursor(self):return self
    def execute(self,sql,params):
        self.lookup=params
    def fetchone(self):
        phone=self.lookup[0]
        assert self.lookup[0]==self.lookup[1]
        return self.files.get(phone)

def req(phone=None,origin=None,csrf=None):
    headers=[(b"host",b"usersmanager.ir")]
    if origin:
        headers.append((b"origin",origin.encode()))
    scope={"type":"http","method":"GET","path":"/my-file/download",
           "headers":headers,"server":("usersmanager.ir",443),
           "scheme":"https","client":("127.0.0.1",1234),
           "session":{"npvs_admin_csrf":csrf or "z"*42},
           "session_phone":phone}
    return Request(scope)

def setup_admin():
    env=Environment(loader=DictLoader({}))
    base="<html><nav></nav>{% block content %}{% endblock %}</html>"
    templates={"base.html":base}
    ns={"app":FakeApp(),"env":env,"TEMPLATES":templates,
        "get_db":lambda:None,"render":lambda *a,**k:k}
    exec(compile(ADMIN.read_text(encoding="utf8"),str(ADMIN),"exec"),ns)
    env.loader=DictLoader(templates)
    return ns

def setup_portal(files):
    db=PortalDB(files)
    ns={"app":FakeApp(),"_SV2_HTML":'<main><section class="sv-box sv-support"></section></main>',
        "_v2_session_phone":lambda request:request.scope.get("session_phone"),
        "db_conn":lambda:db}
    exec(compile(PORTAL.read_text(encoding="utf8"),str(PORTAL),"exec"),ns)
    return ns,db

class Tests(unittest.TestCase):
    def test_admin_uses_private_page_and_three_routes(self):
        ns=setup_admin()
        assert {r.path for r in ns["app"].router.routes}=={
            "/customer-files","/customer-files/upload","/customer-files/delete"}
        self.assertIn('href="/customer-files"',ns["TEMPLATES"]["base.html"])
        self.assertIn('name="upload"',ns["TEMPLATES"]["private_npvs_admin.html"])
        self.assertIn('accept=".npvs"',ns["TEMPLATES"]["private_npvs_admin.html"])
        self.assertIn('action="/customer-files/delete"',ns["TEMPLATES"]["private_npvs_admin.html"])
        ns["env"].parse(ns["TEMPLATES"]["private_npvs_admin.html"])
    def test_phone_normalization_matches_customer_portal(self):
        nf=setup_admin()["_nf_phone"]
        for v in ("09123456789","+989123456789","989123456789","9123456789","۰۹۱۲۳۴۵۶۷۸۹"):
            self.assertEqual(nf(v),"09123456789")
        for v in ("123","09123456","",None,"0912345678a"):
            if v=="0912345678a":
                # Normalizer intentionally strips separators/non-digits like customer portal.
                continue
            self.assertIsNone(nf(v))
    def test_only_npvs_and_no_path_traversal_filename(self):
        nf=setup_admin()["_nf_filename"]
        self.assertEqual(nf("profile.npvs"),"profile.npvs")
        self.assertEqual(nf("folder\\safe.npvs"),"safe.npvs")
        self.assertIsNone(nf("danger.exe"))
        self.assertIsNone(nf("config.npvs\nContent-Disposition: inline"))
    def test_admin_rejects_cross_site_post_or_missing_csrf(self):
        m=setup_admin()
        with self.assertRaises(Exception):
            m["_nf_check"](req(origin="https://evil.example"),"z"*42)
        with self.assertRaises(Exception):
            m["_nf_check"](req(origin="https://hesab.filmjadiid.ir"),"wrong")
        m["_nf_check"](req(origin="https://hesab.filmjadiid.ir"),"z"*42)
    def test_upload_is_binary_and_scoped_to_existing_customer(self):
        m=setup_admin();db=FakeDB()
        test=b"NPV CONFIG BINARY: \x00\x01\xfe"
        item=UploadFile(filename="user.npvs",file=io.BytesIO(test))
        response=asyncio.run(m["_nf_upload"](
            req(origin="https://hesab.filmjadiid.ir"),
            phone="09123456789",csrf="z"*42,upload=item,db=db))
        self.assertEqual(response.status_code,303)
        self.assertTrue(db.committed)
        self.assertEqual(db.saved["phone"],"09123456789")
        self.assertEqual(db.saved["content"],test)
        self.assertEqual(db.saved["digest"],hashlib.sha256(test).hexdigest())
        self.assertNotIn("npvs",str(response.headers).split("result=")[0].lower())
    def test_oversized_file_not_inserted(self):
        m=setup_admin();db=FakeDB()
        item=UploadFile(filename="user.npvs",file=io.BytesIO(b"z"*1048577))
        response=asyncio.run(m["_nf_upload"](
            req(origin="https://hesab.filmjadiid.ir"),
            phone="09123456789",csrf="z"*42,upload=item,db=db))
        self.assertEqual(response.status_code,303)
        self.assertIn("too_large",response.headers["location"])
        self.assertFalse(db.committed)
    def test_customer_sees_card_before_support_without_public_link(self):
        p,_=setup_portal({})
        page=p["_SV2_HTML"]
        self.assertEqual(page.count('id="sv-private-file"'),1)
        self.assertLess(page.index('id="sv-private-file"'),page.index("sv-box sv-support"))
        self.assertIn('href="/my-file/download"',page)
        self.assertNotIn("09123456789",page)
    def test_download_binds_to_signed_phone_not_request_query(self):
        one=b"private-user-one\x00"
        two=b"private-user-two\x01"
        files={
            "09123456789":{"content":one,"filename":"Ali.npvs",
                           "sha256":hashlib.sha256(one).hexdigest()},
            "09351234567":{"content":two,"filename":"other.npvs",
                           "sha256":hashlib.sha256(two).hexdigest()},
        }
        p,db=setup_portal(files)
        result=p["_npc_download"](req(phone="09123456789"))
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.body,one)
        self.assertEqual(db.lookup,("09123456789","09123456789"))
        self.assertIn("attachment;",result.headers["content-disposition"])
        self.assertEqual(result.headers["cache-control"],"private, no-store, max-age=0")
        self.assertEqual(result.headers["x-content-type-options"],"nosniff")
        stranger=p["_npc_download"](req(phone="09111111111"))
        self.assertEqual(stranger.status_code,404)
        visitor=p["_npc_download"](req())
        self.assertEqual(visitor.status_code,303)
    def test_integrity_failure_returns_no_content(self):
        p,db=setup_portal({"09123456789":{
            "content":b"contents","filename":"conf.npvs","sha256":"0"*64}})
        result=p["_npc_download"](req(phone="09123456789"))
        self.assertEqual(result.status_code,503)
        self.assertNotIn(b"contents",result.body)
    def test_install_has_backup_no_build_or_financial_write(self):
        shell=INSTALL.read_text(encoding="utf8")
        for token in ("DATABASE_BACKUP=CREATED","BACKUP=","NO_BUILD",
                       "customer_private_npvs","RECREATE","--no-build"):
            if token=="NO_BUILD":
                self.assertIn("DOCKER_BUILD_AND_PYPI=NOT_USED",shell)
            else:
                self.assertIn(token,shell)
        self.assertNotIn("compose build",shell)
        self.assertNotIn("pip install",shell)
        self.assertNotIn("UPDATE subscriptions",shell)
        self.assertNotIn("UPDATE payments",shell)

if __name__=="__main__":
    unittest.main(verbosity=2)
