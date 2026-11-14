#!/usr/bin/env python3
"""V13 UI-only regression. Never reaches Production or active Maya tunnels."""
import re
import subprocess
import unittest
from pathlib import Path
from jinja2 import Environment

ROOT=Path(__file__).resolve().parents[1]
V2=(ROOT/"patches/control_room_v2.py").read_text()
V3=(ROOT/"patches/control_room_table_v3.py").read_text()
V13=ROOT/"patches/control_room_user_rows_v13.py"

def live_like_fixture():
    match=re.search(r"_CR2_TEMPLATE\s*=\s*r'''(.*?)'''",V2,re.S)
    assert match, "V2 template fixture missing"
    base=match.group(1)
    assert '<div id="c2-cards" class="c2-cards"></div>' in base
    base=base.replace('<div id="c2-cards" class="c2-cards"></div>',
        '<section id="p1-ops-root"></section>'+
        '<div id="c2-cards" class="c2-cards"></div>'+
        '<div id="p1-monitor"></div>',1)
    scope={
       "_cr2_one":lambda server,db:{"ok":True,"rows":[]},
       "TEMPLATES":{"control_room.html":base,"other.html":"Original unrelated UI"},
       "env":type("Env",(),{"loader":type("Loader",(),{"mapping":{}})()})(),
    }
    # Apply real V3 changes to V2's template instead of rewriting a test
    # fixture; this proves V13 targets actual V3 filter/rendering structure.
    exec(compile(V3,str(ROOT/"patches/control_room_table_v3.py"),"exec"),scope)
    actual=scope["TEMPLATES"]["control_room.html"]
    assert "function c3VisibleRows(rows,server)" in actual
    assert 'id="c3-mode"' in actual
    assert actual.count("{% endblock %}")>=2  # title and content Jinja blocks
    scope["TEMPLATES"]["control_room.html"]=actual.replace(
        "{% block content %}",
        '{% block content %}<style id="t10-compact-css"></style>',1)
    return scope

def patched():
    scope=live_like_fixture()
    old=scope["TEMPLATES"]["control_room.html"]
    original_one=scope["_cr2_one"]
    exec(compile(V13.read_text(),str(V13),"exec"),scope)
    return scope,old,original_one

