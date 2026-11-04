#!/usr/bin/env python3
"""Offline regression suite: Maya3 2026-11-04 and conservative passive quality."""
import importlib.util
import json
from pathlib import Path
import types
import unittest
from jinja2 import Environment

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/maya_dual_passive_quality_v1.py"
PATCH=ROOT/"patches/control_room_passive_quality_v1.py"
FIXTURE=ROOT/"fixtures/maya3_mieru_degraded_20261104.json"
spec=importlib.util.spec_from_file_location("passive_quality",SCRIPT)
pq=importlib.util.module_from_spec(spec)
spec.loader.exec_module(pq)

def sample(at, ip="8.8.8.8", counters=None):
    def path():
        item={"ip":ip,"state":"healthy","https_passed":3,"https_total":3,
              "https_avg_ms":245}
        if counters:
            item["haproxy_counters"]=dict(counters)
        return item
    servers={sid:{"state":"ok","paths":{
      "backhaul":path(),"mieru":path()}} for sid in pq.SERVERS}
    return {"format":"HESAB_DUAL_HOURLY_V1","collected_at":at,"servers":servers}

def counters(epoch="run-1",**kwargs):
    result={"source":"haproxy_stats_readonly","scope":"backend",
       "epoch":epoch,
       "bytes_in":1000000,"bytes_out":3000000,"sessions_total":100,
       "sessions_current":200,"connection_errors_total":0,
       "response_errors_total":0}
    result.update(kwargs)
    return result

