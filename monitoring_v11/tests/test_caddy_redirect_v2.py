"""Offline tests for redacted Caddy redirect matcher V11 scanner."""
import importlib.util
from pathlib import Path
import unittest

p=Path(__file__).resolve().parents[1]/"audit_caddy_redirect_v2_readonly.py"
spec=importlib.util.spec_from_file_location("caddy_v11_redirect_v2",p)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def config(matcher="path /old/*",name="@redir"):
    return ("\n"
      "unrelated.invalid {\n  reverse_proxy other:8000\n}\n"
      "hesab.invalid {\n"
      "  encode zstd gzip\n"
      f"  {name} {matcher}\n"
      f"  redir {name} /to-other-path 301\n"
      "  handle_path /billing-api/* {\n"
      "    reverse_proxy customer:8090\n"
      "  }\n"
      "  handle {\n"
      "    reverse_proxy app:8000\n"
      "  }\n"
      "}\n")

class RedirectTests(unittest.TestCase):
    def test_simple_path_clear(self):
        x=m.evaluate(config())
        self.assertEqual((x["kind"],x["match"]),("PATH","CLEAR"))

    def test_path_overlap(self):
        x=m.evaluate(config("path /api/control-room/*"))
        self.assertEqual((x["kind"],x["match"]),("PATH","OVERLAP"))

    def test_negated_path(self):
        self.assertEqual(m.evaluate(config("not path /api/control-room/*"))["match"],"CLEAR")
        self.assertEqual(m.evaluate(config("not path /other/*"))["match"],"OVERLAP")

    def test_method_get_excludes_post(self):
        self.assertEqual(m.evaluate(config("method GET HEAD"))["match"],"CLEAR")
        self.assertEqual(m.evaluate(config("method POST"))["match"],"OVERLAP")

    def test_complex_matchers_are_not_assumed_safe(self):
        for matcher,kind in [
            ("host other.invalid","HOST"),
            ("header X-Test value","HEADER"),
            ("path_regexp ^/api/.*","REGEXP"),
            ("expression complex-expression","EXPRESSION"),
            ("{","BLOCK"),
        ]:
            with self.subTest(matcher=kind):
                x=m.evaluate(config(matcher))
                self.assertEqual((x["kind"],x["match"]),(kind,"UNKNOWN"))

    def test_bad_redirect_and_topology_are_rejected(self):
        self.assertEqual(m.evaluate(config().replace("redir @redir","redir @missing"))["match"],"UNKNOWN")
        self.assertEqual(m.evaluate(config().replace("  handle {\n","  handle /else/* {\n"))["shape"],"UNEXPECTED")
        self.assertEqual(m.evaluate(config()+"hesab.another.invalid {\n}\n")["site"],"UNEXPECTED")

    def test_only_public_source_free(self):
        source=p.read_text()
        self.assertNotIn("hesab.filmjadiid.ir",source)
        self.assertNotIn("94.184.4.38",source)
        self.assertNotIn("import subprocess",source)
        self.assertNotIn("import socket",source)

if __name__=="__main__":
    unittest.main(verbosity=2)
