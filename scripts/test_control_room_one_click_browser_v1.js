const fs=require("fs"),vm=require("vm"),assert=require("assert");
const text=fs.readFileSync("patches/control_room_one_click_status_v1.py","utf8");
const raw=text.split("_OCS_UI = r'''")[1]?.split("'''")[0];
assert(raw,"one-click script missing");
const js=raw.split('<script id="ocs-js">')[1]?.split('</script>')[0];
assert(js,"one-click JS missing");
new vm.Script(js.replace("{{ ctrl_csrf }}","synthetic"));
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.textContent="";this.className="";this.disabled=false;this.listeners={};}
 appendChild(c){this.children.push(c);return c;}
 replaceChildren(...list){this.children=[...list];}
 addEventListener(name,handler){this.listeners[name]=handler;}
}
const roles=["backhaul","mieru"],ids=["maya1","maya-s3","maya4"];
const dual={
 ok:true,servers:Object.fromEntries(ids.map(id=>[id,{
 state:"ok",age_s:1,
 paths:Object.fromEntries(roles.map(role=>[role,{state:"healthy"}]))
 }]))
};
const cards=new Element("div"),button=new Element("button"),
 status=new Element("div"),foot=new Element("div");
let quality={
 ok:true,report:{source_stale:false,source_at:Math.floor(Date.now()/1000),
 servers:Object.fromEntries(ids.map(id=>[id,{paths:{
 backhaul:{quality:{state:"not_measured"}},
 mieru:{quality:{state:"not_measured"}}
 }}]))}
};
let fetchCalls=[];
const fetch=async (url,opts)=>{
 fetchCalls.push({url,opts});
 if(url.includes("refresh-meta"))return {ok:true,json:async()=>({ok:true,snapshot_mtime_ms:200})};
 if(url.endsWith("/refresh"))return {ok:true,json:async()=>({ok:true,accepted:true,previous_snapshot_mtime_ms:100})};
 if(url.endsWith("/dual-hourly/status"))return {ok:true,json:async()=>dual};
 if(url.endsWith("/dual-quality/status"))return {ok:true,json:async()=>quality};
 throw Error("Unknown mock API");
};
const context={
 document:{
 getElementById(id){return {"ocs-check":button,"ocs-status":status,
 "ocs-grid":cards,"ocs-foot":foot}[id]||null;},
 createElement(tag){return new Element(tag);}
 },window:{},fetch,
 setTimeout(fn){Promise.resolve().then(fn);},console
};
vm.runInNewContext(js.replace("{{ ctrl_csrf }}","synthetic"),context);
assert(status.textContent.includes("برای بررسی"),"must wait for click");
assert.equal(cards.children.length,0,"no pre-click status");
(async()=>{
 await button.listeners.click();
 assert.equal(cards.children.length,3,"3 Maya rows");
 assert(status.textContent.includes("اتصال هر شش مسیر سالم"),"green only for connectivity");
 assert(foot.textContent.includes("کیفیت واقعی انتقال داده"),"must disclose unknown throughput");
 const first=cards.children[0].children[1].children[1];
 assert(first.textContent==="سالم","healthy path");
 assert(fetchCalls.some(item=>item.url.endsWith("/refresh")&&item.opts.method==="POST"),"manual refresh must trigger fixed route");
 quality.report.servers["maya-s3"].paths.mieru.quality.state="suspected_degradation";
 await button.listeners.click();
 assert(status.textContent.includes("هشدار"),"quality suspicion must show warning");
 const second=cards.children[1].children[2].children[1];
 assert(second.textContent==="هشدار کیفیت","Maya3 Mieru warning");
 dual.servers.maya4.paths.mieru.state="down";
 await button.listeners.click();
 const third=cards.children[2].children[2].children[1];
 assert(third.textContent==="هشدار اتصال","Maya4 Mieru down warning");
 console.log("ONE_CLICK_STATUS_BROWSER_MOCK_PASS");
})().catch(error=>{console.error(error);process.exit(1)});
