document.addEventListener("DOMContentLoaded",()=>{
  document.querySelectorAll("input[type=number]").forEach(el=>{
    el.addEventListener("wheel",e=>e.target.blur(),{passive:true});
  });

  const normalizeDigits=value=>String(value||"")
    .replace(/[۰-۹]/g,d=>"0123456789"["۰۱۲۳۴۵۶۷۸۹".indexOf(d)])
    .replace(/[٠-٩]/g,d=>"0123456789"["٠١٢٣٤٥٦٧٨٩".indexOf(d)]);

  document.querySelectorAll("[data-money-input]").forEach(el=>{
    const format=()=>{
      const digits=normalizeDigits(el.value).replace(/\D/g,"");
      el.value=digits?Number(digits).toLocaleString("en-US"):"";
    };
    el.addEventListener("input",format);
    format();
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
  let applyDebtSearch=()=>{};
  if(debtSearch){
    const groups=[...document.querySelectorAll("[data-debt-group]")];
    const count=document.getElementById("debt-search-count");
    const empty=document.getElementById("debt-no-results");
    const faDigits=n=>String(n).replace(/\d/g,d=>"۰۱۲۳۴۵۶۷۸۹"[d]);

    applyDebtSearch=()=>{
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

    debtSearch.addEventListener("input",applyDebtSearch);
  }

  // Preserve the exact debt group, expanded panels, search text, and viewport offset
  // across POST -> 303 -> GET actions. This prevents every save from jumping to page top.
  if(location.pathname==="/debts"){
    const K={
      open:"hesab.debts.open",
      group:"hesab.debts.group",
      top:"hesab.debts.groupTop",
      y:"hesab.debts.scrollY",
      search:"hesab.debts.search"
    };
    const allGroups=()=>[...document.querySelectorAll("[data-debt-group]")];
    const keyOf=group=>group?.dataset.groupKey||"";

    const savePosition=form=>{
      try{
        const openKeys=allGroups().filter(group=>{
          const panel=group.querySelector("[data-debt-panel]");
          return panel && !panel.hasAttribute("hidden");
        }).map(keyOf).filter(Boolean);
        sessionStorage.setItem(K.open,JSON.stringify(openKeys));
        sessionStorage.setItem(K.y,String(window.scrollY));
        if(debtSearch) sessionStorage.setItem(K.search,debtSearch.value||"");

        const group=form.closest("[data-debt-group]");
        if(group && keyOf(group)){
          sessionStorage.setItem(K.group,keyOf(group));
          sessionStorage.setItem(K.top,String(group.getBoundingClientRect().top));
        }else{
          sessionStorage.removeItem(K.group);
          sessionStorage.removeItem(K.top);
        }
      }catch(_){}
    };

    document.querySelectorAll(".debt-desk form, form[data-preserve-position]").forEach(form=>{
      form.addEventListener("submit",()=>savePosition(form));
    });

    try{
      const savedSearch=sessionStorage.getItem(K.search);
      if(debtSearch && savedSearch!==null){
        debtSearch.value=savedSearch;
        applyDebtSearch();
      }

      let openKeys=[];
      try{openKeys=JSON.parse(sessionStorage.getItem(K.open)||"[]");}catch(_){}
      allGroups().forEach(group=>{
        if(!openKeys.includes(keyOf(group))) return;
        const panel=group.querySelector("[data-debt-panel]");
        const btn=group.querySelector("[data-debt-toggle]");
        if(panel) panel.removeAttribute("hidden");
        if(btn) btn.classList.add("open");
      });

      const savedGroup=sessionStorage.getItem(K.group);
      const savedTop=parseFloat(sessionStorage.getItem(K.top)||"NaN");
      const savedY=parseFloat(sessionStorage.getItem(K.y)||"0");

      requestAnimationFrame(()=>requestAnimationFrame(()=>{
        const target=savedGroup?allGroups().find(g=>keyOf(g)===savedGroup):null;
        if(target && Number.isFinite(savedTop)){
          const desired=target.getBoundingClientRect().top-savedTop;
          window.scrollTo(0,Math.max(0,desired));
        }else if(Number.isFinite(savedY) && savedY>0){
          window.scrollTo(0,savedY);
        }
        Object.values(K).forEach(k=>sessionStorage.removeItem(k));
      }));
    }catch(_){}
  }
});
