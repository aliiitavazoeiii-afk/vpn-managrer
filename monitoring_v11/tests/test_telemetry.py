#!/usr/bin/env python3
"""Offline regression tests for signed telemetry V11. No network/database service."""
import copy
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile
import time
import unittest

BASE=Path(__file__).resolve().parent.parent


def imported(name,path):
    spec=importlib.util.spec_from_file_location(name,str(path))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

rc=imported("hesab_receiver_v11",BASE/"receiver.py")
agent=imported("hesab_agent_v11",BASE/"iran_agent.py")


def payload(sid="maya1",tm=1762171200,nonce=None,a=True,b=True):
    nonce=nonce or secrets.token_hex(16)
    lane=lambda available:{
        "available":available,"passed_probes":3 if available else 0,
        "total_probes":3,"latency_ms":230.0 if available else None,
        "consecutive_success":5 if available else 0,
        "consecutive_fail":0 if available else 4,
        "haproxy_before_action":"UP" if available else "MAINT",
        "tcp_https":"ok" if available else "degraded","udp":"unknown",
    }
    h=lambda status:{
        "status":status,"active_connections":5,"total_connections":100,
        "bytes_in":14000,"bytes_out":25000,"check_failures":0,
    }
    return {
        "schema":"hesab-tunnel-v11","server_id":sid,"sent_at":tm,"nonce":nonce,
        "tunnel_type":"dual-backhaul-mieru-ha",
        "system":{
            "cpu_pct":12.4,"ram_pct":33.2,"disk_pct":40.0,"uptime_s":500,
            "interface":"ens160","rx_bytes":123456,"tx_bytes":789012,
            "tcp443_listen":"listening",
        },
        "services":{"x-ui":"active","dual-ha-v2-health":"active"},
        "controller":{"state":"ok","age_s":3.0,
                      "paths":{"backhaul":lane(a),"mieru":lane(b)}},
        "haproxy":{"backhaul":h("UP"),"mieru":h("UP")},
        "foreign_ips":{"backhaul":"192.0.2.21","mieru":"198.51.100.32"},
        "quota":{"state":"unknown","remaining_gb":None},
        "xui_online":None,"vpn_end_to_end":"not_tested"
    }