class PassiveQualityTests(unittest.TestCase):
    def test_original_v1_never_invents_metrics(self):
        t=1793782900
        data=pq.validate_snapshot(sample(t),t+1)
        result=pq.summarise([data],t+1)
        self.assertFalse(result["alerts"])
        for sid in pq.SERVERS:
            for role in pq.ROLES:
                item=result["servers"][sid]["paths"][role]
                self.assertEqual(item["quality"]["state"],"not_measured")
                self.assertIsNone(item["latest_counters"])
                self.assertIsNone(item["last_transfer_test"])
                self.assertEqual(item["trend"],[])
    def test_delta_from_true_monotonic_counters(self):
        old=counters()
        new=counters(bytes_in=1250000,bytes_out=4000000,
                     sessions_total=193,sessions_current=201,
                     connection_errors_total=0,response_errors_total=0)
        d=pq.deltas(old,new,20)
        self.assertEqual(d["new_connections"],93)
        self.assertEqual(d["bytes_out_delta"],1000000)
        self.assertEqual(d["bytes_out_per_s"],50000)
        self.assertEqual(d["active_connections"],201)
        self.assertEqual(d["connection_errors_delta"],0)
    def test_counter_reset_epoch_or_gap_never_generates_negative_rate(self):
        a=counters()
        self.assertEqual(pq.deltas(a,counters(epoch="another"),20)["state"],"reset_or_gap")
        self.assertEqual(pq.deltas(a,counters(bytes_out=1),20)["state"],"counter_reset")
        self.assertEqual(pq.deltas(a,counters(bytes_out=5000000),5000)["state"],"reset_or_gap")
        self.assertIsNone(pq.deltas(None,a,20))
    def test_no_suspect_from_one_imbalanced_window(self):
        f=json.loads(FIXTURE.read_text())
        a=f["backend_stats_20_seconds"]["backhaul"]
        b=f["backend_stats_20_seconds"]["mieru"]
        def backend(item):
            x=counters()
            y=counters(bytes_out=x["bytes_out"]+item["bytes_out_delta"],
              sessions_total=x["sessions_total"]+item["new_connections"],
              sessions_current=item["active_connections"])
            return pq.deltas(x,y,20)
        back=backend(a);mieru=backend(b)
        self.assertEqual(back["new_connections"],93)
        self.assertEqual(mieru["new_connections"],84)
        self.assertEqual(back["bytes_out_delta"],11310000)
        self.assertEqual(mieru["bytes_out_delta"],350000)
        self.assertEqual(pq.quality_label([mieru])["state"],"not_measured")
    def test_suspect_needs_three_consecutive_active_low_windows(self):
        baseline=[{"state":"ok","bytes_out_per_s":1000000,
                    "new_connections":90,"active_connections":200} for _ in range(7)]
        low=[{"state":"ok","bytes_out_per_s":40000,
             "new_connections":80,"active_connections":200} for _ in range(3)]
        self.assertEqual(pq.quality_label(baseline+low)["state"],"suspected_degradation")
        self.assertNotEqual(pq.quality_label(baseline+low[:2])["state"],"suspected_degradation")
        self.assertNotEqual(pq.quality_label(baseline+[
            {**x,"new_connections":0} for x in low])["state"],"suspected_degradation")
    def test_foreign_ip_replacement_breaks_counter_lineage(self):
        t=1793782900
        a=pq.validate_snapshot(sample(t,ip="8.8.8.8",counters=counters()),t+1)
        b=pq.validate_snapshot(sample(t+60,ip="9.9.9.9",
            counters=counters(bytes_out=50000000,sessions_total=300)),t+61)
        result=pq.summarise([a,b],t+62)
        for sid in pq.SERVERS:
            for role in pq.ROLES:
                item=result["servers"][sid]["paths"][role]
                self.assertEqual(item["quality"]["state"],"not_measured")
                self.assertIsNone(item["latest_counters"])
                self.assertEqual(item["trend"][-1]["bytes_out_per_s"],None)

    def test_maya3_incident_http200_is_not_transfer_success(self):
        f=json.loads(FIXTURE.read_text())
        results={item["path"]:pq.transfer_test(item) for item in f["transfer_tests"]}
        self.assertEqual(results["backhaul"]["state"],"completed")
        self.assertEqual(results["mieru"]["state"],"failed")
        self.assertEqual(results["mieru"]["reason"],"timeout")
        self.assertEqual(results["mieru"]["received_bytes"],30118)
        self.assertEqual(results["mieru"]["http_status"],200)
        self.assertEqual(results["mieru"]["exit_code"],28)
        self.assertEqual(results["haproxy"]["state"],"failed")
        self.assertEqual(results["mieru_replacement"]["state"],"completed")
        self.assertEqual(pq.quality_label([],results["mieru"])["state"],
                         "confirmed_transfer_test_failure")
    def test_stale_never_healthy_transfer(self):
        t=1793782900
        data=pq.validate_snapshot(sample(t),t+1)
        result=pq.summarise([data],t+5000)
        self.assertTrue(result["source_stale"])
        for sid in pq.SERVERS:
            for role in pq.ROLES:
                p=result["servers"][sid]["paths"][role]
                self.assertEqual(p["health"],"stale")
                self.assertEqual(p["quality"]["state"],"stale")
    def test_reject_unproven_counters(self):
        self.assertIsNone(pq.validate_counters({"bytes_out":1000}))
        bad=counters();bad["bytes_out"]=-1
        self.assertIsNone(pq.validate_counters(bad))
        bad=counters();bad["source"]="unknown"
        self.assertIsNone(pq.validate_counters(bad))
        self.assertIsNotNone(pq.validate_counters(counters()))
    def test_new_addon_template_parses_and_is_after_dom(self):
        class App:
            def __init__(self):
                self.router=types.SimpleNamespace(routes=[])
            def add_api_route(self,p,fn,methods):
                self.router.routes.append(types.SimpleNamespace(path=p,endpoint=fn))
        tpl='''{% block content %}
<style id="t10-compact-css"></style>
<div id="dh1-root">
<div id="dh1-grid" class="dh1-grid"></div>
</section>
<script id="dh1-script">window.__HESAB_DUAL_REFRESH_NOW=function(){};</script>
<button id="dm2-refresh"></button>
{% endblock %}'''
        page={"control_room.html":tpl}
        ns={"app":App(),"TEMPLATES":page,"env":Environment(),
            "_dh1_auth":lambda request:False}
        exec(compile(PATCH.read_text(),str(PATCH),"exec"),ns)
        new=page["control_room.html"]
        Environment().parse(new)
        self.assertEqual(new.count('id="pq-root"'),1)
        self.assertLess(new.index('id="pq-cards"'),new.index('id="pq-js"'))
        self.assertEqual([r.path for r in ns["app"].router.routes],
                         ["/control-room/dual-quality/status"])
    def test_no_active_probes_or_remote_permissions(self):
        source=SCRIPT.read_text()
        patch=PATCH.read_text()
        for banned in ("subprocess","socket","curl","ssh","dual health",
                       "systemctl restart","haproxy -c"):
            self.assertNotIn(banned,source.split("def run():")[1])
        self.assertIn("_dh1_auth(request)",patch)
        self.assertNotIn("subprocess.run",patch)
if __name__=="__main__":
    unittest.main(verbosity=2)