class Tests(unittest.TestCase):
    def test_actual_v2_v3_template_compiles_and_patches_cleanly(self):
        scope,old,one=patched()
        new=scope["TEMPLATES"]["control_room.html"]
        Environment().parse(new)
        self.assertIs(scope["_cr2_one"],one,"backend XUI sampling must not change")
        self.assertEqual(scope["TEMPLATES"]["other.html"],"Original unrelated UI")
        self.assertEqual(new.count('id="r13-compact-list-style"'),1)
        self.assertEqual(new.count('id="c2-users"'),1)
        self.assertEqual(new.count('id="c3-mode"'),1)
        self.assertEqual(new.count('<option value="unmatched">'),1)
        self.assertIn('mode==="unmatched"',new)
        self.assertIn('filtered=filtered.filter(item=>!item.sid||item.control_ambiguous===true);',new)
        self.assertIn('c3LastMs(a.last_online)-c3LastMs(b.last_online)',new)
        self.assertIn('todayCell.title=item.usage_sampled?',new)
        self.assertIn("مصرف امروز برای ",new)
        self.assertIn('detailsButton.onclick=()=>c3Details(server,item)',new)
        self.assertIn('btn.onclick=()=>toggle(server,item,btn)',new)
        self.assertIn('link.href="/users/"+encodeURIComponent(item.sid)',new)
        self.assertIn('fetch("/control-room/v2/data"',new)
        self.assertIn('fetch("/control-room/maya-live/toggle"',new)
        self.assertIn('id="c2-top-today"',new)
        self.assertIn('id="c2-top-30"',new)
        self.assertIn("t10-compact-css",new)
        self.assertIn("control_room.html",scope["env"].loader.mapping)
    def test_safe_failure_if_template_or_mode_mismatched(self):
        scope=live_like_fixture()
        current=scope["TEMPLATES"]["control_room.html"]
        scope["TEMPLATES"]["control_room.html"]=current.replace(
             '<option value="today">','<option value="wrong">',1)
        with self.assertRaises(RuntimeError):
            exec(compile(V13.read_text(),str(V13),"exec"),scope)
        # Template is not assigned until all assertions and Jinja parsing pass.
        self.assertNotIn("r13-compact-list-style",scope["TEMPLATES"]["control_room.html"])
    def test_ui_css_shows_three_metrics_and_one_row_per_user(self):
        new=patched()[0]["TEMPLATES"]["control_room.html"]
        style=re.search(r'<style id="r13-compact-list-style">(.+?)</style>',new,re.S).group(1)
        self.assertIn("nth-child(4)",style,"Lifetime XUI up+down must be visible")
        self.assertIn("nth-child(5)",style,"Daily sampled data must be visible")
        self.assertIn("nth-child(8)",style,"Last connection must be visible")
        self.assertIn("nth-child(6)",style,"30-day usage remains in modal")
        self.assertIn("nth-child(7)",style,"Current sample rate remains in modal")
        self.assertIn("display:table-row!important",style)
        self.assertIn("display:grid!important",style)
        self.assertIn("grid-template-columns:repeat(2",style)
        self.assertIn("min-width:0!important",style)
        self.assertNotIn("background-image:url(",style)
        self.assertEqual(new.count('id="r13-compact-list-style"'),1)
    def test_all_three_mayas_keep_shared_source_and_switch_behavior(self):
        new=patched()[0]["TEMPLATES"]["control_room.html"]
        self.assertIn('["maya1","maya-s3","maya4"]',new)
        self.assertIn('state.modes[id]||"normal"',new)
        self.assertIn('state.queries[id]||""',new)
        self.assertIn('for(const item of c3VisibleRows(data.rows,server)){',new)
    def test_browser_filter_sort_js_against_real_v3_code(self):
        new=patched()[0]["TEMPLATES"]["control_room.html"]
        a=new.index("const c3Mode=document.getElementById")
        b=new.index("\nfunction renderCards(){",a)
        snippet=new[a:b]
        checks=r'''
const byID={"c3-mode":{value:"normal"},"c3-filter-info":{textContent:""}};
const document={getElementById:(id)=>byID[id]};
const state={query:""};
const normal=(s)=>String(s||"").toLowerCase().replace(/\s+/g,"");
const count=(n)=>String(n);
const now=Date.now();
const rows=[
 {email:"older",name:"Older",sid:null,control_ambiguous:false,
  last_online:now-160*3600*1000,usage_sampled:false},
 {email:"newer",name:"Newer",sid:42,control_ambiguous:false,
  last_online:now-50*3600*1000,usage_sampled:true,today_bytes:100},
 {email:"today",name:"Today",sid:33,control_ambiguous:false,
  last_online:now-2*3600*1000,usage_sampled:true,today_bytes:500},
 {email:"unknown",name:"Unknown",sid:null,control_ambiguous:false,
  last_online:0,usage_sampled:false},
 {email:"conflict",name:"Conflict",sid:66,control_ambiguous:true,
  last_online:now-70*3600*1000,usage_sampled:true}
];
function assert(ok,msg){if(!ok)throw Error(msg)}
byID["c3-mode"].value="unmatched";
assert(JSON.stringify(c3VisibleRows(rows,"maya1").map(x=>x.email))===
       JSON.stringify(["older","unknown","conflict"]),"unmatched selection");
state.query="unknown";
assert(c3VisibleRows(rows,"maya-s3")[0].email==="unknown","search and mode");
state.query="";
byID["c3-mode"].value="idle";
assert(JSON.stringify(c3VisibleRows(rows,"maya4").map(x=>x.email))===
       JSON.stringify(["older","conflict","newer"]),"48h oldest first");
byID["c3-mode"].value="unknown";
assert(c3VisibleRows(rows,"maya1")[0].email==="unknown","separate unknown time");
byID["c3-mode"].value="today";
assert(c3VisibleRows(rows,"maya1")[0].email==="today","sampled usage ordering");
byID["c3-mode"].value="normal";
assert(c3VisibleRows(rows,"maya1").length===5,"all rows preserved");
assert(byID["c3-filter-info"].textContent.includes("اندازه‌گیری نشده"),
       "missing sample disclosure");
console.log("V13_MAYA_ALL_FILTERS_SORT=PASS");
'''
        split=checks.index("const now=Date.now();")
        script=checks[:split]+"\n"+snippet+"\n"+checks[split:]
        p=subprocess.run(["node","-e",script],capture_output=True,
            text=True,timeout=15)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn("V13_MAYA_ALL_FILTERS_SORT=PASS",p.stdout)
    def test_no_backend_or_vpn_mutation_in_patch(self):
        src=V13.read_text()
        for forbidden in ("app.add_api_route","docker compose","subprocess.run",
                           "requests.","paramiko","sqlite3.connect","UPDATE ",
                           "DELETE FROM","toggle(","/usr/local/bin/dual",
                           "haproxy","_cr2_one="):
            self.assertNotIn(forbidden,src)
        self.assertIn('TEMPLATES["control_room.html"]=_R13_UPDATED',src)
if __name__=="__main__":
    unittest.main(verbosity=2)
