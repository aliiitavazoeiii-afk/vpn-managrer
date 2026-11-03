"""Unit tests for full baseline-vs-candidate adapted Caddy JSON comparison."""
import copy
import importlib.util
from pathlib import Path
import unittest

p=Path(__file__).resolve().parents[1]/"audit_caddy_offline_regression_v11.py"
spec=importlib.util.spec_from_file_location("hesab_caddy_regression_v11",p)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def old_document():
    return {"apps":{"http":{"servers":{"main":{"routes":[
        {"match":[{"host":["example.invalid"]}],
         "handle":[{"handler":"subroute","routes":[
            {"match":[{"path":["/existing/*"]}],
             "handle":[{"handler":"reverse_proxy",
                        "upstreams":[{"dial":"existing:8090"}]}]},
            {"handle":[{"handler":"reverse_proxy",
                        "upstreams":[{"dial":"existing:8000"}]}]}
         ]}],"terminal":True}
    ]}}}}}

def heartbeat_route():
    return {"match":[{"path":[mod.candidate_module.HEARTBEAT_PATH],
                      "method":["POST"]}],
            "handle":[{"handler":"subroute","routes":[
                {"handle":[{"handler":"reverse_proxy",
                            "upstreams":[{"dial":mod.candidate_module.INTERNAL_UPSTREAM}]}]}
            ]}]}

def proposed_document():
    new=copy.deepcopy(old_document())
    routes=new["apps"]["http"]["servers"]["main"]["routes"][0]["handle"][0]["routes"]
    routes.insert(0,heartbeat_route())
    return new

class RegressionTests(unittest.TestCase):
    def test_one_new_post_only_route_preserves_existing(self):
        baseline=old_document()
        candidate=proposed_document()
        self.assertEqual(mod.compare(baseline,candidate),
                         "UNCHANGED_EXCEPT_NEW_POST_ROUTE")
        self.assertEqual(baseline,old_document())  # no in-place mutation
        self.assertEqual(candidate,proposed_document())

    def test_altered_existing_backend_detected(self):
        new=proposed_document()
        new["apps"]["http"]["servers"]["main"]["routes"][0]["handle"][0]["routes"][1]["handle"][0]["upstreams"][0]["dial"]="changed:8090"
        self.assertEqual(mod.compare(old_document(),new),"NOT_IDENTICAL_AFTER_STRIP")

    def test_duplicate_or_nonexact_heartbeat_rejected(self):
        new=proposed_document()
        new["apps"]["http"]["servers"]["main"]["routes"][0]["handle"][0]["routes"].insert(0,heartbeat_route())
        self.assertNotEqual(mod.compare(old_document(),new),"UNCHANGED_EXCEPT_NEW_POST_ROUTE")
        wrong=proposed_document()
        wrong["apps"]["http"]["servers"]["main"]["routes"][0]["handle"][0]["routes"][0]["match"][0]["method"]=["GET"]
        self.assertEqual(mod.compare(old_document(),wrong),"NEW_ROUTE_NOT_EXACT_POST")

    def test_missing_heartbeat_rejected(self):
        self.assertNotEqual(mod.compare(old_document(),old_document()),"UNCHANGED_EXCEPT_NEW_POST_ROUTE")

    def test_never_uses_live_caddy_api(self):
        src=p.read_text(encoding="utf8")
        for invalid in ["caddy reload","docker restart","docker compose up","urlopen(","socket.create_connection("]:
            self.assertNotIn(invalid,src)

if __name__=="__main__":
    unittest.main(verbosity=2)
