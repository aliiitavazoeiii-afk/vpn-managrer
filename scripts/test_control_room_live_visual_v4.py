#!/usr/bin/env python3
"""Offline integration test: authentic V2 template -> Phase1 -> V3 -> V4.
Requires Jinja2 and Node; no credentials, production DB, HTTP or XUI mutations.
"""
import ast,re,subprocess,sys,tempfile,types
from pathlib import Path
from jinja2 import Environment,DictLoader

ROOT=Path(__file__).resolve().parents[1]
paths=[
  "patches/control_room_v2.py",
  "patches/control_room_phase1_v1.py",
  "patches/control_room_table_v3.py",
  "patches/control_room_live_visual_v4.py",
  "scripts/maya_xui_host_metrics_v1.py"
]
for p in paths:
    ast.parse((ROOT/p).read_text(encoding="utf-8"),filename=p)
print("V4_PYTHON_SYNTAX_OK")

original=ast.parse((ROOT/paths[0]).read_text(encoding="utf-8"))
original_template=None
for node in original.body:
    if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="_CR2_TEMPLATE" for t in node.targets):
        original_template=ast.literal_eval(node.value)
assert original_template
# The live project has an operator matching toolbar inserted by the Maya
# dynamic-links overlay after Control Room V2 and before Phase1.
original_template=original_template.replace(
    '<div id="c2-cards" class="c2-cards"></div>',
    '<div id="mdl2-toolbar"></div><div id="c2-cards" class="c2-cards"></div>',1)
templates={"control_room.html":original_template}
env=Environment(loader=DictLoader(templates))

# Stub the two FastAPI imports used only for read-only status endpoints.
fa=types.ModuleType("fastapi")
fa.Request=type("Request",(),{})
class Response:
    def __init__(self,document,headers=None,status_code=200):
        self.body=document
        self.status_code=status_code
fa_resp=types.ModuleType("fastapi.responses")
fa_resp.JSONResponse=Response
sys.modules.setdefault("fastapi",fa)
sys.modules.setdefault("fastapi.responses",fa_resp)

class Router:
    def __init__(self): self.routes={}
    def add_api_route(self,path,view,methods):
        assert path not in self.routes,("duplicate route",path)
        self.routes[path]=(view,methods)
app=Router()
ns={"__builtins__":__builtins__,
    "TEMPLATES":templates,"env":env,"app":app,
    "_cr2_one":lambda server,db:{"rows":[]}}
for p in paths[1:4]:
    src=(ROOT/p).read_text(encoding="utf-8")
    exec(compile(src,p,"exec"),ns)
    Environment().parse(ns["TEMPLATES"]["control_room.html"])
    print("TEMPLATE_TRANSFORM_PASS",p)

html=ns["TEMPLATES"]["control_room.html"]
for marker in ('id="c4-shell"','id="c2-cards"','id="c3-mode"',
               'id="c2-users"','mdl2-toolbar','c3Details(server,item)'):
    assert marker in html,marker
assert html.count('id="c2-cards"')==1
assert html.count('id="c2-search"')==1
assert "IR-1" not in html and "Foreign-1" not in html
assert "c4FetchMetrics()" in html
assert "{#" not in html
assert "/control-room/v4/host-metrics" in app.routes
assert app.routes["/control-room/v4/host-metrics"][1]==["GET"]
assert ns["_c4_status"](None).status_code==200

# Validate all actual generated scripts after Jinja interpolation.
rendered=html.replace("{{ ctrl_csrf }}","example-csrf")
snippets=re.findall(r"<script>(.*?)</script>",rendered,re.DOTALL)
assert len(snippets)>=2
with tempfile.TemporaryDirectory() as t:
    for i,script in enumerate(snippets):
        file=Path(t)/("inline-"+str(i)+".js")
        file.write_text(script,encoding="utf-8")
        subprocess.run(["node","--check",str(file)],check=True)
print("V4_JS_JINJA_TRANSFORMATION_ROUTE_SMOKE_OK")
