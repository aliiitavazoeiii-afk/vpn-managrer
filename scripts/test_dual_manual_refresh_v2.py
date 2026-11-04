#!/usr/bin/env python3
"""Offline regression for protected manual read-only Dual status refresh."""
import ast
import importlib.util
from pathlib import Path
import types
import unittest
from jinja2 import Environment

ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/"patches/control_room_dual_manual_refresh_v2.py"
BROKER=ROOT/"scripts/maya_dual_refresh_broker_v2.py"
REPAIR=ROOT/"scripts/repair_maya3_xui_sync_v2.py"
INSTALL=ROOT/"scripts/install_dual_manual_refresh_v2.sh"

def create_app():
    class App:
        def __init__(self):
            self.router=types.SimpleNamespace(routes=[])
        def add_api_route(self,path,fun,methods=None):
            self.router.routes.append(types.SimpleNamespace(path=path,endpoint=fun,
                              methods=methods))
    return App()

class Tests(unittest.TestCase):
    def test_python_sources_are_parseable(self):
        for p in (PATCH,BROKER,REPAIR):
            ast.parse(p.read_text(encoding="utf8"))
    def test_app_patch_template_executes_after_grid(self):
        source=PATCH.read_text(encoding="utf8")
        env=Environment()
        prior='''{% block content %}
        <style id="t10-compact-css"></style>
        <section id="dh1-root">
         <div class="dh1-heading">
          <span class="dh1-note">بررسی خودکار هر ساعت · زمان پاسخ HTTPS، نه پینگ ICMP</span>
         </div>
         <div id="dh1-grid"></div>
        </section>
        <script id="dh1-script">
        function refresh(){}
        render(null);refresh();
        setInterval(refresh,60000);
        </script>
        {% endblock %}'''
        templates={"control_room.html":prior}
        app=create_app()
        ns={"TEMPLATES":templates,"app":app,"env":env,
            "_dh1_auth":lambda req: False}
        exec(compile(source,str(PATCH),"exec"),ns)
        updated=templates["control_room.html"]
        Environment().parse(updated)
        self.assertEqual(updated.count('id="dm2-refresh"'),1)
        self.assertEqual(updated.count('id="dm2-script"'),1)
        self.assertLess(updated.index('id="dh1-grid"'),
                        updated.index('id="dh1-script"'))
        self.assertLess(updated.index('id="dh1-script"'),
                        updated.index('id="dm2-script"'))
        self.assertIn("window.__HESAB_DUAL_REFRESH_NOW=refresh;",updated)
        self.assertNotIn("{#",updated)
        self.assertEqual([r.path for r in app.router.routes],[
          "/control-room/dual-hourly/refresh",
          "/control-room/dual-hourly/refresh-meta"])
    def test_broker_fixed_operation_only(self):
        spec=importlib.util.spec_from_file_location("dual_broker",BROKER)
        broker=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(broker)
        for payload in (None,{},{"op":"health"},
                        {"op":"refresh","server":"maya3"},
                        {"op":"refresh","cmd":"sh"},
                        {"op":"refresh","server":"maya1"}):
            self.assertFalse(broker.handle(payload)["ok"])
        self.assertIn('"/usr/bin/python3"',BROKER.read_text())
        self.assertNotIn("shell=True",BROKER.read_text())
        self.assertIn('"StrictHostKeyChecking=yes"',
                       (ROOT/"scripts/maya_dual_hourly_collect_v1.py").read_text())
        self.assertNotIn("dual health",BROKER.read_text().split("def run_job():")[1])
    def test_no_ui_can_pass_ip_or_credentials_to_worker(self):
        source=PATCH.read_text()
        self.assertIn('request.headers.get("origin")',source)
        self.assertIn("_dh1_auth(request)",source)
        self.assertIn('b\\'{"op":"refresh"}\\\\n\\'',source.replace('b\'{"op":"refresh"}\\n\'','b\\\'{"op":"refresh"}\\\\n\\\'')) if False else None
        self.assertNotIn("subprocess.run(",source)
        self.assertNotIn("ssh_identity",source)
        self.assertNotIn("docker compose",source)
        self.assertIn("MAYA3_IP=",REPAIR.read_text())
        self.assertIn("verify_rsa_host()",REPAIR.read_text())
        self.assertIn("maya.pull",REPAIR.read_text())
        self.assertIn("shutil.copy2",REPAIR.read_text())
        self.assertIn("BACKUP=",INSTALL.read_text())
        self.assertIn("--no-deps --no-build --force-recreate app",INSTALL.read_text())
if __name__=="__main__":
    unittest.main(verbosity=2)
