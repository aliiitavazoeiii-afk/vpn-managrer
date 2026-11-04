"""Tests for strict Caddy group relabeling equivalence and preserved routing."""
import copy
import importlib.util
from pathlib import Path
import unittest

target=Path(__file__).resolve().parents[1]/"audit_caddy_group_equivalence_v11.py"
spec=importlib.util.spec_from_file_location("v11_group_alpha",target)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def base():
    return {"apps":{"http":{"servers":{"srv":{"routes":[
        {"match":[{"host":["test.invalid"]}],"handle":[
            {"handler":"subroute","routes":[
                {"group":"a","match":[{"path":["/old/api/*"]}],
                 "handle":[{"handler":"reverse_proxy","upstreams":[{"dial":"backend:8090"}]}]},
                {"group":"a","handle":[{"handler":"reverse_proxy",
                 "upstreams":[{"dial":"backend:8000"}]}]}
            ]}
        ]}
    ]}}}}}

def next_version():
    x=copy.deepcopy(base())
    routes=x["apps"]["http"]["servers"]["srv"]["routes"][0]["handle"][0]["routes"]
    for route in routes:route["group"]="b"
    routes.insert(0,{"group":"b",
       "match":[{"path":[mod.REG.candidate_module.HEARTBEAT_PATH],"method":["POST"]}],
       "handle":[{"handler":"reverse_proxy","upstreams":[
           {"dial":mod.REG.candidate_module.INTERNAL_UPSTREAM}]}]})
    return x

class GroupAuditTests(unittest.TestCase):
    def test_renamed_group_only_accepted(self):
        res=mod.evaluate(base(),next_version())
        self.assertTrue(res["pass"])
        self.assertEqual(res["reason"],"UNCHANGED_EXCEPT_EXACT_POST_AND_GROUP_RENAMES")
        self.assertEqual(res["old_group_count"],1)
        self.assertEqual(res["group_values_changed"],2)

    def test_new_heartbeat_must_share_existing_exclusive_group(self):
        x=next_version()
        rr=x["apps"]["http"]["servers"]["srv"]["routes"][0]["handle"][0]["routes"]
        rr[0]["group"]="independent"
        outcome=mod.evaluate(base(),x)
        self.assertFalse(outcome["pass"])
        self.assertEqual(outcome["reason"],"NEW_ROUTE_NOT_IN_EXISTING_EXCLUSIVE_GROUP")

    def test_split_group_rejected(self):
        x=next_version()
        rr=x["apps"]["http"]["servers"]["srv"]["routes"][0]["handle"][0]["routes"]
        rr[2]["group"]="c"
        self.assertFalse(mod.evaluate(base(),x)["pass"])

    def test_backend_change_rejected(self):
        x=next_version()
        rr=x["apps"]["http"]["servers"]["srv"]["routes"][0]["handle"][0]["routes"]
        rr[1]["handle"][0]["upstreams"][0]["dial"]="changed:8090"
        self.assertFalse(mod.evaluate(base(),x)["pass"])

    def test_existing_route_reordering_rejected(self):
        x=next_version()
        rr=x["apps"]["http"]["servers"]["srv"]["routes"][0]["handle"][0]["routes"]
        rr[1],rr[2]=rr[2],rr[1]
        self.assertFalse(mod.evaluate(base(),x)["pass"])

    def test_non_post_route_rejected(self):
        x=next_version()
        rr=x["apps"]["http"]["servers"]["srv"]["routes"][0]["handle"][0]["routes"]
        rr[0]["match"][0]["method"]=["GET"]
        self.assertFalse(mod.evaluate(base(),x)["pass"])

    def test_non_bijective_group_renaming_rejected(self):
        a={"routes":[{"group":"g1"},{"group":"g2"}]}
        b={"routes":[{"group":"same"},{"group":"same"}]}
        self.assertFalse(mod.group_alpha_equivalent(a,b)[0])

    def test_source_has_no_runtime_mutations(self):
        s=target.read_text()
        for forbidden in ["docker restart","caddy reload","systemctl restart",
                          "socket.create_connection(","/etc/dual-ha/"]:
            self.assertNotIn(forbidden,s)

if __name__=="__main__":
    unittest.main()
