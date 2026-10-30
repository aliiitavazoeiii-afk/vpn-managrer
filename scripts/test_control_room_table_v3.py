#!/usr/bin/env python3
"""HESAB_CONTROL_ROOM_TABLE_V3_TEST: offline static and anomaly tests."""
import ast, importlib.util, json, sqlite3, subprocess, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
src=(ROOT/"patches/control_room_table_v3.py").read_text()
tree=ast.parse(src)
labels={}
for node in tree.body:
    if isinstance(node,ast.Assign):
        for t in node.targets:
            if isinstance(t,ast.Name) and t.id in ("_C3_CSS","_C3_TOOLBAR","_C3_JS"):
                labels[t.id]=ast.literal_eval(node.value)
assert set(labels)=={"_C3_CSS","_C3_TOOLBAR","_C3_JS"}
from jinja2 import Environment
assert "{#" not in labels["_C3_CSS"]
Environment().parse("".join(labels.values()))
with tempfile.TemporaryDirectory() as temp:
    output=Path(temp)/"v3.js"
    output.write_text(labels["_C3_JS"],encoding="utf-8")
    subprocess.run(["node","--check",str(output)],check=True)
    db=Path(temp)/"usage.sqlite3"
    with sqlite3.connect(db) as c:
        c.execute("""CREATE TABLE daily_usage (
            server TEXT,email TEXT,local_day TEXT,
            up INTEGER,down INTEGER,sample_count INTEGER)""")
        today=datetime.now(ZoneInfo("Asia/Tehran")).date()
        for n,gb in enumerate((1,1,1),start=1):
            day=(today-timedelta(days=n)).isoformat()
            c.execute("INSERT INTO daily_usage VALUES (?,?,?,?,?,?)",
                      ("maya1","example",day,int(gb*1024**3),0,275))
        c.commit()
    # Isolate the wrapper function without requiring the actual admin imports.
    func=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_cr2_one")
    unit=ast.Module(body=[func],type_ignores=[])
    base={"ok":True,"rows":[
        {"email":"example","usage_sampled":True,"today_bytes":int(4*1024**3)},
        {"email":"unknown","usage_sampled":True,"today_bytes":int(20*1024**3)}]}
    ns={
        "_C3_ORIGINAL_ONE": lambda server,db: json.loads(json.dumps(base)),
        "_CR2_DB": db, "_CR2_TZ": ZoneInfo("Asia/Tehran"),
        "_cr2_datetime": datetime, "_c3_timedelta": timedelta,
        "_c3_sqlite": sqlite3, "_C3_GIB":1024**3,
    }
    exec(compile(unit,"<anomaly_unit_test>","exec"),ns)
    rows=ns["_cr2_one"]("maya1",None)["rows"]
    assert rows[0]["anomaly"] is True and rows[0]["baseline_days"]==3
    assert rows[1]["anomaly"] is False and rows[1]["baseline_days"]==0
    base["rows"][0]["today_bytes"]=int(1.5*1024**3)
    rows=ns["_cr2_one"]("maya1",None)["rows"]
    assert rows[0]["anomaly"] is False
    # Missing usage history must not ever mark users anomalous.
    db.unlink()
    assert not ns["_cr2_one"]("maya1",None)["rows"][0]["anomaly"]
print("V3_PYTHON_JS_JINJA_ANOMALY_TESTS_OK")
