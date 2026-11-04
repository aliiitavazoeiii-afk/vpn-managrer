// Offline DOM regression: click alone causes mock network request; never real VPN.
const fs=require("fs"),vm=require("vm"),assert=require("assert");
const source=fs.readFileSync("patches/control_room_manual_path_test_v1.py","utf8");
const raw=source.split("_PT_SCRIPT=r'''")[1]?.split("'''")[0];
assert(raw);
const js=raw.replace(/<\/?script[^>]*>/g,"").replace("{{ ctrl_csrf }}","synthetic");
new vm.Script(js);
class Element{
 constructor(tag){this.tag=tag;this.children=[];this.textContent="";this.hidden=false;
 this.className="";this.disabled=false;this.listeners={};}
 appendChild(x){this.children.push(x);return x;}
 replaceChildren(...xs){this.children=xs;}
 addEventListener(name,fn){this.listeners[name]=fn;}
}
const btn=new Element("button"),box=new Element("div"),grid=new Element("div");
const ids=["maya1","maya-s3","maya4"];
const roles=["backhaul","mieru","haproxy"];
let run=0,pass=true,requests=[];
const fetch=async(url,options)=>{
 requests.push({url,options});
 if(url.endsWith("/path-test/start")){
  run++;
  return {ok:true,json:async()=>({ok:true,run_id:String(run).padStart(24,"0")})};
 }
 if(url.endsWith("/path-test/status")){
  const servers=Object.fromEntries(ids.map(id=>[
     id,Object.fromEntries(roles.map(role=>[
       role,(!pass&&id==="maya-s3"&&role==="mieru")?"warning":"healthy"
     ]))
  ]));
  return {ok:true,json:async()=>({ok:true,
      run_id:String(run).padStart(24,"0"),state:"completed",servers})};
 }
 throw Error("Unexpected mock route "+url);
};
const sandbox={
 document:{getElementById:id=>({
  "ocs-transfer-check":btn,"ocs-transfer-box":box,
  "ocs-transfer-grid":grid}[id]||null),
 createElement:tag=>new Element(tag)},window:{},
 fetch,console,setTimeout:fn=>Promise.resolve().then(fn)
};
vm.runInNewContext(js,sandbox);
assert.equal(requests.length,0,"page load MUST NOT start any download");
assert(typeof btn.listeners.click==="function");
(async()=>{
 await btn.listeners.click();
 assert.equal(grid.children.length,3,"3 Maya groups");
 assert(box.textContent.includes("سالم"),"all 9 healthy paths");
 assert(requests.some(r=>r.url.endsWith("/path-test/start")&&r.options.method==="POST"));
 assert.equal(grid.children.reduce((sum,col)=>sum+col.children.length-1,0),9);
 pass=false;
 await btn.listeners.click();
 assert(box.textContent.includes("هشدار"),"Maya3 Mieru warning");
 let col=grid.children[1];
 assert(col.children[2].children[1].textContent==="هشدار","Mieru alert displayed");
 assert(col.children[1].children[1].textContent==="سالم","Backhaul independent");
 assert(col.children[3].children[1].textContent==="سالم","HAProxy independent");
 console.log("MANUAL_PATH_TEST_BROWSER_MOCK_PASS");
})().catch(err=>{console.error(err);process.exit(1)});
