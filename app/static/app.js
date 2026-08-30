document.addEventListener("DOMContentLoaded",()=>{
  document.querySelectorAll("input[type=number]").forEach(el=>{
    el.addEventListener("wheel",e=>e.target.blur(),{passive:true});
  });

  const q=document.querySelector('.search input[name="q"]');
  if(q){
    window.addEventListener("keydown",e=>{
      if(e.key==="/" && document.activeElement!==q){
        e.preventDefault();
        q.focus();
      }
    });
  }

  const toast=()=>{
    const el=document.getElementById("copy-toast");
    if(!el) return;
    el.classList.add("show");
    clearTimeout(window.__copyTimer);
    window.__copyTimer=setTimeout(()=>el.classList.remove("show"),1300);
  };

  const copyText=async text=>{
    try{
      await navigator.clipboard.writeText(text);
    }catch(_){
      const t=document.createElement("textarea");
      t.value=text;
      document.body.appendChild(t);
      t.select();
      document.execCommand("copy");
      t.remove();
    }
    toast();
  };

  document.querySelectorAll("[data-debt-toggle]").forEach(btn=>{
    btn.addEventListener("click",e=>{
      if(e.target.closest("[data-copy]") || e.target.closest("[data-copy-target]")) return;
      const id=btn.dataset.debtToggle;
      const panel=document.querySelector(`[data-debt-panel="${id}"]`);
      if(!panel) return;
      const open=panel.hasAttribute("hidden");
      if(open){
        panel.removeAttribute("hidden");
        btn.classList.add("open");
      }else{
        panel.setAttribute("hidden","");
        btn.classList.remove("open");
      }
    });
  });

  document.querySelectorAll("[data-copy]").forEach(el=>{
    el.addEventListener("click",e=>{
      e.preventDefault();
      e.stopPropagation();
      copyText(el.dataset.copy||el.textContent.trim());
    });
  });

  document.querySelectorAll("[data-copy-target]").forEach(el=>{
    el.addEventListener("click",e=>{
      e.preventDefault();
      e.stopPropagation();
      const target=document.getElementById(el.dataset.copyTarget);
      if(target) copyText(target.value||target.textContent||"");
    });
  });

  const debtSearch=document.getElementById("debt-search");
  if(debtSearch){
    const groups=[...document.querySelectorAll("[data-debt-group]")];
    const count=document.getElementById("debt-search-count");
    const empty=document.getElementById("debt-no-results");
    const faDigits=n=>String(n).replace(/\d/g,d=>"۰۱۲۳۴۵۶۷۸۹"[d]);

    const apply=()=>{
      const term=debtSearch.value.trim().toLowerCase();
      let visible=0;
      groups.forEach(group=>{
        const hay=(group.dataset.search||"").toLowerCase();
        const show=!term||hay.includes(term);
        group.hidden=!show;
        if(show) visible++;
      });
      if(count) count.textContent=`${faDigits(visible)} نتیجه`;
      if(empty) empty.hidden=visible!==0;
    };

    debtSearch.addEventListener("input",apply);
  }
});
