document.addEventListener("DOMContentLoaded",()=>{
  document.querySelectorAll("input[type=number]").forEach(el=>{
    el.addEventListener("wheel",e=>e.target.blur(),{passive:true});
  });
  const q=document.querySelector('.search input[name="q"]');
  if(q){window.addEventListener("keydown",e=>{if(e.key==="/" && document.activeElement!==q){e.preventDefault();q.focus();}})}
});
