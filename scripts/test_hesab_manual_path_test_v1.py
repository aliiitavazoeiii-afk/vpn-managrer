#!/usr/bin/env python3
"""No live transfer is executed in this regression suite."""
import importlib.util
from pathlib import Path
from unittest import mock
import types
import unittest
from jinja2 import Environment

ROOT=Path(__file__).resolve().parents[1]
REMOTE=ROOT/"scripts/hesab_path_test_remote_v1.py"
BROKER=ROOT/"scripts/hesab_manual_path_test_broker_v1.py"
PATCH=ROOT/"patches/control_room_manual_path_test_v1.py"
INSTALL=ROOT/"scripts/install_hesab_manual_path_test_v1.sh"
PREP=ROOT/"scripts/prepare_hesab_path_test_v1.py"
REMOTE_INSTALL=ROOT/"scripts/install_hesab_path_test_remote_v1.py"

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

remote=load(REMOTE,"transfer_test_remote")
broker=load(BROKER,"transfer_test_broker")

def fake_curl(exit_code=0,http=200,received=524288,seconds=.98,ttfb=.15):
    return types.SimpleNamespace(
        returncode=exit_code,
        stdout=f"{http} {received} {seconds} {ttfb}")

class Tests(unittest.TestCase):
    def test_healthy_complete_data_is_required(self):
        with mock.patch.object(remote.subprocess,"run",
                               return_value=fake_curl()) as run:
            item=remote.test_one("mieru",21002)
            self.assertEqual(item["state"],"healthy")
            self.assertEqual(item["received_bytes"],524288)
            args=run.call_args.args[0]
            self.assertIn("--socks5-hostname",args)
            self.assertIn("127.0.0.1:21002",args)
            self.assertIn("--max-time",args)
            self.assertIn("--retry",args)
            self.assertIn("https://speed.cloudflare.com/__down?bytes=524288",args)
            self.assertNotIn("-k",args)
            self.assertNotIn("--location",args)
    def test_actual_maya3_http200_with_30118_timeout_is_warning(self):
        with mock.patch.object(remote.subprocess,"run",return_value=
                               fake_curl(28,200,30118,25.0,.22)):
            result=remote.test_one("mieru",21002)
        self.assertEqual(result["state"],"warning")
        self.assertEqual(result["reason"],"timeout")
        self.assertEqual(result["received_bytes"],30118)
        self.assertEqual(result["http_status"],200)
    def test_partial_or_slow_complete_is_warning(self):
        samples=(fake_curl(0,200,30118,1.0),
                 fake_curl(0,200,524288,15.0),
                 fake_curl(0,503,524288,1.0))
        for result in samples:
            with self.subTest(result=result):
                with mock.patch.object(remote.subprocess,"run",return_value=result):
                    self.assertEqual(remote.test_one("backhaul",21001)["state"],"warning")
    def test_there_are_three_fixed_ports_and_budget(self):
        self.assertEqual(remote.PATHS,{"backhaul":21001,"mieru":21002,"haproxy":18080})
        self.assertEqual(remote.BYTES,524288)
        self.assertEqual(remote.MAX_SECONDS,25)
        self.assertEqual(3*3*remote.BYTES,4718592)
        self.assertEqual(remote.COOLDOWN,120)
    def test_remote_preflight_executes_no_curl(self):
        with mock.patch.dict(remote.os.environ,{"SSH_ORIGINAL_COMMAND":"hesab-path-test-preflight"}):
            with mock.patch.object(remote,"test_one",side_effect=AssertionError("active")):
                with mock.patch.object(remote,"output") as output:
                    remote.run()
                    payload=output.call_args.args[0]
                    self.assertEqual(payload["mode"],"preflight")
    def test_broker_rejects_arbitrary_operation(self):
        for bad in ({},{"op":"ssh"},{"op":"start","host":"maya4"},{"op":"health"}):
            self.assertFalse(broker.handle(bad)["ok"])
    def test_broker_verifies_complete_true_metrics(self):
        meta=lambda state="healthy",received=524288: {
           "state":state,"http_status":200,"requested_bytes":524288,
           "received_bytes":received,"exit_code":0,"duration_ms":980,
           "ttfb_ms":130,"reason":"complete"}
        reply={"format":broker.REMOTE_FORMAT,"state":"completed",
            "paths":{role:meta() for role in broker.ROLES}}
        with mock.patch.object(broker,"run_ssh",return_value=reply):
            x=broker.fetch_one("maya-s3")
            self.assertEqual(x["state"],"completed")
            self.assertTrue(all(x["paths"][r]["state"]=="healthy" for r in broker.ROLES))
        reply["paths"]["mieru"]=meta("healthy",30118)
        with mock.patch.object(broker,"run_ssh",return_value=reply):
            x=broker.fetch_one("maya-s3")
            self.assertEqual(x["paths"]["mieru"]["state"],"warning")
    def test_app_template_contains_two_buttons_and_no_server_probes(self):
        html='''{% block content %}
          <style id="t10-compact-css"></style>
          <button id="ocs-check" type="button">بررسی وضعیت</button>
          <div id="ocs-grid" class="ocs-grid"></div>
          <script id="ocs-js">console.log("original")</script>
          {% endblock %}'''
        class App:
            def __init__(self):
                self.router=types.SimpleNamespace(routes=[])
            def add_api_route(self,path,fn,methods):
                self.router.routes.append(types.SimpleNamespace(path=path))
        env=Environment(); templates={"control_room.html":html}
        namespace={"TEMPLATES":templates,"env":env,"app":App(),
                   "_dh1_auth":lambda req: False}
        exec(compile(PATCH.read_text(),str(PATCH),"exec"),namespace)
        output=templates["control_room.html"]
        self.assertEqual(output.count('id="ocs-transfer-check"'),1)
        self.assertEqual(output.count('id="pt-ui-script"'),1)
        self.assertTrue(output.index('id="ocs-transfer-grid"')<
                        output.index('id="pt-ui-script"'))
        Environment().parse(output)
        self.assertEqual([r.path for r in namespace["app"].router.routes],
                         ["/control-room/path-test/start","/control-room/path-test/status"])
        source=PATCH.read_text()
        self.assertIn('_dh1_auth(request)',source)
        self.assertIn('request.headers.get("origin")',source)
        self.assertNotIn("subprocess.run",source)
    def test_installers_have_no_automatic_download(self):
        install=INSTALL.read_text()
        remote_inst=REMOTE_INSTALL.read_text()
        self.assertIn("--preflight",install)
        self.assertNotIn('"hesab-path-test-v1"',install)
        self.assertNotIn("test_one(",remote_inst)
        self.assertNotIn("systemctl restart",install)
        self.assertNotIn("docker compose down",install)
        self.assertIn("DATABASE_BACKUP",install)
        self.assertIn("ROOT_REQUIRED",install)
        self.assertIn("ACTIVE_DOWNLOADS_EXECUTED=NO",PREP.read_text())
if __name__=="__main__":
    unittest.main(verbosity=2)
