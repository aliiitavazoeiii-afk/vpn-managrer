#!/usr/bin/env python3
"""Offline V2 NIC meter tests; no SSH, XUI, finance or production files."""
import ast, importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"scripts/maya_net_meter_collect_v2.py"
SENSOR=ROOT/"scripts/maya_net_meter_sensor_v2.py"
PATCH=ROOT/"patches/control_room_net_meter_v2_ui.py"
for p in (SOURCE,SENSOR,PATCH,ROOT/"scripts/maya_net_meter_manage_v2.py"):
    ast.parse(p.read_text(encoding="utf-8"),filename=str(p))
    print("SOURCE_PARSE_OK",p.name)

spec=importlib.util.spec_from_file_location("meter_v2",SOURCE)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
def reading(rx,tx,boot="12345678-1234-1234-1234-123456789abc",index=2):
    return {"format":m.VERSION,"iface":"ens160","rx_bytes":rx,
            "tx_bytes":tx,"boot_id":boot,"ifindex":index,
            "sample_time":1_000_000,"uptime_s":1111}
cfg={"host":"192.0.2.5","interface":"ens160","direction":"rx",
     "period_id":"2026-10-30","quota_gb":100,"initial_provider_used_gb":10}
one,st=m.calculate(cfg,reading(100_000_000,70_000_000),None,1_000_000)
assert one["remaining_gb"]==90 and one["traffic_source"]=="NIC_RX"
two,st2=m.calculate(cfg,reading(20_100_000_000,30_070_000_000),st,1_000_060)
assert two["rx_period_gb"]==20 and two["tx_period_gb"]==30
assert two["traffic_used_gb"]==30 and two["remaining_gb"]==70
assert two["traffic_state"]=="estimated"
txcfg=dict(cfg,direction="tx",period_id="2026-10-30-tx")
txfirst,txst=m.calculate(txcfg,reading(100,100),None,1_000_000)
txsecond,txst=m.calculate(txcfg,reading(12_000_000_100,4_000_000_100),txst,1_000_060)
assert txsecond["traffic_used_gb"]==14 and txsecond["remaining_gb"]==86
assert txsecond["traffic_source"]=="NIC_TX"
reboot,st3=m.calculate(cfg,reading(2000,4000,boot="abcdef12-1234-1234-1234-123456789abc"),
                        st2,1_000_120)
assert reboot["traffic_state"]=="uncertain_reset"
assert "remaining_gb" not in reboot
assert st3["accum_rx"]==20_000_000_000
after,st4=m.calculate(cfg,reading(1_000_002_000,2_000_004_000,
 boot="abcdef12-1234-1234-1234-123456789abc"),st3,1_000_180)
assert after["traffic_state"]=="uncertain_reset" and st4["accum_rx"]==21_000_000_000
try:
    m.calculate(dict(cfg,direction="tx"),reading(1_000_000_000,2_000_000_000),st2,1_000_240)
except ValueError:pass
else:raise AssertionError("same period direction change must fail")
# Provider quota top-up preserves the original measured epoch.
larger,st5=m.calculate(dict(cfg,quota_gb=150),
                       reading(20_100_000_000,30_070_000_000),st2,1_000_180)
assert larger["remaining_gb"]==120 and st5["accum_rx"]==20_000_000_000
undirected,unknown=m.calculate(
    {"host":"192.0.2.5","interface":"ens160"},
    reading(500,700),None,1_000_000)
assert "remaining_gb" not in undirected
assert undirected["traffic_state"]=="direction_unconfirmed"

# In-place UI patch against exact V4 card snippet, Jinja-validated.
from jinja2 import Environment, DictLoader
tree=ast.parse(PATCH.read_text(encoding="utf-8"))
values={}
for node in tree.body:
    if isinstance(node,ast.Assign):
        for target in node.targets:
            if isinstance(target,ast.Name) and target.id in ("_M2_TARGET","_M2_FOOT"):
                values[target.id]=ast.literal_eval(node.value)
assert set(values)=={"_M2_TARGET","_M2_FOOT"}
base=("{% block content %}<div id=\"c2-search\"></div><script>"+
      values["_M2_TARGET"]+" "+values["_M2_FOOT"]+
      "</script>{% endblock %}")
templates={"control_room.html":base}
env=Environment(loader=DictLoader(templates))
ns={"TEMPLATES":templates,"env":env}
exec(compile(PATCH.read_text(),str(PATCH),"exec"),ns)
html=templates["control_room.html"]
assert "مصرف مبنای سهمیه" in html and "m2-warning" in html
Environment().parse(html)
print("MAYA_NET_METER_V2_QUOTA_REBOOT_DIRECTION_AND_UI_TESTS_OK")