def signed(p,key):
    raw=json.dumps(p,separators=(",",":")).encode()
    headers={"X-Hesab-Server":p["server_id"],
             "X-Hesab-Time":str(p["sent_at"]),
             "X-Hesab-Nonce":p["nonce"],
             "X-Hesab-Signature":"sha256="+hmac.new(key,
               str(p["sent_at"]).encode()+b"."+raw,hashlib.sha256).hexdigest()}
    return headers,raw


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file=Path(self.temp.name)/"a"/"data.sqlite3"
        rc.initialize(self.file)
        self.key=os.urandom(32)
        self.keys={"maya1":self.key}
        self.now=1762171200

    def call(self,p,headers=None,raw=None,now=None):
        original,document=signed(p,self.key)
        return rc.process_heartbeat(headers or original,
                                    document if raw is None else raw,
                                    self.keys,self.file,self.now if now is None else now)

    def test_good_hmac_and_no_duplicate(self):
        doc=payload(tm=self.now)
        self.assertEqual(self.call(doc)[0],202)
        # Early replay (even if expressed as rate limit) never inserts another sample.
        self.assertIn(self.call(doc)[0],(409,429))
        with sqlite3.connect(self.file) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM samples").fetchone()[0],1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM replays").fetchone()[0],1)

    def test_invalid_signatures_and_unknown_server(self):
        p=payload(tm=self.now)
        headers,raw=signed(p,self.key)
        invalid=dict(headers)
        invalid["X-Hesab-Signature"]="sha256="+"0"*64
        self.assertEqual(self.call(p,headers=invalid,raw=raw)[0],401)
        unknown=dict(headers)
        unknown["X-Hesab-Server"]="maya-nope"
        self.assertEqual(self.call(p,headers=unknown,raw=raw)[0],401)
        mutated=raw.replace(b"ens160",b"eth000")
        self.assertEqual(self.call(p,headers=headers,raw=mutated)[0],401)
        with sqlite3.connect(self.file) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM samples").fetchone()[0],0)

    def test_expired_timestamp(self):
        p=payload(tm=self.now-200)
        self.assertEqual(self.call(p)[0],401)
        self.assertEqual(self.call(payload(tm=self.now+200))[0],401)

    def test_wrong_shape_or_invented_quota(self):
        p=payload(tm=self.now)
        p["quota"]={"state":"verified","remaining_gb":999999}
        self.assertEqual(self.call(p)[0],422)
        p=payload(tm=self.now)
        p["controller"]["paths"]["mieru"]["udp"]="ok"
        self.assertEqual(self.call(p)[0],422)
        p=payload(tm=self.now)
        p["leaked_secret"]="must not store"
        self.assertEqual(self.call(p)[0],422)

    def test_hysteresis_events_alert_outbox_and_counter_reset(self):
        a=payload(tm=self.now,a=True,b=True)
        b=payload(tm=self.now+30,a=True,b=False)
        c=payload(tm=self.now+60,a=True,b=False)
        d=payload(tm=self.now+90,a=False,b=False)
        e=payload(tm=self.now+120,a=False,b=False)
        f=payload(tm=self.now+150,a=True,b=True)
        g=payload(tm=self.now+180,a=True,b=True)
        c["haproxy"]["backhaul"]["bytes_out"]=1000 # counter reset
        for item in (a,b,c,d,e,f,g):
            self.assertEqual(self.call(item,now=item["sent_at"])[0],202)
        with sqlite3.connect(self.file) as db:
            events=[row[0] for row in db.execute("SELECT kind FROM events ORDER BY id")]
            self.assertEqual(events.count("degraded"),1)
            self.assertEqual(events.count("both_unavailable"),1)
            self.assertEqual(events.count("counter_reset"),1)
            self.assertEqual(events.count("healthy"),1)
            self.assertEqual(db.execute("SELECT effective_state FROM server_state WHERE server_id='maya1'").fetchone()[0],"healthy")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM alerts WHERE state='pending_review'").fetchone()[0],3)
            self.assertEqual(db.execute("SELECT MAX(epoch) FROM counters WHERE server_id='maya1' AND lane='backhaul'").fetchone()[0],1)

    def test_stale_is_not_claimed_healthy(self):
        p=payload(tm=self.now)
        self.assertEqual(self.call(p)[0],202)
        with sqlite3.connect(self.file) as db:
            rc.mark_stale(db,now=self.now+121)
            self.assertEqual(db.execute("SELECT effective_state FROM server_state WHERE server_id='maya1'").fetchone()[0],"stale")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events WHERE kind='stale'").fetchone()[0],1)
            rc.mark_stale(db,now=self.now+160)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events WHERE kind='stale'").fetchone()[0],1)

    def test_receiver_docker_peer_policy_is_private_and_explicit(self):
        self.assertTrue(rc.allowed_proxy_peer("127.0.0.1","loopback"))
        self.assertFalse(rc.allowed_proxy_peer("172.20.0.4","loopback"))
        self.assertTrue(rc.allowed_proxy_peer("172.20.0.4","docker-internal"))
        self.assertTrue(rc.allowed_proxy_peer("10.12.0.4","docker-internal"))
        self.assertFalse(rc.allowed_proxy_peer("8.8.8.8","docker-internal"))
        self.assertFalse(rc.allowed_proxy_peer("127.0.0.1","docker-internal"))
        self.assertFalse(rc.allowed_proxy_peer("198.51.100.4","docker-internal"))
        self.assertFalse(rc.allowed_proxy_peer("invalid","docker-internal"))
        self.assertFalse(rc.allowed_proxy_peer("172.20.0.4","no-such-mode"))

    def test_docker_service_never_publishes_management_port(self):
        compose=(BASE/"docker-compose.telemetry-v11.yml").read_text(encoding="utf8")
        self.assertIn("HESAB_RECEIVER_DEPLOYMENT: docker-internal",compose)
        self.assertNotIn("\n    ports:",compose)
        self.assertNotIn("network_mode: host",compose)
        self.assertIn("read_only: true",compose)
        self.assertIn("cap_drop:",compose)
        self.assertIn("mem_limit:",compose)
        self.assertIn("telemetry_v11:rw",compose)
        self.assertNotIn("privileged: true",compose)
    def test_distinct_servers_have_distinct_credentials(self):
        p=payload(tm=self.now,sid="maya-s3")
        self.assertEqual(self.call(p)[0],401)

    def test_no_finance_tables(self):
        with sqlite3.connect(self.file) as db:
            tables={name for (name,) in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"events","alerts","replays","server_state","samples","counters"}.issubset(tables))
        self.assertFalse({"subscriptions","payments","audit_events"} & tables)


