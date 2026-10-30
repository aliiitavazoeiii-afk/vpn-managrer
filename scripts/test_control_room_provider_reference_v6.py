#!/usr/bin/env python3
"""Control Room V6 offline integration: V2 -> Phase1 -> V3 -> V4 -> M2 -> V5 -> V6.
No production dependencies, no SSH, no XUI and no provider calls.
"""
import ast,json,re,subprocess,sys,tempfile,time,types
from pathlib import Path
from jinja2 import Environment,DictLoader

ROOT=Path(__file__).resolve().parents[1]
base=ROOT/"patches/control_room_v2.py"
order=[
  "patches/control_room_phase1_v1.py",
  "patches/control_room_table_v3.py",
  "patches/control_room_live_visual_v4.py",
  "patches/control_room_net_meter_v2_ui.py",
  "patches/control_room_nic_live_v5.py",
  "patches/control_room_provider_reference_v6.py",
]
v2=ast.parse(base.read_text(encoding="utf8"))
template=None
for node in v2.body:
    if isinstance(node,ast.Assign):
        for target in node.targets:
            if isinstance(target,ast.Name) and target.id=="_CR2_TEMPLATE":
                template=ast.literal_eval(node.value)
assert template
# Dynamically linked matching controls are inserted before Phase1.
template=template.replace('<div id="c2-cards" class="c2-cards"></div>',
      '<div id="mdl2-toolbar"></div><div id="c2-cards" class="c2-cards"></div>',1)
templates={"control_room.html":template}
env=Environment(loader=DictLoader(templates))
fastapi=types.ModuleType("fastapi")
fastapi.Request=type("Request",(),{})
responses=types.ModuleType("fastapi.responses")
class Json:
    def __init__(self,doc,headers=None,status_code=200):
        self.body=json.dumps(doc).encode()
        self.status_code=status_code
responses.JSONResponse=Json
sys.modules["fastapi"]=fastapi
sys.modules["fastapi.responses"]=responses
class App:
    def __init__(self):self.routes={}
    def add_api_route(self,path,method,methods):
        assert path not in self.routes,path
        self.routes[path]=(method,methods)
app=App()
ns={"__builtins__":__builtins__,"TEMPLATES":templates,"env":env,
    "app":app,"_cr2_one":lambda server,db:{"rows":[]}}
for path in order:
    src=(ROOT/path).read_text(encoding="utf8")
    ast.parse(src)
    exec(compile(src,path,"exec"),ns)
    Environment().parse(templates["control_room.html"])
    print("V6_CHAIN_PASS",path)
final=templates["control_room.html"]
for marker in ("آخرین مانده اعلامی دیتاسنتر","b6FetchReference()",
               'id="b6-reference-style"',"RX اندازه‌گیری‌شده",
               "c3Details(server,item)",'id="c3-mode"',"mdl2-toolbar"):
    assert marker in final,marker
assert final.count('id="c2-cards"')==1
assert final.count('id="c2-search"')==1
assert app.routes["/control-room/v6/provider-reference"][1]==["GET"]

with tempfile.TemporaryDirectory() as d:
    temp=Path(d)
    path=temp/"provider_reference.json"
    ns["_B6_REF_PATH"]=path
    doc=json.loads(ns["_b6_status"](None).body)
    assert all(doc["servers"][key]["state"]=="not_recorded"
               for key in ("maya1","maya-s3","maya4"))
    values=[144,189,144]
    data={"format":"HESAB_PROVIDER_BALANCE_REFERENCE_V1",
        "recorded_at":int(time.time()),"provider_observed_at_known":False,
        "source":"operator_report",
        "servers":{key:{"remaining_gb":v}
                   for key,v in zip(("maya1","maya-s3","maya4"),values)}}
    path.write_text(json.dumps(data),encoding="utf8")
    actual=json.loads(ns["_b6_status"](None).body)
    for key,val in zip(("maya1","maya-s3","maya4"),values):
        assert actual["servers"][key]["state"]=="reported_not_live"
        assert actual["servers"][key]["remaining_gb"]==val
        assert actual["servers"][key]["provider_observed_at_known"] is False
    data["provider_observed_at_known"]=True
    path.write_text(json.dumps(data),encoding="utf8")
    invalid=json.loads(ns["_b6_status"](None).body)
    assert invalid["servers"]["maya1"]["state"]=="invalid"
    scripts=re.findall(r"<script>(.*?)</script>",final,re.DOTALL)
    assert scripts
    for index,script in enumerate(scripts):
        scriptfile=temp/f"inline_{index}.js"
        scriptfile.write_text(script,encoding="utf8")
        subprocess.run(["node","--check",str(scriptfile)],check=True)
print("V6_PROVIDER_REFERENCES_API_TEMPLATE_JS_TESTS_OK")
