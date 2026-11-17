#!/usr/bin/env python3
"""Offline integration tests: physical NIC continuity, 30-day charts, safe endpoints."""
import importlib.util
import json
import runpy
import subprocess
import sys
import tempfile
import time
import types
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("traffic",ROOT/"scripts/maya_traffic_history_v11.py")
meter=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(meter)


def raw(at, rx, tx=0, boot="0"*36):
    return {"last_rx":rx,"last_tx":tx,"sample_at":at,"ifindex":2,
            "boot_id":boot,"identity":"203.0.113.1|eth0"}


def tests_meter():
    with tempfile.TemporaryDirectory() as folder:
        first=int(datetime(2026,11,17,23,59,20,tzinfo=ZoneInfo("Asia/Tehran")).timestamp())
        prev={"buckets":{}}
        assert meter.advance(prev,raw(first,1_000_000_000),first)=="baseline"
        assert meter.advance(prev,raw(first+100,1_100_000_000,50_000_000),first+100)=="observed"
        assert sum(x["rx"] for x in prev["buckets"].values())==100_000_000
        assert len(prev["buckets"])==2,"midnight split"
        assert sum(x["seconds"] for x in prev["buckets"].values())==100
        original=dict(prev["buckets"])
        assert meter.advance(prev,raw(first+100,1_100_000_000,50_000_000),first+100)=="duplicate"
        assert prev["buckets"]==original
        assert meter.advance(prev,raw(first+161,100,100,boot="1"*36),first+161)=="reset"
        assert prev["buckets"]==original
        assert meter.advance(prev,raw(first+222,40_000_100,10_000_100,boot="1"*36),first+222)=="observed"
        assert sum(x["rx"] for x in prev["buckets"].values())==140_000_000
        assert meter.advance(prev,raw(first+1000,50_000_100,11_000_100,boot="1"*36),first+1000)=="gap"
        assert sum(x["rx"] for x in prev["buckets"].values())==140_000_000
        assert prev["gaps"]==2
        for sid in ("maya1","maya-s3","maya4"):
            export=meter.make_export(sid,prev,{"state":"ok"},first+1000,
                                     datetime.fromtimestamp(first+1000,meter.ZONE).date())
            assert len(export["days"])==30
            assert len(export["days"][-1]["hours"])==24
            assert export["days"][-1]["rx_gb"] is not None
            assert export["gaps"]==2
        no=meter.make_export("maya-s3",{},{"state":"unavailable"},first+1000,
                             datetime.fromtimestamp(first+1000,meter.ZONE).date())
        assert no["state"]=="unavailable" and no["rx_today_gb"] is None
        today=datetime.fromtimestamp(first,meter.ZONE).date().isoformat()
        entry={}
        legacy={"day":today,"collected_at":first,
                "servers":{"maya1":{"state":"ok","rx_today_gb":5.2}}}
        meter.import_daily_carry(entry,"maya1",legacy,first,first)
        assert entry["carry_rx"]==5_200_000_000
        meter.advance(entry,raw(first,1_000_000_000),first)
        meter.advance(entry,raw(first+60,1_020_000_000),first+60)
        result=meter.make_export("maya1",entry,{"state":"ok"},first+60,
                                  datetime.fromtimestamp(first+60,meter.ZONE).date())
        assert abs(result["rx_today_gb"]-5.22)<0.00001,"do not regress valid V10 day total"
        assert result["days"][-1]["unallocated_rx_gb"]==5.2
        assert result["days"][-1]["hours"][23]["rx_gb"]==0.02
    print("PHYSICAL_NIC_HISTORY_SPLITS_RESETS_GAPS_CARRY=PASS")