class AgentTests(unittest.TestCase):
    def test_real_controller_schema_mapped(self):
        now=time.time()
        h={"updated_utc":__import__("datetime").datetime.fromtimestamp(now,
            __import__("datetime").timezone.utc).isoformat(),
           "paths":{"backhaul":{
             "available":True,"passed_probes":3,"total_probes":3,
             "latency_average_s":0.225,"consecutive_success":7,"consecutive_fail":0,
             "haproxy_before_action":"UP"
           },"mieru":{
             "available":False,"passed_probes":0,"total_probes":3,
             "latency_average_s":None,"consecutive_success":0,"consecutive_fail":4,
             "haproxy_before_action":"MAINT"
           }}}
        prev=agent.HEALTH
        with tempfile.TemporaryDirectory() as t:
            filename=Path(t)/"health.json"
            filename.write_text(json.dumps(h))
            agent.HEALTH=filename
            try:
                result=agent.controller()
            finally:
                agent.HEALTH=prev
        self.assertEqual(result["state"],"ok")
        self.assertEqual(result["paths"]["backhaul"]["latency_ms"],225.0)
        self.assertEqual(result["paths"]["backhaul"]["tcp_https"],"ok")
        self.assertEqual(result["paths"]["mieru"]["tcp_https"],"degraded")
        self.assertEqual(result["paths"]["mieru"]["udp"],"unknown")

    def test_agent_never_probes_vpn_or_opens_private_tunnel_bundles(self):
        import unittest.mock as mock
        src=(BASE/"iran_agent.py").read_text(encoding="utf8")
        for forbidden in ("socket.create_connection", "/etc/dual-ha/",
                          "--socks5", "subprocess.run(['curl'",
                          "systemctl\", \"restart", "haproxy set server"):
            self.assertNotIn(forbidden,src)
        with mock.patch.object(agent.socket,"create_connection",side_effect=AssertionError("network probe attempted")):
            host=agent.sysinfo("lo")
        self.assertIn(host["tcp443_listen"],("listening","not_listening","unknown"))
        self.assertNotIn("tcp443_loopback",host)

    def test_heartbeat_from_agent_is_single_shot_and_not_vpn_health_test(self):
        import unittest.mock as mock
        with (mock.patch.object(agent,"controller",return_value={"state":"unavailable","paths":{},"age_s":None}),
              mock.patch.object(agent,"haproxy_stats",return_value={}),
              mock.patch.object(agent,"service_state",return_value="unknown"),
              mock.patch.object(agent,"sysinfo",return_value={"tcp443_listen":"unknown"})):
            p=agent.build_snapshot("maya1","ens160",{})
        self.assertEqual(p["tunnel_type"],"unidentified")
        self.assertEqual(p["vpn_end_to_end"],"not_tested")
        self.assertEqual(p["foreign_ips"],{})
        self.assertEqual(p["quota"]["state"],"unknown")
    def test_missing_health_cannot_be_healthy(self):
        prev=agent.HEALTH
        agent.HEALTH=Path("/nonexistent/hesab-v11-test-health.json")
        try:
            result=agent.controller()
        finally:
            agent.HEALTH=prev
        self.assertNotEqual(result["state"],"ok")


if __name__=="__main__":
    unittest.main(verbosity=2)
