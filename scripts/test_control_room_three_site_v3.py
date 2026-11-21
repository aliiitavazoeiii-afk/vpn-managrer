#!/usr/bin/env python3
"""Offline tests for three-site Control Room V3 parser/UI with Maya4 legacy."""
import ast
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]

def load(name,filename):
    spec=importlib.util.spec_from_file_location(name,ROOT/"scripts"/filename)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module)
    return module

c=load("three_site_collector","maya_dual_hourly_collect_v1.py")
v2=load("maya3_role_patch","patch_maya3_dual_backhaul_ui_v1.py")
v3=load("three_site_ui_patch","patch_control_room_three_site_v3.py")

def status(role="MAYA1",first=("OK","OK","OK"),second=("OK","OK","OK"),age=7):
    if role=="MAYA1":
        ip="94.184.4.38"; ports=(21101,21102); egress=("82.152.132.159","152.237.230.77")
    else:
        ip="185.215.230.221"; ports=(21001,21002); egress=("152.237.230.140","82.152.132.112")
    def lane(index,fields):
        passed=fields.count("OK")
        return (f"  BACKHAUL{index+1} foreign={egress[index]}  SOCKS={ports[index]} UP\n"
                f"        active=400 total=940123 weight=1 | HTTPS={passed}/3 | BULK=not measured | bytes=? speed=? B/s\n"
                f"        CHECKS: Google={fields[0]} Cloudflare={fields[1]} Apple={fields[2]}\n")
    return (f"DUAL BACKHAUL | {role}\nIRAN: {ip} | REALITY/x-ui: active\n"
            +lane(0,first)+lane(1,second)
            +f"  HTTPS targets: Google | Cloudflare | Apple; interval=600s\n  Controller cache age: {age}s\n")

class Tests(unittest.TestCase):
    def test_maya1_and_maya3_3_sites(self):
        for node in ("MAYA1","MAYA3"):
            r=c.parse_dual_status(status(node,first=("OK","FAIL","OK")),sampled_at=123)
            self.assertEqual(r["health_interval_s"],600)
            self.assertEqual(r["state"],"ok")
            self.assertEqual(r["mode"],"dual_backhaul")
            self.assertEqual(r["paths"]["backhaul"]["state"],"healthy")
            self.assertTrue(r["paths"]["backhaul"]["site_warning"])
            self.assertEqual(r["paths"]["backhaul"]["https_sites"],
                             {"google":True,"cloudflare":False,"apple":True})
            self.assertFalse(r["paths"]["mieru"]["site_warning"])
            self.assertEqual(r["paths"]["mieru"]["https_passed"],3)

    def test_2_failed_destinations_unknown_even_if_live_up(self):
        x=c.parse_dual_status(status(first=("FAIL","FAIL","OK")))
        self.assertEqual(x["paths"]["backhaul"]["state"],"unknown")
        self.assertEqual(x["paths"]["backhaul"]["https_passed"],1)
        self.assertTrue(x["paths"]["backhaul"]["site_warning"])

    def test_v3_strict_validation_and_staleness(self):
        good=status(age=780)
        self.assertEqual(c.parse_dual_status(good)["state"],"ok")
        self.assertEqual(c.parse_dual_status(status(age=781))["state"],"stale")
        bad=good.replace("Google=OK Cloudflare=OK Apple=OK",
                         "Google=OK Cloudflare=OK Apple=FAIL",1)
        with self.assertRaises(ValueError):
            c.parse_dual_status(bad)
        with self.assertRaises(ValueError):
            c.parse_dual_status(good.replace("CHECKS:", "TESTS:",1))
        with self.assertRaises(ValueError):
            c.parse_dual_status(good+"\x1b[31m")

    def test_legacy_remains_supported(self):
        s=("BACKHAUL 8.8.8.8  local SOCKS 127.0.0.1:21001\n"
           " HEALTHY | https=3/3 avg=0.241s\n"
           "MIERU 1.1.1.1  local SOCKS 127.0.0.1:21002\n"
           " HEALTHY | https=3/3 avg=0.362s\n"
           "health.json age: 3s\n")
        row=c.parse_dual_status(s)
        self.assertEqual(row["mode"],"legacy")
        self.assertEqual(row["paths"]["backhaul"]["https_avg_ms"],241)
        self.assertIsNone(row["paths"]["backhaul"]["https_sites"])

    def test_transform_exact_reviewed_overlay_and_preserves_auth(self):
        base=(ROOT/"patches"/"control_room_dual_hourly_v1.py").read_text()
        with_maya3=v2.transform(base)
        result=v3.transform(with_maya3)
        ast.parse(result)
        self.assertIn(v3.MARK,result)
        self.assertIn('app.add_api_route("/control-room/dual-hourly/status"',result)
        self.assertIn('"x-control-csrf"',result)
        self.assertIn('{"google","cloudflare","apple"}',result)
        self.assertIn('"سنجش مسیرها: هر ۱۰ دقیقه',result)
        self.assertIn('site_warning',result)
        self.assertIn('observed_age+age>1500',result)
        self.assertIn('const title=item.mode==="dual_backhaul"',result)
        self.assertNotIn('set server dual_egress',result)
        with self.assertRaises(ValueError):
            v3.transform(result)

    def test_ui_literal_js_syntax_with_node_optional(self):
        import shutil,subprocess,tempfile
        base=(ROOT/"patches"/"control_room_dual_hourly_v1.py").read_text()
        obj=ast.parse(v3.transform(v2.transform(base)))
        constants={}
        for stmt in ast.walk(obj):
            if isinstance(stmt,ast.Assign) and len(stmt.targets)==1 and isinstance(stmt.targets[0],ast.Name):
                if stmt.targets[0].id in ("_DH1_HTML","_DH1_JS"):
                    constants[stmt.targets[0].id]=ast.literal_eval(stmt.value)
        self.assertEqual(set(constants),{"_DH1_HTML","_DH1_JS"})
        self.assertIn("Google",constants["_DH1_JS"])
        self.assertIn("Cloudflare",constants["_DH1_JS"])
        self.assertIn("Apple",constants["_DH1_JS"])
        self.assertIn('_dh1_auth(request)',result)
        if shutil.which("node"):
            with tempfile.TemporaryDirectory() as td:
                f=Path(td)/"card.js"
                js=constants["_DH1_JS"].replace("<script id=\"dh1-script\">","").replace("</script>","")
                f.write_text(js.replace('{{ ctrl_csrf }}','synthetic'),encoding="utf8")
                subprocess.run(["node","--check",str(f)],check=True,capture_output=True)

if __name__=="__main__":
    unittest.main(verbosity=2)
