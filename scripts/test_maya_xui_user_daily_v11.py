#!/usr/bin/env python3
"""Offline regression: per-client XUI traffic by Tehran calendar day."""
import importlib.util
import json
import sqlite3
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

from jinja2 import Environment

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"scripts/maya_xui_user_daily_v11.py"
PATCH=ROOT/"patches/control_room_xui_daily_usage_v11.py"
INSTALL=ROOT/"scripts/install_maya_xui_user_daily_v11.sh"

spec=importlib.util.spec_from_file_location("xui_daily_v11",SRC)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def stamp(y,m,d,h,minute,sec=0):
    return int(datetime(y,m,d,h,minute,sec,tzinfo=mod.TZ).timestamp())

def item(server,ts,data):
    return {"server":server,"observed_at":ts,
            "clients":{name:(up,down) for name,(up,down) in data.items()}}

class Tests(TestCase):
    def setUp(self):
        self.conn=sqlite3.connect(":memory:")
        self.conn.executescript(mod.DDL)
        self.dir=tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.orig_db=mod.DB
        mod.DB=Path(self.dir.name)/"day.sqlite3"
        self.addCleanup(lambda:setattr(mod,"DB",self.orig_db))
    def rows(self,day,server="maya-s3"):
        return self.conn.execute(
          "SELECT up,down,samples,first_sample,last_sample,reset_count,"
          "gap_count,boundary_unassigned,new_baselines "
          "FROM day_v11 WHERE server=? AND day=?",
          (server,day)).fetchone()
    def test_daily_only_xui_counters_plus_out_and_no_nic(self):
        a=stamp(2026,11,7,0,0,10)
        mod.update(self.conn,item("maya-s3",a,{"a":(100,300),"b":(200,400)}))
        b=a+60
        mod.update(self.conn,item("maya-s3",b,{"a":(150,500),"b":(250,450)}))
        day=mod.local_day(a)
        row=self.rows(day)
        self.assertEqual((row[0],row[1]),(100,250))
        self.assertEqual(row[2],2)
        self.assertEqual(mod.midnight(a),stamp(2026,11,7,0,0))
        self.assertEqual(mod.RETENTION,45)
        self.assertNotIn("rx_period_gb",SRC.read_text())
    def test_exact_tehran_midnight_crossing_is_not_assigned(self):
        before=stamp(2026,11,7,23,59,50)
        after=stamp(2026,11,8,0,0,13)
        mod.update(self.conn,item("maya1",before,{"one":(1000,1200)}))
        mod.update(self.conn,item("maya1",after,{"one":(2000,2200)}))
        mod.update(self.conn,item("maya1",after+60,{"one":(2500,2500)}))
        row=self.rows("2026-11-08","maya1")
        self.assertEqual((row[0],row[1]),(500,300))
        self.assertEqual(row[7],1)  # boundary_unassigned, never guessed
        self.assertNotEqual(self.rows("2026-11-07","maya1")[0],1000)
    def test_reset_counts_only_post_reset_lower_bound(self):
        a=stamp(2026,11,7,9,0)
        mod.update(self.conn,item("maya4",a,{"one":(10000,10000)}))
        mod.update(self.conn,item("maya4",a+60,{"one":(800,400)}))
        row=self.rows("2026-11-07","maya4")
        self.assertEqual((row[0],row[1]),(800,400))
        self.assertEqual(row[5],2)
    def test_missing_client_does_not_leak_old_baseline_to_recreated_user(self):
        a=stamp(2026,11,7,8,0)
        mod.update(self.conn,item("maya1",a,{"one":(1000,2000),"two":(1000,2000)}))
        mod.update(self.conn,item("maya1",a+60,{"one":(1500,2500)}))
        mod.update(self.conn,item("maya1",a+120,{"one":(1700,2600),"two":(30000,35000)}))
        row=self.rows("2026-11-07","maya1")
        self.assertEqual((row[0],row[1]),(700,600))
        self.assertEqual(row[8],3)  # two first users plus returning two
    def test_large_same_day_gap_is_not_fabricated_even_if_monotone(self):
        a=stamp(2026,11,7,7,0)
        mod.update(self.conn,item("maya-s3",a,{"one":(100,100)}))
        mod.update(self.conn,item("maya-s3",a+3600,{"one":(1000,500)}))
        row=self.rows("2026-11-07")
        self.assertEqual((row[0],row[1]),(900,400))
        self.assertEqual(row[6],1)
    def test_sample_must_advance_and_reject_invalid_clients(self):
        a=stamp(2026,11,7,10,0)
        mod.update(self.conn,item("maya1",a,{"one":(0,0)}))
        with self.assertRaises(ValueError):
            mod.update(self.conn,item("maya1",a,{"one":(1,1)}))
    def test_read_only_check_no_db_writes(self):
        s=item("maya1",stamp(2026,11,7,10,0),{"a":(100,150)})
        with patch.object(mod,"payload",side_effect=lambda name:dict(s,server=name)):
            result=mod.run(["--check"])
        self.assertEqual(result,0)
        self.assertFalse(mod.DB.exists())
    def test_summary_is_truthful_if_maya3_missing(self):
        with sqlite3.connect(mod.DB) as con:
            con.executescript(mod.DDL)
        summary=mod.collect(today="2026-11-07",errors={"maya-s3":"RuntimeError"})
        self.assertEqual(summary["servers"]["maya-s3"]["state"],"unavailable")
        self.assertEqual(summary["servers"]["maya1"]["state"],"not_measured")
    def test_valid_summary_not_exact_midnight_derived(self):
        a=stamp(2026,11,7,0,0,4)
        with sqlite3.connect(mod.DB) as con:
            con.executescript(mod.DDL)
            mod.update(con,item("maya-s3",a,{"one":(100,100)}))
            mod.update(con,item("maya-s3",a+60,{"one":(250,400)}))
        with patch.object(mod.time,"time",return_value=a+61):
            summary=mod.collect(today="2026-11-07")
        value=summary["servers"]["maya-s3"]
        self.assertEqual(value["total_bytes"],450)
        self.assertEqual(value["state"],"partial")
        self.assertIs(value["complete_day_exact"],False)
        self.assertEqual(summary["servers"]["maya4"]["state"],"not_measured")
    def test_source_is_readonly_xui_bridge(self):
        s=SRC.read_text()
        self.assertIn('{"op":"snapshot","server":server}',s)
        for prohibited in ("maya_daily_nic_v10","rx_today_gb","UPDATE subscriptions",
                           "updateClient","restart haproxy","systemctl restart"):
            self.assertNotIn(prohibited,s)
    def test_ui_only_changes_daily_display_not_quota(self):
        template=('''{% block content %}
<style id="t10-compact-css"></style>
<script>
const t10CSRF="{{ ctrl_csrf }}";
const response=await fetch("/control-room/v10/daily",
    {credentials:"same-origin",cache:"no-store"});
const today=day.state==="ok"?t10FormatGB(day.rx_today_gb):"—";
c4CardLabel("ترافیک روز",today,values);
if(day.partial_day===true){
values.lastElementChild.title="مصرف RX فقط از شروع ثبت در امروز است؛ کل روز نیست.";
}else{
values.lastElementChild.title="مصرف RX کارت شبکه در روز تهران";
}
</script>
{% endblock %}''')
        class App:
            def __init__(self):self.router=type("Router",(),{"routes":[]})()
            def add_api_route(self,path,func,methods):
                self.router.routes.append(type("Route",(),{"path":path})())
        env=Environment();pages={"control_room.html":template}
        ns={"app":App(),"TEMPLATES":pages,"env":env,
            "_dh1_auth":lambda request:False}
        exec(compile(PATCH.read_text(),str(PATCH),"exec"),ns)
        new=pages["control_room.html"]
        self.assertIn("مصرف کاربران امروز",new)
        self.assertIn("X-Control-CSRF",new)
        self.assertIn("users-daily",new)
        self.assertNotIn("rx_today_gb",new)
        self.assertNotIn("ترافیک روز",new)
        Environment().parse(new)
        self.assertEqual(ns["app"].router.routes[0].path,
                         "/control-room/v11/users-daily")
    def test_guarded_installer_changes_only_account_host(self):
        code=INSTALL.read_text()
        for token in ("MAYA1_MAYA3_MAYA4_XUI_READ=PASS",
                      "FIRST_BASELINE=VERIFIED_NO_HISTORICAL_BACKFILL",
                      "BACKUP=","--no-build --force-recreate app",
                      "XUI_TUNNELS_HAPROXY_PAYMENT_DB_CHANGED=NO"):
            self.assertIn(token,code)
        self.assertNotIn("docker compose down",code)
        self.assertNotIn("systemctl restart haproxy",code)
        self.assertNotIn("pip install",code)
if __name__=="__main__":
    main(verbosity=2)
