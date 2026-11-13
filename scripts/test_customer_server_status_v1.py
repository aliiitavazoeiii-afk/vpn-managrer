#!/usr/bin/env python3
"""HESAB_CUSTOMER_SERVER_STATUS_TEST_V1.
Tests actual V1 addons against isolated mock DB/app and protected temp reports.
No real network, SSH, data transfer, Production state or VPN dependency.
"""
import asyncio
import concurrent.futures
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
ADMIN=ROOT/"patches/customer_server_status_bridge_v1.py"
CUSTOMER=ROOT/"customer_portal/customer_server_status_portal_v1.py"

class App:
    def __init__(self):
        self.router=type("Router",(),{"routes":[]})()
    def add_api_route(self,path,fn,methods=None,**kwargs):
        self.router.routes.append(type("Route",(),{
            "path":path,"endpoint":fn,"methods":set(methods or [])})())

class FakeRequest:
    def __init__(self,sid=None,headers=None,payload=None,phone=None):
        self.query_params={} if sid is None else {"sid":str(sid)}
        self.headers=headers or {}
        self._body=json.dumps(payload).encode() if payload is not None else b""
        self.phone=phone
    async def body(self):return self._body

def decode(response):
    return response.status_code,json.loads(response.body)

def admin_module(approved=None):
    scope={"app":App(),"_ma_approved":lambda: approved or {},
           "_ML_APPROVAL_SHA":"trust-sha"}
    exec(compile(ADMIN.read_text(),str(ADMIN),"exec"),scope)
    return scope

def portal_module(owned=None,template=None):
    owned=owned or {"09120000000":[1,9],"09350000000":[3],"09121111111":[4]}
    class DB:
        def __enter__(self):return self
        def __exit__(self,*args):pass
    def active(db,phone):
        return [{"id":sid,"display_name":"اشتراک "+str(sid)}
                for sid in owned.get(phone,[])]
    scope={"app":App(),
           "_SV2_HTML":template if template is not None else '''<!doctype html><html lang="fa"><head></head><body>
        <section class="sv-server"><div class="sv-server-footer"></div></section>
        </body></html>''',
           "_v2_session_phone":lambda request:request.phone,
           "normalize_phone":lambda p:p,
           "db_conn":lambda:DB(),"active_subscriptions":active,
           "csrf_for":lambda p:"csrf-"+p,
           "verify_csrf":lambda p,t:t=="csrf-"+p}
    exec(compile(CUSTOMER.read_text(),str(CUSTOMER),"exec"),scope)
    return scope

def dual(now,server="maya1"):
    return {"format":"HESAB_DUAL_HOURLY_V1","collected_at":now,
       "servers":{server:{"state":"ok","sampled_at":now,
        "controller_age_s":3,"paths":{
        "backhaul":{"state":"healthy","https_total":3,"https_passed":3},
        "mieru":{"state":"healthy","https_total":3,"https_passed":3}}}}}

def metrics(elapsed=4000,got=524288,code=0,reason="complete"):
    return {"state":"healthy" if code==0 and got==524288 and elapsed<=12000 else "warning",
       "requested_bytes":524288,"received_bytes":got,"http_status":200,
       "exit_code":code,"duration_ms":elapsed,"ttfb_ms":100,
       "reason":reason}

def transfer(now,server="maya1",path=None):
    paths=path or {k:metrics() for k in ("backhaul","mieru","haproxy")}
    return {"format":"HESAB_PATH_TEST_ACCOUNT_V1","state":"completed",
       "run_id":"a"*24,"started_at":now-35,"completed_at":now,
       "servers":{server:{"state":"completed","paths":paths}}}

