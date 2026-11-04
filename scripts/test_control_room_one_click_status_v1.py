#!/usr/bin/env python3
"""Offline template and deployment safety checks for compact one-click UI."""
import ast
from pathlib import Path
import types
import unittest
from jinja2 import Environment

ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/"patches/control_room_one_click_status_v1.py"
INSTALL=ROOT/"scripts/install_control_room_one_click_status_v1.sh"

class Tests(unittest.TestCase):
 def test_template_inserts_one_compact_section_after_anchor(self):
  class App: pass
  base='''{% block content %}
  <style id="t10-compact-css"></style>
  <div id="c2-cards" class="c2-cards"></div>
  <section id="dh1-root"><div id="dm2-refresh"></div></section>
  <section id="pq-root">Verbose tables</section>
  {% endblock %}
  '''
  data={"control_room.html":base}
  namespace={"TEMPLATES":data,"env":Environment(),"app":App()}
  exec(compile(PATCH.read_text(),str(PATCH),"exec"),namespace)
  result=data["control_room.html"]
  self.assertEqual(result.count('id="ocs-root"'),1)
  self.assertEqual(result.count('id="ocs-check"'),1)
  self.assertEqual(result.count('id="ocs-js"'),1)
  self.assertLess(result.index('id="ocs-grid"'),result.index('id="ocs-js"'))
  self.assertIn("#c2-root #dh1-root, #c2-root #pq-root {display:none!important}",result)
  self.assertIn("Verbose tables",result,"Backend and original JS should remain intact")
  Environment().parse(result)
 def test_no_new_endpoint_or_active_download(self):
  source=PATCH.read_text()
  self.assertNotIn("add_api_route(",source)
  self.assertNotIn("subprocess",source)
  self.assertNotIn("socket",source)
  self.assertNotIn("curl ",source)
  self.assertNotIn("dual health",source)
  self.assertIn('"/control-room/dual-hourly/refresh"',source)
  self.assertIn('"/control-room/dual-quality/status"',source)
  self.assertIn("کیفیت واقعی انتقال داده",source)
 def test_guarded_install_safety(self):
  s=INSTALL.read_text()
  for assertion in ("DATABASE_BACKUP=CREATED","BACKUP=","ROLLING_BACK",
                    "--no-deps --no-build --force-recreate app",
                    "PREFLIGHT PRODUCTION DASHBOARD"):
   # Rollback text can mention RESTORING rather than ROLLING_BACK
   if assertion=="ROLLING_BACK":
    self.assertIn("RESTORING_ADMIN_OVERLAY",s)
   else:self.assertIn(assertion,s)
  self.assertNotIn("restart haproxy",s)
  self.assertNotIn("systemctl restart",s)
  self.assertNotIn("docker compose down",s)
if __name__=="__main__":
 unittest.main(verbosity=2)
