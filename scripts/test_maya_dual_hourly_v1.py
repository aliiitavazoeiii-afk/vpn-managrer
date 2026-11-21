#!/usr/bin/env python3
"""Offline checks for the simple two-lane hourly status view. No SSH or Docker."""
import importlib.util
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "maya_dual_hourly_collect_v1.py"
spec = importlib.util.spec_from_file_location("dual_hourly", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def sample(age="4", a="HEALTHY", b="HEALTHY", ip1="8.8.8.8", ip2="1.1.1.1"):
    return f"""
  DUAL HA  |  Iran Xray / 2 independent foreign egress paths
  -----------------------------------------------------------------
  IRAN    192.0.2.1  | REALITY 443: active
  BACKHAUL         {ip1}  local SOCKS 127.0.0.1:21001
           {a} | https=3/3 avg=0.235s
  MIERU            {ip2}  local SOCKS 127.0.0.1:21002
           {b} | https=2/3 avg=0.850s
  GATEWAY 127.0.0.1:18080 | HAProxy=active | controller=active
  health.json age: {age}s
"""

def modern_sample(age="5", first="UP", second="UP", bulk1="True", bulk2="True"):
    return f"""
  DUAL BACKHAUL | MAYA3 | unchanged HAProxy leastconn
  ----------------------------------------------------------------
  IRAN: 185.215.230.221 | REALITY/x-ui: active
  BACKHAUL1 foreign=152.237.230.140  SOCKS=21001 {first}
        active=301 total=5499920 weight=1 | HTTPS=3/3 | BULK={bulk1} | bytes=262144 speed=185000 B/s
  BACKHAUL2 foreign=82.152.132.112   SOCKS=21002 {second}
        active=351 total=5329262 weight=1 | HTTPS=3/3 | BULK={bulk2} | bytes=262144 speed=310000 B/s
  Controller cache age: {age}s
"""

class TestDualHourly(unittest.TestCase):
    def test_maya3_dual_backhaul_new_layout_and_ip(self):
        row=mod.parse_dual_status(modern_sample(),sampled_at=42)
        self.assertEqual(row["mode"],"dual_backhaul")
        self.assertEqual(row["state"],"ok")
        self.assertEqual(row["paths"]["backhaul"]["ip"],"152.237.230.140")
        self.assertEqual(row["paths"]["mieru"]["ip"],"82.152.132.112")
        self.assertEqual(row["paths"]["backhaul"]["state"],"healthy")
        self.assertEqual(row["paths"]["mieru"]["state"],"healthy")
        self.assertIsNone(row["paths"]["backhaul"]["https_avg_ms"])
        self.assertNotIn("filtered",str(row))

    def test_maya1_new_socks_ports_and_legacy_compatibility(self):
        text=modern_sample()
        text=text.replace("152.237.230.140  SOCKS=21001",
                          "82.152.132.159  SOCKS=21101")
        text=text.replace("82.152.132.112   SOCKS=21002",
                          "152.237.230.77   SOCKS=21102")
        row=mod.parse_dual_status(text)
        self.assertEqual(row["mode"],"dual_backhaul")
        self.assertEqual(row["state"],"ok")
        self.assertEqual(row["paths"]["backhaul"]["ip"],"82.152.132.159")
        self.assertEqual(row["paths"]["mieru"]["ip"],"152.237.230.77")
        self.assertEqual(row["paths"]["mieru"]["state"],"healthy")
        with self.assertRaises(ValueError):
            mod.parse_dual_status(text.replace("82.152.132.159","8.8.8.8"))
        self.assertEqual(mod.parse_dual_status(sample())["mode"],"legacy")

    def test_exact_maya1_new_helper_status_and_green_gate(self):
        # Exact field layout emitted by /usr/local/bin/dual on migrated Maya1.
        text="""  DUAL BACKHAUL | MAYA1 | HAProxy leastconn
  ---------------------------------------------------------------
  IRAN: 94.184.4.38 | REALITY/x-ui: active
  BACKHAUL1 foreign=82.152.132.159  SOCKS=21101 UP
        active=356 total=919 weight=1 | HTTPS=3/3 | BULK=True | bytes=1048576 speed=172896 B/s
  BACKHAUL2 foreign=152.237.230.77  SOCKS=21102 UP
        active=357 total=921 weight=1 | HTTPS=3/3 | BULK=True | bytes=1048576 speed=139024 B/s
  Controller cache age: 7s
  Historical backend name 'mieru' actually carries BACKHAUL2.
"""
        result=mod.parse_dual_status(text,sampled_at=123)
        self.assertEqual(result["mode"],"dual_backhaul")
        self.assertEqual(result["state"],"ok")
        self.assertEqual(result["sampled_at"],123)
        self.assertEqual(result["paths"]["backhaul"]["ip"],"82.152.132.159")
        self.assertEqual(result["paths"]["mieru"]["ip"],"152.237.230.77")
        self.assertTrue(all(x["state"]=="healthy" for x in result["paths"].values()))
        self.assertEqual(result["paths"]["backhaul"]["https_passed"],3)
        self.assertEqual(result["paths"]["mieru"]["https_total"],3)
        self.assertEqual(mod.parse_dual_status(text.replace(
            "BACKHAUL2 foreign=152.237.230.77  SOCKS=21102 UP",
            "BACKHAUL2 foreign=152.237.230.77  SOCKS=21102 UNKNOWN")
        )["paths"]["mieru"]["state"],"unknown")
        self.assertEqual(mod.parse_dual_status(text.replace(
            "Controller cache age: 7s","Controller cache age: 60s")
        )["paths"]["backhaul"]["state"],"stale")

    def test_maya3_observed_down_and_unmeasured_bulk(self):
        row=mod.parse_dual_status(modern_sample(first="DOWN",bulk2="False"))
        self.assertEqual(row["paths"]["backhaul"]["state"],"down")
        # BULK=False is a speed/quality warning, not a broken live HAProxy route.
        self.assertEqual(row["paths"]["mieru"]["state"],"healthy")
        self.assertEqual(mod.parse_dual_status(modern_sample(first="DISABLED"))["paths"]["backhaul"]["state"],"unknown")
        self.assertEqual(mod.parse_dual_status(modern_sample(bulk1="False",bulk2="False"))["paths"]["backhaul"]["state"],"healthy")

    def test_ten_min_three_site_health_is_fresh_not_stale(self):
        output=modern_sample(age="652",bulk1="False",bulk2="False")
        output=output.replace("  Controller cache age:",
                              "  HTTPS targets: Google | Cloudflare | Apple; interval=600s\n  Controller cache age:")
        row=mod.parse_dual_status(output)
        self.assertEqual(row["state"],"ok")
        self.assertEqual(row["health_interval_s"],600)
        self.assertEqual(row["paths"]["backhaul"]["state"],"healthy")
        self.assertEqual(row["paths"]["mieru"]["state"],"healthy")
        too_old=mod.parse_dual_status(output.replace("age: 652s","age: 781s"))
        self.assertEqual(too_old["state"],"stale")
        self.assertEqual(too_old["paths"]["mieru"]["state"],"stale")
        legacy=mod.parse_dual_status(modern_sample(age="90"))
        self.assertEqual(legacy["health_interval_s"],30)
        self.assertEqual(legacy["state"],"stale")

    def test_maya3_stale_and_ansi_rejected(self):
        row=mod.parse_dual_status(modern_sample(age="60"))
        self.assertEqual(row["state"],"stale")
        self.assertTrue(all(x["state"]=="stale" for x in row["paths"].values()))
        with self.assertRaises(ValueError):
            mod.parse_dual_status(modern_sample()+"\x1b[31m")

    def test_maya3_overlay_scope_and_compatibility(self):
        import sys
        patch=ROOT/"scripts"/"patch_maya3_dual_backhaul_ui_v1.py"
        spec=importlib.util.spec_from_file_location("maya3_ui",patch)
        obj=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(obj)
        original=(ROOT/"patches"/"control_room_dual_hourly_v1.py").read_text()
        revised=obj.transform(original)
        self.assertIn('item.mode==="dual_backhaul"',revised)
        self.assertIn('role==="backhaul"?"Backhaul":"Mieru"',revised)
        self.assertIn('Backhaul 2',revised)
        self.assertIn('"mode": "dual_backhaul"',revised)
        self.assertIn('"/control-room/dual-hourly/status"',revised)
        with self.assertRaises(ValueError):
            obj.transform(revised)

    def test_healthy_and_https_latency(self):
        result = mod.parse_dual_status(sample(), sampled_at=42)
        self.assertEqual(result["state"], "ok")
        self.assertEqual(result["paths"]["backhaul"]["state"], "healthy")
        self.assertEqual(result["paths"]["backhaul"]["ip"], "8.8.8.8")
        self.assertEqual(result["paths"]["backhaul"]["https_avg_ms"], 235)
        self.assertEqual(result["paths"]["mieru"]["https_avg_ms"], 850)
        self.assertEqual(result["paths"]["mieru"]["https_passed"], 2)

    def test_failure_not_inferred_as_filtering(self):
        text = sample(b="DOWN / health checks failed (cause unverified)")
        result = mod.parse_dual_status(text)
        self.assertEqual(result["paths"]["mieru"]["state"], "down")
        self.assertNotIn("filtered", str(result))

    def test_stale_cannot_be_green(self):
        result = mod.parse_dual_status(sample(age="999"))
        self.assertEqual(result["state"], "stale")
        for item in result["paths"].values():
            self.assertEqual(item["state"], "stale")
            self.assertIsNone(item["https_avg_ms"])

    def test_unknown_status_parses_without_green(self):
        text = sample(a="UNKNOWN (stale/missing controller data)", age="60")
        result = mod.parse_dual_status(text)
        self.assertEqual(result["paths"]["backhaul"]["state"], "stale")

    def test_malformed_or_partial_output_blocks(self):
        with self.assertRaises(ValueError):
            mod.parse_dual_status("BACKHAUL 8.8.8.8\n  HEALTHY")
        with self.assertRaises(ValueError):
            mod.parse_dual_status(sample().replace("21002", "21999"))
        with self.assertRaises(ValueError):
            mod.parse_dual_status(sample() + "\x1b[31mred\x1b[0m")

    def test_no_unreviewed_remote_actions(self):
        data = SOURCE.read_text()
        self.assertIn("/usr/local/bin/dual status", data)
        self.assertIn("StrictHostKeyChecking=yes", data)
        self.assertIn("BatchMode=yes", data)
        self.assertNotIn("dual health", data)
        for verb in ("dual replace", "systemctl restart", "docker compose down",
                     "DELETE FROM payments", "UPDATE subscriptions"):
            self.assertNotIn(verb, data)

    def test_jinja_template_syntax_with_responsive_css(self):
        import ast
        from jinja2 import Environment
        code = (ROOT / "patches" / "control_room_dual_hourly_v1.py").read_text()
        tree = ast.parse(code)
        consts = {}
        for stmt in tree.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                target = stmt.targets[0]
                if isinstance(target, ast.Name) and target.id in ("_DH1_HTML", "_DH1_JS"):
                    consts[target.id] = ast.literal_eval(stmt.value)
        self.assertEqual(set(consts), {"_DH1_HTML", "_DH1_JS"})
        page = ('{% block content %}<style id="t10-compact-css"></style>'
                '<div id="c2-cards" class="c2-cards"></div>{% endblock %}')
        page = page.replace('<div id="c2-cards" class="c2-cards"></div>',
                            '<div id="c2-cards" class="c2-cards"></div>' + consts["_DH1_HTML"])
        page = page.replace('{% endblock %}', consts["_DH1_JS"] + '{% endblock %}')
        Environment().parse(page)
        self.assertNotIn("{#", consts["_DH1_HTML"])
        self.assertIn("dh1-grid", page)
        self.assertLess(page.index('id="dh1-grid"'), page.index('id="dh1-script"'))
        self.assertIn("_ANCHOR + _DH1_HTML + _DH1_JS", code)
        self.assertNotIn('_DH1_TEMPLATE.replace("{% endblock %}"', code)

    def test_control_room_is_read_only(self):
        ui = (ROOT / "patches" / "control_room_dual_hourly_v1.py").read_text()
        self.assertIn("/control-room/dual-hourly/status", ui)
        self.assertIn("x-control-csrf", ui)
        self.assertIn("Cache-Control", ui)
        self.assertIn("75 minutes", ui)
        for unsafe in ("app.add_api_route(\"/control-room/maya-live/toggle\"",
                       "set server dual_egress", "subprocess.run(", "docker compose"):
            self.assertNotIn(unsafe, ui)

if __name__ == "__main__":
    unittest.main(verbosity=2)
