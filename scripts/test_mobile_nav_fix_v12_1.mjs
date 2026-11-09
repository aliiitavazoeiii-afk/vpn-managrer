#!/usr/bin/env node
// Simulate actual v12 menu + v12.1 nav repair with an ancestor that creates
// a CSS stacking context; assert ALL original links remain clickable.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";

const source = readFileSync("patches/mobile_dashboard_admin_v12.py", "utf8");
const repair = readFileSync("patches/mobile_dashboard_nav_fix_v12_1.py", "utf8");
function extract(s,id) {
  const match=s.match(new RegExp('<script id="'+id+'">([\\s\\S]*?)<\\/script>'));
  assert.ok(match, "missing script "+id);
  return match[1];
}
const legacy=extract(source,"hm12-admin-menu");
const fixed=extract(repair,"hm121-sidebar-layer-script");
const links=[
  ["/","داشبورد"],["/debts","وصول بدهی"],["/followups","در انتظار"],
  ["/payments","پرداختی‌ها"],["/removed","حذفی‌ها"],["/control-room","اتاق کنترل"]
];
const originalLinks=links.map(([href,label])=>'<a href="'+href+'">'+label+'</a>').join("");
const dom=new JSDOM('<!doctype html><html lang="fa" dir="rtl"><head></head>'+
 '<body><div class="app" style="position:relative;transform:translateZ(0);z-index:1">'+
 '<aside class="sidebar"><div class="brand">حساب VPN</div>'+
 '<nav>'+originalLinks+'</nav></aside>'+
 '<main class="main"><h1>داشبورد</h1><table><tbody><tr><td>A</td></tr></tbody></table></main>'+
 '</div></body></html>',{
  url:"https://hesab.filmjadiid.ir/",pretendToBeVisual:true,
  runScripts:"outside-only"
 });
const win=dom.window, doc=win.document;
let mobile=true;
win.matchMedia=()=>({matches:mobile,addEventListener(){},removeEventListener(){}});
win.requestAnimationFrame=(fn)=>{fn();return 1};
win.eval(legacy);
win.eval(fixed);
await new Promise(resolve=>setTimeout(resolve,60));
const sidebar=doc.querySelector(".sidebar");
const toggle=doc.querySelector(".hm12-open-button");
const backdrop=doc.querySelector(".hm12-backdrop");
assert.ok(toggle&&backdrop,"mobile toggle/backdrop created");
assert.ok(doc.body.classList.contains("hm12-ready"),"mobile layout activated");
assert.equal(sidebar.parentElement,doc.body,"sidebar MUST be outside stacking context");
assert.equal(toggle.getAttribute("aria-expanded"),"false");
toggle.click();
assert.equal(toggle.getAttribute("aria-expanded"),"true");
assert.ok(doc.body.classList.contains("hm12-open"));
assert.equal(backdrop.hidden,false);
assert.equal(sidebar.inert,false);
for(const [href,label] of links){
  const el=[...sidebar.querySelectorAll("nav a")].find(a=>a.getAttribute("href")===href);
  assert.ok(el,"missing menu destination "+href);
  assert.equal(el.textContent,label);
}
backdrop.click();
assert.equal(toggle.getAttribute("aria-expanded"),"false");
assert.equal(backdrop.hidden,true);
toggle.click();
assert.ok(doc.body.classList.contains("hm12-open"),"second open failed");
const userLink=sidebar.querySelector('a[href="/control-room"]');
userLink.dispatchEvent(new win.MouseEvent("click",{bubbles:true,cancelable:true}));
assert.ok(!doc.body.classList.contains("hm12-open"),"link click should close menu");
mobile=false;
win.dispatchEvent(new win.Event("resize"));
assert.equal(sidebar.parentElement,doc.querySelector(".app"),
  "desktop sidebar must return to original layout");
assert.ok(!doc.body.classList.contains("hm12-open"));
const count=sidebar.querySelectorAll("nav a[href]").length;
assert.equal(count,links.length);
mobile=true;
win.dispatchEvent(new win.Event("resize"));
assert.equal(sidebar.parentElement,doc.body,"drawer must return to body on mobile");
toggle.click();
assert.ok(doc.body.classList.contains("hm12-open"));
doc.dispatchEvent(new win.KeyboardEvent("keydown",{key:"Escape",bubbles:true}));
assert.ok(!doc.body.classList.contains("hm12-open"),"Escape must close");
console.log("MOBILE_NAV_V12_1_BROWSER_DOM_REGRESSION=PASS");
console.log("ALL_SIX_MENU_LINKS_PRESERVED=YES");
console.log("STACKING_CONTEXT_ISOLATED=YES");
console.log("DESKTOP_LAYOUT_RESTORED=YES");
win.close();
