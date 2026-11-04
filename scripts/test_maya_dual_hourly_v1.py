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

class TestDualHourly(unittest.TestCase):
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
