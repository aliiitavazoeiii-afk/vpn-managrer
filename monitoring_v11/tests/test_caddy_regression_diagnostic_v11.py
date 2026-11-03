"""Offline tests for redacted Caddy structural diagnostic; no real services."""
import copy
import importlib.util
from pathlib import Path
import unittest

p=Path(__file__).resolve().parents[1]/"audit_caddy_regression_diagnostic_v11.py"
spec=importlib.util.spec_from_file_location("caddy_diff_v11",p)
d=importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)

BASE={"apps":{"http":{"servers":{"s":{"routes":[{"handle":[{"handler":"subroute",
"routes":[{"match":[{"path":["/old/*"]}],"group":"group42",
"handle":[{"handler":"reverse_proxy","upstreams":[{"dial":"old-service:8000"}]}]}]}]}]}}}}}

def augmented():
    newer=copy.deepcopy(BASE)
    routes=newer["apps"]["http"]["servers"]["s"]["routes"][0]["handle"][0]["routes"]
    routes[0]["group"]="group11"
    routes.insert(0,{"match":[{"path":[d.REG.candidate_module.HEARTBEAT_PATH],
        "method":["POST"]}],"group":"group33",
        "handle":[{"handler":"reverse_proxy",
                   "upstreams":[{"dial":d.REG.candidate_module.INTERNAL_UPSTREAM}]}]})
    return newer

class DiagnosticTests(unittest.TestCase):
    def test_generated_group_only_is_reported_not_automatically_approved(self):
        outcome=d.analyze(BASE,augmented())
        self.assertEqual(outcome["removed"],1)
        self.assertEqual(outcome["verdict"],"NOT_IDENTICAL_AFTER_STRIP")
        self.assertTrue(outcome["only_groups"])
        self.assertEqual(outcome["diffs"][0][1],"OPAQUE_GROUP_ID_CHANGED")

    def test_actual_upstream_change_is_detected(self):
        after=augmented()
        routes=after["apps"]["http"]["servers"]["s"]["routes"][0]["handle"][0]["routes"]
        routes[1]["handle"][0]["upstreams"][0]["dial"]="wrong-upstream:8000"
        outcome=d.analyze(BASE,after)
        self.assertFalse(outcome["only_groups"])
        self.assertNotEqual(outcome["verdict"],"UNCHANGED_EXCEPT_NEW_POST_ROUTE")

    def test_new_handler_which_isnt_post_only_is_not_accepted(self):
        after=augmented()
        after["apps"]["http"]["servers"]["s"]["routes"][0]["handle"][0]["routes"][0]["match"][0]["method"]=["GET"]
        outcome=d.analyze(BASE,after)
        self.assertEqual(outcome["verdict"],"NEW_ROUTE_NOT_EXACT_POST")

    def test_no_private_field_values_in_diagnostic(self):
        left={"sensitive-site.domain":{"Authorization":"private-token-value"}}
        right={"sensitive-site.domain":{"Authorization":"other-token-value"}}
        changes,_=d.structural_differences(left,right)
        text=repr(changes)
        self.assertNotIn("private-token-value",text)
        self.assertNotIn("other-token-value",text)
        self.assertNotIn("sensitive-site.domain",text)
        self.assertNotIn("Authorization",text)
        self.assertIn("<redacted_key>",text)

    def test_no_runtime_mutation_functions(self):
        source=p.read_text()
        for forbidden in ["systemctl restart","caddy reload","docker compose up",
                          "docker restart","socket.create_connection("]:
            self.assertNotIn(forbidden,source)

if __name__=="__main__":
    unittest.main()
