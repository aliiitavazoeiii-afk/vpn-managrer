"use strict";
const toggle=document.getElementById("auto"),status=document.getElementById("status");
chrome.storage.local.get({autoSend:false}, v=>{toggle.checked=!!v.autoSend;});
toggle.addEventListener("change",async()=>{
 await chrome.storage.local.set({autoSend:toggle.checked});
 status.textContent=toggle.checked?"ارسال خودکار فعال شد؛ فقط پس از تست گیرنده و متن استفاده کن.":"حالت امن: پیش‌نویس + ارسال دستی";
});
document.getElementById("open").onclick=()=>chrome.tabs.create({url:"https://messages.google.com/web/conversations"});
