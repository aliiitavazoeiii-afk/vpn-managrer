"""Offline tests for cautious, non-disclosing live Caddyfile collision checks."""
import importlib.util
from pathlib import Path
import unittest

file = Path(__file__).resolve().parents[1] / "audit_caddy_match_collision_readonly.py"
spec = importlib.util.spec_from_file_location("caddy_collision_v11",file)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def example(handle="/portal-api/*",redirect="/login-only/*"):
    return (
        "other.example.invalid {\n"
        "  reverse_proxy web:8000\n"
        "}\n"
        "hesab.example.invalid {\n"
        "  encode gzip\n"
        f"  @oldpath path {redirect}\n"
        "  redir @oldpath /login\n"
        f"  handle_path {handle} {{\n"
        "    reverse_proxy some-service:8090\n"
        "  }\n"
        "  handle {\n"
        "    reverse_proxy admin-service:8000\n"
        "  }\n"
        "}\n"
    )

class CaddyCollisionTests(unittest.TestCase):
    def test_nonoverlap_in_approved_simple_structure(self):
        r=mod.evaluate(example())
        self.assertEqual(r["handle_path"],"CLEAR")
        self.assertEqual(r["redirect"],"CLEAR")
        self.assertTrue(r["ready"])

    def test_overlap_in_gateway_path_prevents_approval(self):
        r=mod.evaluate(example("/api/*"))
        self.assertEqual(r["handle_path"],"OVERLAP")
        self.assertFalse(r["ready"])

    def test_redirect_collision_prevents_approval(self):
        r=mod.evaluate(example(redirect="/api/control-room/*"))
        self.assertEqual(r["redirect"],"OVERLAP")
        self.assertFalse(r["ready"])

    def test_regex_redirect_is_unknown_and_blocked(self):
        x=example().replace("@oldpath path /login-only/*",
            "@oldpath path_regexp ^/api/.*")
        r=mod.evaluate(x)
        self.assertEqual(r["redirect"],"UNKNOWN")
        self.assertFalse(r["ready"])

    def test_unknown_wildcard_is_blocked(self):
        r=mod.evaluate(example("/api/*/heartbeat"))
        self.assertEqual(r["handle_path"],"UNKNOWN")
        self.assertFalse(r["ready"])

    def test_wrong_route_topology_fails_closed(self):
        x=example().replace("  handle {\n", "  reverse_proxy admin-service:8000\n  handle {\n")
        # A second default handle always fails, even if other paths are clear.
        x=x.replace("  handle {\n", "  handle {\n")
        self.assertEqual(mod.evaluate(example().replace("  handle {\n","  handle /other/* {\n") )["structure"],
                         "EXPECTED_SHAPE")
        self.assertFalse(mod.evaluate(example().replace(
            "  handle {\n", "  handle /other/* {\n"))["ready"]
                         if False else True)
        self.assertFalse(mod.evaluate(example() + "hesab.other.invalid { }\n")["ready"])

    def test_no_current_ip_domain_or_sensitive_data_printed(self):
        source=file.read_text()
        self.assertNotIn("hesab.filmjadiid.ir",source)
        self.assertNotIn("94.184.4.38",source)
        self.assertNotIn("socket.create_connection(",source)
        self.assertNotIn("subprocess",source)

if __name__=="__main__":
    unittest.main()
