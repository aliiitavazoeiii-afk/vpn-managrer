"""Offline tests for Caddy candidate generation and POST-only route."""
import importlib.util
from pathlib import Path
import unittest

p = Path(__file__).resolve().parents[1] / "audit_caddy_offline_candidate_v11.py"
spec = importlib.util.spec_from_file_location("offline_candidate_v11", p)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

SOURCE = (
    "other.invalid {\n"
    "  reverse_proxy other:8000\n"
    "}\n"
    "hesab.invalid {\n"
    "  handle {\n"
    "    reverse_proxy web:8000\n"
    "  }\n"
    "}\n"
)

class CandidateTests(unittest.TestCase):
    def test_inserts_at_one_site_only(self):
        proposed = mod.candidate(SOURCE)
        self.assertEqual(proposed.replace(mod.BLOCK, ""), SOURCE)
        self.assertIn("method POST", proposed)
        self.assertIn("path /api/control-room/v11/heartbeat", proposed)

    def test_duplicate_site_rejected(self):
        with self.assertRaises(ValueError):
            mod.candidate(SOURCE + "hesab.other.invalid {\n}\n")
        with self.assertRaises(ValueError):
            mod.candidate(mod.candidate(SOURCE))

    def test_matching_upstream_requires_post_and_exact_path(self):
        upstream = {"handler": "reverse_proxy",
                    "upstreams": [{"dial": mod.INTERNAL_UPSTREAM}]}
        wrong = {"apps": {"http": {"servers": {"srv": {"routes": [
            {"handle": [upstream]}]}}}}}
        self.assertFalse(mod.normalize_routes(wrong)[0])
        good = {"apps": {"http": {"servers": {"srv": {"routes": [
            {"match": [{"path": [mod.HEARTBEAT_PATH],
                        "method": ["POST"]}], "handle": [upstream]}
            ]}}}}}
        self.assertTrue(mod.normalize_routes(good)[0])

if __name__ == "__main__":
    unittest.main()
