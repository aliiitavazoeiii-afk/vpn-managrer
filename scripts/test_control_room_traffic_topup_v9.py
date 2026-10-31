#!/usr/bin/env python3
"""Control Room V9 offline integration: complete template plus idempotent purchase API.
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
  "patches/control_room_provisional_remaining_v7.py",
  "patches/control_room_traffic_topup_v9.py",
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
fastapi.Depends=lambda fn:None
fastapi.Form=lambda val=None:val
class HTTPException(Exception):
    def __init__(self,status_code,detail):
        self.status_code=status_code;self.detail=detail
fastapi.HTTPException=HTTPException
sa=types.ModuleType("sqlalchemy")
sa.text=lambda s:s
orm=types.ModuleType("sqlalchemy.orm");orm.Session=object
exc=types.ModuleType("sqlalchemy.exc");exc.IntegrityError=type("IntegrityError",(Exception,),{})
sys.modules["sqlalchemy"]=sa
sys.modules["sqlalchemy.orm"]=orm
sys.modules["sqlalchemy.exc"]=exc
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
for marker in ("t9-topup-panel","t9-notify-enable","name=\"t9-amount\"",
               "/control-room/v9/topup","e7Fetch()", "b6FetchReference()",
               'id="b6-reference-style"',"RX اندازه‌گیری‌شده",
               "c3Details(server,item)",'id="c3-mode"',"mdl2-toolbar"):
    assert marker in final,marker
assert final.count('id="c2-cards"')==1
assert final.count('id="c2-search"')==1
assert app.routes["/control-room/v6/provider-reference"][1]==["GET"]
assert app.routes["/control-room/v7/provisional-remaining"][1]==["GET"]
assert app.routes["/control-room/v9/topup"][1]==["POST"]
assert app.routes["/control-room/v9/traffic"][1]==["GET"]

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
    ns["_E7_BASE"]=temp/"provisional_baseline.json"
    ns["_E7_METER"]=temp/"live_meter.json"
    start=int(time.time())
    baseline={"format":"HESAB_MAYA_PROVISIONAL_BASELINE_V7",
              "created_at":start,"direction_assumption":"rx",
              "provider_observation_time_known":False,"alert_eligible":False,
              "servers":{name:{"starting_reported_remaining_gb":value,
                  "rx_baseline_gb":10.0,"tx_baseline_gb":9.0}
                  for name,value in zip(("maya1","maya-s3","maya4"),values)}}
    sample={"format":"HESAB_PHASE1_V1","collected_at":start,
        "servers":{name:{"state":"ok","traffic_state":"direction_unconfirmed",
             "counter_uncertain":False,"rx_period_gb":11.5,
             "tx_period_gb":9.9} for name in ("maya1","maya-s3","maya4")}}
    ns["_E7_BASE"].write_text(json.dumps(baseline),encoding="utf8")
    ns["_E7_METER"].write_text(json.dumps(sample),encoding="utf8")
    provisional=json.loads(ns["_e7_read"](None).body)
    assert provisional["servers"]["maya1"]["state"]=="provisional"
    assert provisional["servers"]["maya1"]["estimate_remaining_gb"]==142.5
    assert provisional["servers"]["maya-s3"]["estimate_remaining_gb"]==187.5
    assert provisional["servers"]["maya4"]["estimate_remaining_gb"]==142.5
    assert provisional["servers"]["maya1"]["alert_eligible"] is False
    sample["servers"]["maya1"]["counter_uncertain"]=True
    ns["_E7_METER"].write_text(json.dumps(sample),encoding="utf8")
    assert json.loads(ns["_e7_read"](None).body)["servers"]["maya1"]["state"]=="uncertain_counter"
    sample["servers"]["maya1"]["counter_uncertain"]=False
    sample["servers"]["maya1"]["rx_period_gb"]=9
    ns["_E7_METER"].write_text(json.dumps(sample),encoding="utf8")
    assert json.loads(ns["_e7_read"](None).body)["servers"]["maya1"]["state"]=="meter_reset"
    ns["_T9_BASELINE"]=ns["_E7_BASE"]
    # Restore healthy status and confirm operator-purchased +500GB only
    # credited for the CURRENT immutable RX baseline.
    sample["servers"]["maya1"]["rx_period_gb"]=11.5
    ns["_E7_METER"].write_text(json.dumps(sample),encoding="utf8")
    epoch=ns["_t9_epochs"]()["maya1"]
    assert epoch and epoch.endswith("|10.0")
    class Result:
        def __init__(self,data):self.data=data
        def all(self):return self.data
        def first(self):return self.data[0] if self.data else None
        def one(self):assert len(self.data)==1;return self.data[0]
    class FakeDB:
        def __init__(self):self.rows=[];self.seq=1;self.commits=0
        def execute(self,query,params=None):
            query=str(query);params=params or {}
            if query.startswith("INSERT INTO"):
                entry=next((x for x in self.rows if x.request_key==params["key"]),None)
                if entry:return Result([])
                row=types.SimpleNamespace(id=self.seq,
                     server_id=params["server"],gb=params["gb"],
                     request_key=params["key"],origin="operator_ui",
                     meter_epoch=params["epoch"],
                     created_at=__import__("datetime").datetime.now(
                         __import__("datetime").timezone.utc))
                self.seq+=1;self.rows.append(row)
                return Result([row])
            if "WHERE request_key=:key" in query:
                return Result([x for x in self.rows if x.request_key==params["key"]])
            if "ORDER BY id DESC LIMIT 100" in query:
                return Result(self.rows[::-1])
            if "GROUP BY server_id,meter_epoch" in query:
                buckets={}
                for x in self.rows:
                    k=(x.server_id,x.meter_epoch)
                    buckets[k]=buckets.get(k,0)+x.gb
                return Result([types.SimpleNamespace(server_id=k[0],
                    meter_epoch=k[1],total=value) for k,value in buckets.items()])
            raise AssertionError("unexpected SQL")
        def commit(self):self.commits+=1
        def rollback(self):pass
    db=FakeDB()
    class Request:
        session={"maya1_control_csrf":"X"*48}
        headers={"origin":"https://hesab.filmjadiid.ir",
                 "sec-fetch-site":"same-origin"}
    req=Request()
    action=dict(server="maya1",amount=500,request_key="T"*32,csrf="X"*48,db=db)
    first=json.loads(ns["_t9_add"](req,**action).body)
    assert first["already_recorded"] is False
    second=json.loads(ns["_t9_add"](req,**action).body)
    assert second["already_recorded"] is True
    assert len(db.rows)==1
    result=json.loads(ns["_t9_status"](req,db).body)
    assert result["servers"]["maya1"]["topup_gb"]==500
    assert result["servers"]["maya1"]["estimated_remaining_gb"]==642.5
    assert result["servers"]["maya1"]["alert_is_estimate_only"] is True
    # Rebaselining (with time/epoch change) must NOT count a purchase twice.
    baseline["created_at"]+=5
    ns["_E7_BASE"].write_text(json.dumps(baseline),encoding="utf8")
    sums,_=ns["_t9_get_data"](db)
    assert sums["maya1"]==0
    try:ns["_t9_add"](req,**{**action,"amount":200})
    except HTTPException as e:assert e.status_code==409
    else:raise AssertionError("duplicate identifier changed purchase amount")
    scripts=re.findall(r"<script>(.*?)</script>",final,re.DOTALL)
    assert scripts
    for index,script in enumerate(scripts):
        scriptfile=temp/f"inline_{index}.js"
        scriptfile.write_text(script,encoding="utf8")
        subprocess.run(["node","--check",str(scriptfile)],check=True)
print("V9_TOPUP_IDEMPOTENCY_EPOCH_AND_JS_UI_PASS")
