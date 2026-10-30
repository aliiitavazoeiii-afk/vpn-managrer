#!/usr/bin/env python3
"""HESAB_NIC_LIVE_V5_TEST: integration against real V2/Phase1/V3/V4/M2 template sources."""
import ast,re,subprocess,sys,tempfile,types
from pathlib import Path
from jinja2 import Environment,DictLoader

ROOT=Path(__file__).resolve().parents[1]
patches=[
    "patches/control_room_phase1_v1.py",
    "patches/control_room_table_v3.py",
    "patches/control_room_live_visual_v4.py",
    "patches/control_room_net_meter_v2_ui.py",
    "patches/control_room_nic_live_v5.py"
]
for p in patches:ast.parse((ROOT/p).read_text(encoding="utf-8"),filename=p)
v2=ast.parse((ROOT/"patches/control_room_v2.py").read_text(encoding="utf-8"))
html=None
for n in v2.body:
    if isinstance(n,ast.Assign):
        for target in n.targets:
            if isinstance(target,ast.Name) and target.id=="_CR2_TEMPLATE":
                html=ast.literal_eval(n.value)
assert html is not None
html=html.replace('<div id="c2-cards" class="c2-cards"></div>',
                  '<div id="mdl2-toolbar"></div><div id="c2-cards" class="c2-cards"></div>',1)
templates={"control_room.html":html}
env=Environment(loader=DictLoader(templates))
fa=types.ModuleType("fastapi")
fa.Request=type("Request",(),{})
response=types.ModuleType("fastapi.responses")
class JSONResponse:
    def __init__(self,object,headers=None,status_code=200):
        self.body=object
        self.status_code=status_code
response.JSONResponse=JSONResponse
sys.modules["fastapi"]=fa
sys.modules["fastapi.responses"]=response
class App:
    def __init__(self):self.paths={}
    def add_api_route(self,path,fun,methods):
        assert path not in self.paths
        self.paths[path]=(fun,methods)
app=App()
ns={"__builtins__":__builtins__,"TEMPLATES":templates,"env":env,
    "app":app,"_cr2_one":lambda server,db:{"rows":[]}}
for p in patches:
    exec(compile((ROOT/p).read_text(encoding="utf-8"),p,"exec"),ns)
    Environment().parse(templates["control_room.html"])
    print("NIC_V5_TEMPLATE_PATCH_PASS",p)
final=templates["control_room.html"]
for marker in ("RX اندازه‌گیری‌شده","TX اندازه‌گیری‌شده",
               "n5FetchTraffic()",'id="n5-net-traffic"',
               "c3Details(server,item)",'id="c3-mode"','mdl2-toolbar'):
    assert marker in final,marker
assert final.count('id="c2-search"')==1
assert final.count('id="c2-cards"')==1
assert "/control-room/v5/nic-traffic" in app.paths
assert ns["_n5_read"](None).status_code==200

# Jinja parsing alone does not verify actual browser JS; check all final script tags.
js=re.findall(r"<script>(.*?)</script>",final,re.DOTALL)
assert js
with tempfile.TemporaryDirectory() as folder:
    for i,script in enumerate(js):
        path=Path(folder)/f"template_{i}.js"
        path.write_text(script,encoding="utf-8")
        subprocess.run(["node","--check",str(path)],check=True)
print("NIC_V5_JINJA_JAVASCRIPT_AND_ROUTE_TEST_PASS")
