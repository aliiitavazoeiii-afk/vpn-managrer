/* Offline browser-DOM smoke test: prevents another empty-cards regression.
   Uses no network; fetch is stubbed to a synthetic local passive report. */
const fs=require("fs"),vm=require("vm"),assert=require("assert");
const source=fs.readFileSync("patches/control_room_passive_quality_v1.py","utf8");
let js=source.split("_PQ_JS=r'''")[1]?.split("'''")[0];
if(!js)throw Error("Quality JS block missing");
js=js.replace(/<\/?script[^>]*>/g,"").replace("{{ ctrl_csrf }}","synthetic");
class Element{
 constructor(tag){this.tag=tag;this.children=[];this.style={};this.textContent="";}
 appendChild(node){this.children.push(node);return node;}
 replaceChildren(...nodes){this.children=[...nodes];}
}
const cards=new Element("div");
const alerts=new Element("div");
const synthetic={
  source_at:1793782900,source_stale:false,alerts:[],servers:{}
};
for(const id of ["maya1","maya-s3","maya4"]){
 const paths={};
 for(const role of ["backhaul","mieru"]){
  paths[role]={ip:"8.8.8.8",health:"healthy",https_passed:3,
   https_total:3,https_avg_ms:230,
   quality:{state:"not_measured",confidence:"none"},
   latest_counters:null,trend:[],last_transfer_test:null};
 }
 synthetic.servers[id]={state:"ok",paths};
}
const globals={
  document:{
    getElementById:id=>id==="pq-cards"?cards:id==="pq-alerts"?alerts:null,
    createElement:tag=>new Element(tag)
  },
  window:{},
  fetch:async()=>({ok:true,json:async()=>({ok:true,report:synthetic})}),
  setInterval:()=>{},
  console
};
vm.runInNewContext(js,globals);
setImmediate(()=>{
 assert.strictEqual(cards.children.length,3,"three Maya server columns expected");
 for(const column of cards.children){
  assert.strictEqual(column.children.filter(n=>n.tag==="div").length,2,
    "two path cards per server expected");
 }
 assert(alerts.children.some(n=>n.textContent.includes("شواهد کافی")),
   "quality unknown must not be shown as healthy");
 console.log("PASSIVE_QUALITY_BROWSER_DOM=PASS");
});
