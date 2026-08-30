document.addEventListener("DOMContentLoaded",()=>{
  document.querySelectorAll("input[type=number]").forEach(el=>{
    el.addEventListener("wheel",e=>e.target.blur(),{passive:true});
  });
  const q=document.querySelector('.search input[name="q"]');
  if(q){window.addEventListener("keydown",e=>{if(e.key==="/" && document.activeElement!==q){e.preventDefault();q.focus();}})}

  document.querySelectorAll('[data-debt-toggle]').forEach(btn=>{
    btn.addEventListener('click',e=>{
      if(e.target.closest('[data-copy]')) return;
      const id=btn.dataset.debtToggle;
      const panel=document.querySelector(`[data-debt-panel="${id}"]`);
      if(!panel) return;
      const open=panel.hasAttribute('hidden');
      if(open){panel.removeAttribute('hidden');btn.classList.add('open');}
      else{panel.setAttribute('hidden','');btn.classList.remove('open');}
    });
  });

  document.querySelectorAll('[data-copy]').forEach(el=>{
    el.addEventListener('click',async e=>{
      e.preventDefault();e.stopPropagation();
      const text=el.dataset.copy||el.textContent.trim();
      try{await navigator.clipboard.writeText(text);}catch(_){
        const t=document.createElement('textarea');t.value=text;document.body.appendChild(t);t.select();document.execCommand('copy');t.remove();
      }
      const toast=document.getElementById('copy-toast');
      if(toast){toast.classList.add('show');clearTimeout(window.__copyTimer);window.__copyTimer=setTimeout(()=>toast.classList.remove('show'),1300);}
    });
  });
});