class Tests(unittest.TestCase):
    def test_known_subscription_unique_authoritative_approvals(self):
        approved={"maya1":{"a":{"sid":1}},"maya-s3":{"b":{"sid":3}},
                  "maya4":{"c":{"sid":4}}}
        n=admin_module(approved)
        self.assertEqual(n["_cssb_server_for_sid"](1),"maya1")
        self.assertEqual(n["_cssb_server_for_sid"](3),"maya-s3")
        self.assertEqual(n["_cssb_server_for_sid"](4),"maya4")
        self.assertIsNone(n["_cssb_server_for_sid"](7))
        self.assertFalse(any(x in ADMIN.read_text() for x in
               ("ssh root@", "subprocess.run", "curl --", "socket.connect")))
    def test_cross_server_conflict_and_legacy_exclusion(self):
        app=admin_module({"maya1":{"a":{"sid":1},"b":{"exclude":True}},
                          "maya4":{"d":{"sid":1}}})
        self.assertIsNone(app["_cssb_server_for_sid"](1))
        app["_cssb_legacy"]=lambda:{"b":21,"other":33}
        self.assertIsNone(app["_cssb_server_for_sid"](21))
        self.assertEqual(app["_cssb_server_for_sid"](33),"maya1")
    def test_maya1_legacy_atomic_sync_0640_is_accepted_but_public_read_is_not(self):
        n=admin_module()
        class FakePath:
            def __init__(self,mode):self.mode=mode
            def stat(self):
                return type("Stat",(),{"st_uid":0,"st_mode":self.mode})()
            def is_symlink(self):return False
        n["_CSSB_LEGACY"]=FakePath(0o100640)
        n["_cssb_read"]=lambda path,limit:{
            "format":"MAYA1_CONTROL_MAPPING_V1",
            "expected_sha":"trust-sha",
            "mapping":{"approved":{"id":11,"reason":"confirmed"},
                       "automatic":{"id":12,"reason":"exact_name"}}}
        self.assertEqual(n["_cssb_legacy"](),{"approved":11})
        n["_CSSB_LEGACY"]=FakePath(0o100644)
        self.assertEqual(n["_cssb_legacy"](),{})
        n["_CSSB_LEGACY"]=FakePath(0o100660)
        self.assertEqual(n["_cssb_legacy"](),{})

    def test_admin_internal_route_rejects_unauthenticated_and_tampered(self):
        n=admin_module({"maya1":{"a":{"sid":1}}})
        with tempfile.TemporaryDirectory() as d:
            key=Path(d)/"key"
            key.write_bytes(b"A"*48)
            key.chmod(0o600)
            n["_CSSB_SECRET"]=key
            now=int(time.time())
            n["_cssb_time"].time=lambda:now
            stamp=str(now)
            sig=hmac.new(b"A"*48,f"v1:{stamp}:1".encode(),hashlib.sha256).hexdigest()
            self.assertEqual(decode(n["_cssb_endpoint"](FakeRequest(sid=1)))[0],403)
            self.assertEqual(decode(n["_cssb_endpoint"](FakeRequest(sid=1,headers={
                "x-hesab-status-at":stamp,"x-hesab-status-signature":sig})))[0],200)
            self.assertEqual(decode(n["_cssb_endpoint"](FakeRequest(sid=3,headers={
                "x-hesab-status-at":stamp,"x-hesab-status-signature":sig})))[0],403)
            self.assertEqual(decode(n["_cssb_endpoint"](FakeRequest(sid=1,headers={
                "x-hesab-status-at":str(now-40),"x-hesab-status-signature":sig})))[0],403)
            self.assertEqual(decode(n["_cssb_endpoint"](FakeRequest(sid="maya4")))[0],404)
            key.chmod(0o644)
            self.assertFalse(n["_cssb_verify"](1,stamp,sig,now))
    def test_fresh_real_transfer_three_routes_maya1_maya3_maya4(self):
        n=admin_module()
        now=int(time.time())
        with tempfile.TemporaryDirectory() as d:
            dualf,tranf=Path(d)/"dual.json",Path(d)/"transfer.json"
            n["_CSSB_DUAL"],n["_CSSB_TRANSFER"]=dualf,tranf
            for server in ("maya1","maya-s3","maya4"):
                dualf.write_text(json.dumps(dual(now,server)))
                tranf.write_text(json.dumps(transfer(now,server)))
                report=n["_cssb_report"](server,now)
                self.assertEqual(report["summary"],"healthy")
                self.assertEqual(set(report["paths"]),{"backhaul","mieru","haproxy"})
                self.assertEqual({v["transfer"] for v in report["paths"].values()},{"healthy"})
                self.assertNotIn("ip",str(report).lower())
                self.assertNotIn("93.184",str(report))
    def test_transfer_slow_timeout_incomplete_and_connection_only(self):
        n=admin_module()
        now=int(time.time())
        with tempfile.TemporaryDirectory() as d:
            dualf,tranf=Path(d)/"dual.json",Path(d)/"transfer.json"
            n["_CSSB_DUAL"],n["_CSSB_TRANSFER"]=dualf,tranf
            dualf.write_text(json.dumps(dual(now)))
            paths={"backhaul":metrics(17000,524288,0,"slow_completion"),
                  "mieru":metrics(25000,0,28,"timeout"),
                  "haproxy":metrics(5000,400000,0,"incomplete")}
            tranf.write_text(json.dumps(transfer(now,path=paths)))
            report=n["_cssb_report"]("maya1",now)
            self.assertEqual(report["paths"]["backhaul"]["state"],"slow")
            self.assertEqual(report["paths"]["mieru"]["state"],"timeout")
            self.assertEqual(report["paths"]["haproxy"]["state"],"incomplete")
            self.assertEqual(report["summary"],"disrupted")
            tranf.write_text(json.dumps(transfer(now-1900)))
            report=n["_cssb_report"]("maya1",now)
            self.assertEqual(report["paths"]["backhaul"]["state"],"connection_only")
            self.assertEqual(report["paths"]["haproxy"]["state"],"unknown")
            self.assertNotEqual(report["summary"],"healthy")
            dualf.write_text(json.dumps(dual(now-5000)))
            self.assertEqual(n["_cssb_report"]("maya1",now)["summary"],"unknown")
    def test_central_report_one_per_maya_across_many_subscription_checks(self):
        n=admin_module()
        observed=[]
        count=threading.Lock()
        def central(server,now=None):
            with count:observed.append(server)
            time.sleep(.06)
            return {"server":server,"summary":"healthy"}
        n["_cssb_report"]=central
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            results=list(pool.map(lambda i:n["_cssb_cached_report"]("maya1",1950000000),
                                  range(16)))
        self.assertEqual(observed,["maya1"])
        self.assertEqual(len(results),16)
        self.assertEqual(results[0]["summary"],"healthy")
        self.assertEqual(n["_cssb_cached_report"]("maya-s3",1950000000)["server"],"maya-s3")
        self.assertEqual(observed,["maya1","maya-s3"])

    def test_server_and_global_rate_limits(self):
        n=admin_module()
        now=1930000000
        self.assertTrue(all(n["_cssb_rate"](now,"maya1") for _ in range(30)))
        self.assertFalse(n["_cssb_rate"](now,"maya1"))
        self.assertTrue(n["_cssb_rate"](now,"maya-s3"))
        self.assertTrue(n["_cssb_rate"](now+61,"maya1"))
    def test_missing_signed_login_denies_accounts_and_status(self):
        n=portal_module()
        q=FakeRequest(phone=None)
        self.assertEqual(decode(n["_cssp_accounts_endpoint"](q))[0],403)
        post=FakeRequest(phone=None,headers={
            "origin":"https://usermanager.ir","content-type":"application/json",
            "x-customer-status-csrf":"csrf-09120000000"},
            payload={"subscription_id":1})
        self.assertEqual(decode(asyncio.run(n["_cssp_check_endpoint"](post)))[0],403)
        self.assertNotIn("customer_status_verified_phone_v1",CUSTOMER.read_text())

    def test_existing_signed_session_own_ids_only_and_reject_forged_server(self):
        n=portal_module()
        phone="09120000000"
        csrf="csrf-"+phone
        base={"origin":"https://usermanager.ir","content-type":"application/json",
              "x-customer-status-csrf":csrf}
        self.assertEqual(decode(n["_cssp_accounts_endpoint"](FakeRequest(phone=phone)))[1]["accounts"],
                         [{"id":1,"label":"اشتراک 1"},{"id":9,"label":"اشتراک 9"}])
        for payload in ({"subscription_id":3},{"subscription_id":4}):
            res=decode(asyncio.run(n["_cssp_check_endpoint"](
                FakeRequest(phone=phone,headers=base,payload=payload))))
            self.assertEqual(res[0],403)
        for payload in ({"subscription_id":1,"server":"maya4"},
                        {"subscription_id":True},{"server":"maya1"},
                        {"subscription_id":"1"}):
            res=decode(asyncio.run(n["_cssp_check_endpoint"](
                FakeRequest(phone=phone,headers=base,payload=payload))))
            self.assertEqual(res[0],400)
        q=FakeRequest(phone=phone,headers={**base,"origin":"https://example.com"},
                payload={"subscription_id":1})
        self.assertEqual(decode(asyncio.run(n["_cssp_check_endpoint"](q)))[0],403)
        q=FakeRequest(phone=phone,headers={**base,"x-customer-status-csrf":"invalid"},
                payload={"subscription_id":1})
        self.assertEqual(decode(asyncio.run(n["_cssp_check_endpoint"](q)))[0],403)
        q=FakeRequest(phone=phone,headers=base,payload={"subscription_id":1})
        n["_cssp_cached"]=lambda sid,now:{"server":"maya1","summary":"unknown"}
        self.assertEqual(decode(asyncio.run(n["_cssp_check_endpoint"](q)))[0],200)
    def test_pre_db_per_phone_and_global_rate_limit(self):
        n=portal_module()
        now=1940000000
        self.assertTrue(all(n["_cssp_gate_request"]("09120000000",now)
                            for _ in range(12)))
        self.assertFalse(n["_cssp_gate_request"]("09120000000",now))
        self.assertTrue(n["_cssp_gate_request"]("09350000000",now))
        self.assertTrue(n["_cssp_gate_request"]("09120000000",now+61))
        n=portal_module()
        bad=FakeRequest(phone="09120000000",headers={
             "origin":"https://usermanager.ir","content-type":"application/json",
             "content-length":"9"*7000,
             "x-customer-status-csrf":"csrf-09120000000"},
             payload={"subscription_id":1})
        status,_=decode(asyncio.run(n["_cssp_check_endpoint"](bad)))
        self.assertEqual(status,400)

    def test_single_flight_shared_cache_no_redundant_requests(self):
        n=portal_module()
        count=[0]
        lock=threading.Lock()
        def fetch(sid,now=None):
            with lock:count[0]+=1
            time.sleep(.08)
            return {"server":"maya1","summary":"healthy"}
        n["_cssp_fetch"]=fetch
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            out=list(pool.map(lambda x:n["_cssp_cached"](1,1900000000),range(12)))
        self.assertEqual(count[0],1)
        self.assertEqual({x["summary"] for x in out},{"healthy"})
    def test_live_server_section_markup_variants_preserve_original_exactly(self):
        live=(ROOT/"customer_portal/services_ui_v2.html").read_text(encoding="utf8")
        cases={
           "repository":live,
           "no_legacy_footer":live.replace(
               '<div class="sv-server-footer">',
               '<div class="sv-live-monitor-head">'),
           "reordered_classes":live.replace(
               'class="sv-box sv-server"',
               'class="sv-live sv-server sv-box"'),
           "single_quoted_classes":live.replace(
               'class="sv-box sv-server"',
               "class='sv-server sv-box'"),
        }
        for name,original in cases.items():
            with self.subTest(name=name):
                n=portal_module(template=original)
                updated=n["_SV2_HTML"]
                self.assertEqual(updated.count('id="sv-cstatus"'),1)
                self.assertEqual(updated.replace(n["_CSSP_CARD"],"",1).replace(
                                 n["_CSSP_STYLE"]+n["_CSSP_JS"],"",1),original)
                # The inserted test is inside the original server section.
                server_section=re.search(r'<section\\b[^>]*\\bsv-server\\b[^>]*>',updated)
                self.assertIsNotNone(server_section)
                start=server_section.start()
                end=updated.find("</section>",start)
                self.assertTrue(start < updated.index('id="sv-cstatus"') < end)
        with self.assertRaises(RuntimeError):
            portal_module(template=live.replace("sv-box sv-server","sv-box sv-absent"))
        with self.assertRaises(RuntimeError):
            portal_module(template=live.replace("</body>",
                '<section class="sv-server"></section></body>'))

    def test_no_customer_access_to_admin_routes_or_private_host_details(self):
        a=admin_module()
        p=portal_module()
        self.assertEqual([x.path for x in a["app"].router.routes],
              ["/internal/customer-server-status/v1"])
        self.assertEqual([x.path for x in p["app"].router.routes],
             ["/api/my-server-status/accounts","/api/my-server-status/check"])
        template=p["_SV2_HTML"]
        self.assertIn("تست وضعیت سرور من",template)
        self.assertIn("sv-cstatus-account",template)
        self.assertIn("@media(max-width:640px)",template)
        self.assertNotIn("/control-room/",template)
        self.assertNotIn("185.190.",template)
        self.assertNotIn("21001",template)
        self.assertNotIn("21002",template)
        self.assertNotIn("18080",template)
        self.assertNotIn("ssh",p["_CSSP_CARD"].lower())
        js=re.search(r'<script id="cssp-js">([\s\S]*?)</script>',template).group(1)
        process=subprocess.run(["node","--check"],input=js,text=True,
                               capture_output=True,timeout=10)
        self.assertEqual(process.returncode,0,process.stderr)
    def test_no_scheduled_or_active_probes_in_customer_module(self):
        for f in (ADMIN,CUSTOMER):
            s=f.read_text()
            for forbidden in ("subprocess.run(","socket.socket(","paramiko","--socks5",
                              "systemctl","SELECT * FROM payments","INSERT INTO","DELETE FROM"):
                self.assertNotIn(forbidden,s)
        self.assertIn("_v2_session_phone(request)",CUSTOMER.read_text())
        self.assertNotIn("customer_status_verified_phone_v1",CUSTOMER.read_text())
        self.assertNotIn("_pt_start(",CUSTOMER.read_text())

if __name__=="__main__":
    unittest.main(verbosity=2)