def tests_control_room():
    # Reuse the existing end-to-end V10 template layering test, not a fake
    # hand-built approximation of the dashboard.
    data=runpy.run_path(str(ROOT/"scripts/test_control_room_compact_v10.py"))
    ns=data["ns"]; app=data["app"]; templates=data["templates"]; env=data["env"]
    app.router=types.SimpleNamespace(routes=[
        types.SimpleNamespace(path=p,methods=set(methods))
        for p,(fn,methods) in app.routes.items()])
    old_add=app.add_api_route
    def add(path,fn,methods):
        old_add(path,fn,methods)
        app.router.routes.append(types.SimpleNamespace(path=path,methods=set(methods)))
    app.add_api_route=add
    ns["render"]=lambda name,request,**kw:types.SimpleNamespace(
        status_code=200,template=name,context=kw)
    ui=(ROOT/"patches/control_room_traffic_analytics_v11.py").read_text(encoding="utf8")
    exec(compile(ui,"traffic-ui","exec"),ns)
    for path in ("/control-room/traffic/summary","/control-room/traffic/data/{server}",
                 "/control-room/traffic/{server}"):
        assert path in app.routes
    main=templates["control_room.html"]
    assert 'classList.add("th11-traffic-link")' in main
    assert 'fetch("/control-room/traffic/summary",' in main
    assert 'headers:{"X-Control-CSRF":t10CSRF}' in main
    assert "t10-compact-css" in main
    assert "/control-room/v9/topup" in main
    assert main.count('id="c2-cards"')==1
    token="C"*42
    class Req:
        def __init__(self,valid=True):
            self.session={"maya1_control_csrf":token}
            self.headers={"x-control-csrf":token if valid else "bad"}
    with tempfile.TemporaryDirectory() as folder:
        page=Path(folder)/"history.json"
        ns["_TH11_PATH"]=page
        assert ns["_th11_summary"](Req(False)).status_code==403
        assert ns["_th11_data"](Req(False),"maya1").status_code==403
        assert ns["_th11_data"](Req(),"xyz").status_code==404
        now=int(time.time())
        row={"state":"ok","rx_today_gb":2.2,"partial_day":True,"name":"maya1",
             "days":[]}
        page.write_text(json.dumps({"format":"MAYA_NIC_TRAFFIC_HISTORY_V11",
             "generated_at":now,"servers":{"maya1":row}}))
        assert json.loads(ns["_th11_summary"](Req()).body)["servers"]["maya1"]["rx_today_gb"]==2.2
        assert json.loads(ns["_th11_data"](Req(),"maya1").body)["server"]["name"]=="maya1"
        page.write_text(json.dumps({"format":"MAYA_NIC_TRAFFIC_HISTORY_V11",
             "generated_at":now-3600,"servers":{"maya1":row}}))
        assert ns["_th11_data"](Req(),"maya1").status_code==503
    page_template=templates["control_room_traffic_v11.html"]
    assert "traffic_server_id | tojson" in page_template
    assert "th11-hourly" in page_template and "th11-daily" in page_template
    # Explicitly render the chart's Jinja script and compile its JS.
    templates["base.html"]='{% block title %}{% endblock %}{% block heading %}{% endblock %}{% block subheading %}{% endblock %}{% block content %}{% endblock %}'
    from jinja2 import Environment,DictLoader
    page_html=Environment(loader=DictLoader(templates)).get_template(
        "control_room_traffic_v11.html").render(
            traffic_server_id="maya-s3",traffic_server_label="مایا ۳",ctrl_csrf=token)
    import re
    scripts=re.findall(r'<script[^>]*>([\s\S]*?)</script>',page_html)
    assert len(scripts)==1
    with tempfile.TemporaryDirectory() as folder:
        p=Path(folder)/"inline.js";p.write_text(scripts[0])
        subprocess.run(["node","--check",str(p)],check=True)
    assert "{{" not in page_html
    print("CHART_PAGE_DASHBOARD_CLICK_AUTH_JINJA_JS=PASS")


if __name__=="__main__":
    tests_meter()
    tests_control_room()
    print("MAYA_TRAFFIC_V11_OFFLINE_TESTS=PASS")
