/* Hesab → Google Messages bridge. Runs ONLY at https://hesab.filmjadiid.ir/.
   Intercepts the old Android-Gateway form BEFORE it can enqueue/send.
   This script never submits the old form, updates finances or retries messages. */
(() => {
  "use strict";
  if (location.origin !== "https://hesab.filmjadiid.ir") return;

  const SEND_PATHS = new Set(["/sms/send", "/sms/debt-send"]);
  const normalize = raw => String(raw || "")
    .replace(/[۰-۹]/g, c => String("۰۱۲۳۴۵۶۷۸۹".indexOf(c)))
    .replace(/[٠-٩]/g, c => String("٠١٢٣٤٥٦٧٨٩".indexOf(c)))
    .replace(/[\s\-()]/g, "");
  let inFlight = false;
  let lastFingerprint = "";
  let lastAttemptTime = 0;

  function toast(message, kind = "info", form) {
    let banner = document.getElementById("hesab-gm-bridge-status");
    if (!banner) {
      banner = document.createElement("div");
      banner.id = "hesab-gm-bridge-status";
      banner.setAttribute("role", "status");
      banner.setAttribute("aria-live", "polite");
      banner.style.cssText = [
        "position:fixed", "bottom:22px", "left:20px", "right:20px",
        "max-width:540px", "margin:auto", "z-index:2147483647",
        "background:#10223e", "border:1px solid #87aefb",
        "color:#f8fafc", "padding:15px", "border-radius:14px",
        "box-shadow:0 15px 40px #000a",
        "font:600 13px/2 Tahoma,sans-serif", "direction:rtl",
        "white-space:pre-wrap"
      ].join(";");
      document.documentElement.appendChild(banner);
    }
    banner.style.borderColor = kind === "error" ? "#f87171" :
      kind === "ok" ? "#68d391" : "#87aefb";
    banner.textContent = message;
  }

  // Debt message textareas may sit outside their submit forms; some deployed
  // templates omit name=/form=. Select only the textarea for THIS customer.
  function readMessage(form, params) {
    const submitted = params.get("message");
    if (typeof submitted === "string" && submitted.trim()) {
      return submitted.trim();
    }

    const candidates = [];
    const add = field => {
      if ((field instanceof HTMLTextAreaElement ||
           field instanceof HTMLInputElement) && !candidates.includes(field)) {
        candidates.push(field);
      }
    };

    add(form.elements.namedItem("message"));
    add(form.querySelector('textarea[name="message"], input[name="message"]'));

    if (form.id === "sms-form") {
      add(form.querySelector("#sms-message"));
    }

    if (form.id) {
      add(document.querySelector(
        'textarea[form="' + CSS.escape(form.id) + '"]'
      ));
    }

    // Index-based lookup also works if the debt textarea is unassociated.
    const debtId = /^debt-sms-form-(\d+)$/.exec(form.id || "");
    if (debtId) {
      const expectedId = "debt-message-" + debtId[1];
      add(document.getElementById(expectedId));
      // The adjacent copy button is constrained to the same indexed field.
      const copy = form.closest(".debt-message-actions")
        ?.querySelector("[data-copy-target]");
      if (copy?.getAttribute("data-copy-target") === expectedId) {
        add(document.getElementById(expectedId));
      }
    }

    const found = candidates.find(field =>
      !field.disabled && typeof field.value === "string" && field.value.trim()
    );
    return found ? found.value.trim() : "";
  }

  function getFields(form) {
    const params = new FormData(form);
    let phone = normalize(params.get("phone"));
    let body = readMessage(form, params);
    if (phone.startsWith("0098")) phone = "0" + phone.slice(4);
    else if (phone.startsWith("98") && phone.length === 12) phone = "0" + phone.slice(2);
    else if (phone.startsWith("+98")) phone = "0" + phone.slice(3);
    else if (phone.length === 10 && phone.startsWith("9")) phone = "0" + phone;
    if (!/^09[0-9]{9}$/.test(phone)) {
      throw new Error("شماره موبایل ایرانی معتبر نیست.");
    }
    if (!body || body.length > 1000) {
      throw new Error(!body
        ? "متن پیامک این فرم پیدا نشد. هیچ پیامکی ارسال نشده؛ ساختار کادر متن را بررسی کن."
        : "متن پیامک بیشتر از ۱۰۰۰ کاراکتر دارد؛ هیچ پیامکی ارسال نشده.");
    }
    return {phone: "+98" + phone.slice(1), message:body};
  }

  function postToExtension(request) {
    return new Promise(resolve => {
      let done = false;
      const timeout = setTimeout(() => {
        if (!done) { done = true; resolve({ok:false, code:"TIMEOUT"}); }
      }, 45000);
      try {
        chrome.runtime.sendMessage(request, response => {
          if (done) return;
          done = true;
          clearTimeout(timeout);
          if (chrome.runtime.lastError) {
            resolve({ok:false,code:"EXTENSION_ERROR",detail:chrome.runtime.lastError.message});
          } else resolve(response || {ok:false,code:"NO_RESPONSE"});
        });
      } catch (e) {
        if (!done) {
          done = true; clearTimeout(timeout);
          resolve({ok:false,code:"EXTENSION_ERROR"});
        }
      }
    });
  }

  // Capture phase makes this handler run before the page's existing submit
  // handlers. If the extension intercepts, NO gateway POST is performed.
  document.addEventListener("submit", async event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    let pathname;
    try {
      const url = new URL(form.action, location.href);
      if (url.origin !== location.origin) return;
      pathname = url.pathname.replace(/\/+$/, "");
    } catch (_) { return; }
    if (!SEND_PATHS.has(pathname)) return;

    event.preventDefault();
    event.stopImmediatePropagation();
    event.stopPropagation();

    if (inFlight) {
      toast("یک پیام دیگر در حال آماده‌سازی است؛ لطفاً صبر کن.", "error", form);
      return;
    }

    let fields;
    try { fields = getFields(form); }
    catch (error) { toast(error.message, "error", form); return; }

    const fingerprint = fields.phone + "\u0000" + fields.message;
    if (lastFingerprint === fingerprint && Date.now() - lastAttemptTime < 120000) {
      toast("برای این شماره و متن اخیراً درخواست ارسال داده‌ای. برای جلوگیری از تکرار، دوباره ارسال نشد. مکالمه Google Messages را بررسی کن.", "error", form);
      return;
    }

    inFlight = true;
    lastFingerprint = fingerprint;
    lastAttemptTime = Date.now();
    toast("در حال انتقال پیام به Google Messages Web…\nهیچ موردی در صف قدیمی Gateway ثبت نمی‌شود.", "info", form);

    try {
      const result = await postToExtension({
        type:"HESAB_SEND_IN_GOOGLE_MESSAGES", phone:fields.phone,
        message:fields.message, source: pathname === "/sms/debt-send" ? "debt" : "manual"
      });
      if (result.ok && result.code === "SUBMITTED") {
        toast("درخواست ارسال در Google Messages Web ثبت شد.\nاین تأیید تحویل به گیرنده نیست؛ مکالمه را بررسی کن.\nوضعیت بدهی در پنل به‌طور خودکار تغییر نکرد.", "ok", form);
      } else if (result.ok && result.code === "DRAFT_READY") {
        toast("گیرنده و متن در Google Messages آماده شد.\nبرای ارسال نهایی روی دکمه Send در همان تب بزن.\nوضعیت بدهی در پنل به‌طور خودکار تغییر نکرد.", "ok", form);
      } else if (result.code === "MANUAL_RECIPIENT") {
        toast("Google Messages باز شد، اما انتخاب دقیق گیرنده به تأیید دستی نیاز دارد.\nگیرنده را انتخاب کن؛ سپس پیام را در Google Messages بفرست.\nفرم قدیمی حساب در صف قرار نگرفت.", "info", form);
      } else if (result.code === "AMBIGUOUS_SEND") {
        toast("وضعیت دکمه ارسال نامشخص است. به هیچ وجه دوباره کلیک نکن؛ ابتدا مکالمه Google Messages را بررسی کن.", "error", form);
      } else {
        toast("ارسال خودکار انجام نشد: " + (result.message || result.code || "خطای نامشخص") +
          "\nهیچ پیامکی در صف قدیمی ایجاد نشد. برای جلوگیری از تکرار، اول تب Google Messages را بررسی کن.", "error", form);
      }
    } finally { inFlight = false; }
  }, true);

  function badge() {
    if (!["/sms","/debts"].includes(location.pathname)) return;
    const id="hesab-gm-bridge-indicator";
    if(document.getElementById(id))return;
    const el=document.createElement("aside");
    el.id=id;
    el.textContent="● Google Messages Bridge فعال — ارسال از صف اندروید غیرفعال";
    el.style.cssText="padding:10px 15px;margin:12px 10px;background:#133b37;color:#d3fae8;border:1px solid #347d64;border-radius:12px;font:600 12px Tahoma,sans-serif;direction:rtl;text-align:center";
    (document.querySelector("main")||document.body).prepend(el);
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",badge,{once:true});
  else badge();
})();
