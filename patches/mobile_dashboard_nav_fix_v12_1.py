# HESAB_MOBILE_SIDEBAR_LAYER_FIX_V12_1
# Navigation presentation repair ONLY. Original sidebar elements and link
# handlers remain untouched. The drawer is relocated within the DOM when on
# mobile so no ancestor stacking context can place it behind the backdrop.
from jinja2 import Environment as _hm121_jinja

_HM121_CSS=r'''
<style id="hm121-sidebar-layer-style">
@media(max-width:860px){
 body.hm12-ready>#hm12-sidebar{
   position:fixed!important;display:block!important;box-sizing:border-box!important;
   width:min(84vw,320px)!important;min-width:0!important;
   max-width:320px!important;height:100dvh!important;
   inset:0 0 0 auto!important;z-index:10072!important;
   background:linear-gradient(180deg,#141633,#0a0d25)!important;
   opacity:1!important;isolation:isolate!important;
 }
 body.hm12-ready.hm12-open>#hm12-sidebar{
   visibility:visible!important;pointer-events:auto!important;
   transform:translate3d(0,0,0)!important;
 }
 body.hm12-ready>#hm12-sidebar nav{
   display:flex!important;flex-direction:column!important;
   position:relative!important;z-index:1!important;
   visibility:visible!important;opacity:1!important;
   gap:6px!important;width:100%!important;
 }
 body.hm12-ready>#hm12-sidebar nav a{
   display:flex!important;align-items:center!important;gap:9px!important;
   opacity:1!important;visibility:visible!important;
   min-height:48px!important;height:auto!important;
   width:100%!important;max-width:100%!important;
   color:#e2e3fb!important;
   font-size:14px!important;line-height:1.6!important;
   white-space:normal!important;text-decoration:none!important;
   overflow-wrap:anywhere!important;
 }
 body.hm12-ready>.hm12-backdrop{z-index:10070!important}
 body.hm12-ready>.hm12-top{z-index:10069!important}
}
@media(min-width:861px){
 body.hm12-ready>.hm12-backdrop,
 body.hm12-ready>.hm12-top{display:none!important}
}
</style>
'''

_HM121_JS=r'''
<script id="hm121-sidebar-layer-script">
(function(){
"use strict";
function fix(){
  const sidebar=document.querySelector(".sidebar");
  const toggle=document.querySelector(".hm12-open-button");
  const backdrop=document.querySelector(".hm12-backdrop");
  if(!sidebar||!toggle||!backdrop||
     !document.body.classList.contains("hm12-ready"))return;
  /* Keep original position for desktop and future resizing. */
  if(!sidebar.parentNode)return;
  const marker=document.createComment("hm121-original-sidebar-position");
  sidebar.parentNode.insertBefore(marker,sidebar);
  function moveToViewportRoot(){
    const mobile=window.matchMedia("(max-width: 860px)").matches;
    if(mobile){
      if(sidebar.parentNode!==document.body){
        document.body.appendChild(sidebar);
      }
    }else if(marker.parentNode&&sidebar.parentNode!==marker.parentNode){
      marker.parentNode.insertBefore(sidebar,marker.nextSibling);
    }
  }
  moveToViewportRoot();
  window.addEventListener("resize",moveToViewportRoot,{passive:true});
  /* The original toggle, backdrop and all navigation events remain active.
     Relocate before painting so the panel cannot sit behind the overlay. */
  toggle.addEventListener("click",moveToViewportRoot,{capture:true});
}
if(document.readyState==="loading"){
  document.addEventListener("DOMContentLoaded",fix,{once:true});
}else{
  fix();
}
})();
</script>
'''

_hm121_base=TEMPLATES.get("base.html","")
if (not isinstance(_hm121_base,str) or
    _hm121_base.count('id="hm12-admin-mobile"')!=1 or
    _hm121_base.count('id="hm12-admin-menu"')!=1 or
    "hm121-sidebar-layer-script" in _hm121_base or
    _hm121_base.count("</head>")!=1 or
    _hm121_base.count("</body>")!=1):
    raise RuntimeError("MOBILE_V12_1_NAV_TEMPLATE_MISMATCH")
_hm121_base=_hm121_base.replace("</head>",_HM121_CSS+"\n</head>",1)
_hm121_base=_hm121_base.replace("</body>",_HM121_JS+"\n</body>",1)
_hm121_jinja().parse(_hm121_base)
TEMPLATES["base.html"]=_hm121_base
if hasattr(env.loader,"mapping"):
    env.loader.mapping.update(TEMPLATES)
