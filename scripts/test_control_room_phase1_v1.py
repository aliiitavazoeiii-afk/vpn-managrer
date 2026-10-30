#!/usr/bin/env python3
"""Static, isolated phase1 checks: no production service, DB or credentials."""
import ast,importlib.util,json,subprocess,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
files=("patches/control_room_phase1_v1.py",
       "scripts/phase1_iran_remote_sensor_v1.py",
       "scripts/phase1_iran_metrics_collect_v1.py")
for path in files:
    text=(ROOT/path).read_text(encoding="utf-8")
    ast.parse(text,filename=path)
    print("PYTHON_SYNTAX_OK",path)
patch=ast.parse((ROOT/files[0]).read_text(encoding="utf-8"))
labels={}
for node in patch.body:
    if isinstance(node,ast.Assign):
        for target in node.targets:
            if isinstance(target,ast.Name) and target.id in ("_P1_CSS","_P1_HEADER","_P1_METRICS","_P1_SCRIPT"):
                labels[target.id]=ast.literal_eval(node.value)
assert len(labels)==4
assert "position:sticky" not in labels["_P1_CSS"]
assert "thead{display:none!important}" in labels["_P1_CSS"]
assert "tbody{display:grid!important}" in labels["_P1_CSS"]
assert "p1-monitor" in labels["_P1_METRICS"]
from jinja2 import Environment
jinja_snippet=labels["_P1_CSS"]+labels["_P1_HEADER"]+labels["_P1_METRICS"]+labels["_P1_SCRIPT"]
assert "{#" not in jinja_snippet,"Unsafe Jinja comment opener in CSS/JS"
Environment().parse(jinja_snippet)
print("PHASE1_JINJA_TEMPLATE_SYNTAX_OK")
with tempfile.TemporaryDirectory() as tmp:
    js=Path(tmp)/"phase1.js"
    js.write_text(labels["_P1_SCRIPT"].replace("<script>","").replace("</script>",""),encoding="utf-8")
    subprocess.run(["node","--check",str(js)],check=True)
print("PHASE1_RESPONSIVE_JS_OK")
spec=importlib.util.spec_from_file_location("phase1_monitor",ROOT/files[2])
monitor=importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)
settings={"host":"192.0.2.5","interface":"ens160","quota_gb":100,"used_at_start_gb":5}
fresh={"cpu_pct":20,"ram_pct":33,"rx_bytes":1000,"tx_bytes":3000,"boot_id":"12345678-1234-1234-1234-123456789abc"}
a,baseline=monitor.calculate(settings,100,fresh,None)
assert a["traffic_state"]=="estimated" and a["remaining_gb"]==95
next_sample=dict(fresh,rx_bytes=1000001000,tx_bytes=3000)
b,progress=monitor.calculate(settings,200,next_sample,baseline)
assert b["remaining_gb"]==94 and progress["accumulated_bytes"]==1000000000
restart=dict(fresh,boot_id="abcdef12-1234-1234-1234-123456789abc")
c,after=monitor.calculate(settings,300,restart,progress)
assert c["traffic_state"]=="uncertain_reset" and after["rebooted"] is True
assert c["remaining_gb"]==94
print("QUOTA_BASELINE_AND_REBOOT_TEST_OK")
