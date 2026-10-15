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

    // The header send button added by sms_nojump.py has NO form id.
    // Its message textarea is elsewhere in the SAME debtor group. Restrict
    // lookup to that group; multiple candidate textareas are ambiguous and
    // must NEVER result in sending a different customer's reminder.
    if (form.hasAttribute("data-debt-sms-form")) {
      const group = form.closest("[data-debt-group]");
      if (group) {
        const groupMessages = [...group.querySelectorAll(
          'textarea[id^="debt-message-"], textarea[form^="debt-sms-form-"]'
        )].filter((node, idx, list) => list.indexOf(node) === idx);
        if (groupMessages.length === 1) add(groupMessages[0]);
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

  async function postToBridge(path, payload) {
    let response;
    try {
      response = await fetch(path, {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
          "X-Hesab-Browser-Sms": "v1"
        },
        body: JSON.stringify(payload),
      });
    } catch (_error) {
      return {ok:false,code:"HESAB_SERVER_UNAVAILABLE"};
    }
    let data;
    try { data = await response.json(); }
    catch (_) { return {ok:false,code:"BRIDGE_BACKEND_NOT_INSTALLED"}; }
    return response.ok ? data :
      {ok:false,code:data?.code || "SERVER_REJECTED_REQUEST"};
  }

  function postToExtension(request) {
    return new Promise(resolve => {
      let done = false;
      const timeout = setTimeout(() => {
        if (!done) { done = true; resolve({ok:false, code:"TIMEOUT"}); }
      }, 85000);
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

    inFlight = true;
    toast("در حال بررسی درخواست با پنل حساب…\nهنوز هیچ پیامکی ارسال یا به صف اندروید اضافه نشده است.", "info", form);
    try {
      const source = pathname === "/sms/debt-send" ? "debt" : "manual";
      const intent = await postToBridge("/sms/browser/begin", {
        phone:fields.phone,message:fields.message,source
      });
      if (!intent.ok) {
        toast("درخواست جدید ثبت نشد: " + (intent.code || "SERVER_ERROR") +
          "\nبرای جلوگیری از ارسال تکراری، سوابق همان مخاطب را بررسی کن. هیچ پیامکی از این کلیک ارسال نشد.",
          "error", form);
        return;
      }
      // Server supplies the canonical reminder body. Never silently rely on
      // a potentially stale or modified frontend textarea for debt SMS.
      toast("در حال ارسال پیام از Google Messages…\nتا مشخص‌شدن نتیجه، دوباره کلیک نکن.", "info", form);
      const result = await postToExtension({
        type:"HESAB_SEND_IN_GOOGLE_MESSAGES",
        phone:intent.phone, message:intent.message, source
      });
      if (result.ok && result.code === "SUBMITTED") {
        // A browser-composer UI submission is NOT a verified delivery receipt.
        // Only this guarded server transition can move eligible debt accounts.
        const receipt = await postToBridge("/sms/browser/finish", {
          id:intent.id,token:intent.token,result:"SUBMITTED"
        });
        if (receipt.ok && receipt.status === "browser_submitted") {
          toast("Google Messages ارسال را در رابط خود ثبت کرد؛ تحویل به گیرنده هنوز تأیید نشده." +
            (source === "debt" ? "\n" + receipt.moved + " حساب به «در انتظار» منتقل شد." : ""),
            "ok", form);
          if (source === "debt" && receipt.moved > 0) {
            setTimeout(() => location.reload(), 1600);
          }
        } else {
          toast("در Google Messages دکمه ارسال اجرا شد، اما ثبت حسابداری قطعی نیست: " +
            (receipt.code || "UNKNOWN") +
            "\nپیام را دوباره ارسال نکن. ابتدا سوابق Google Messages و وضعیت حساب را بررسی کن.",
            "error", form);
        }
      } else {
        // We deliberately do NOT claim success or transition a debt on a draft,
        // a failed action, or a possibly successful but unconfirmed click.
        if (result.code === "AMBIGUOUS_SEND" || result.code === "TIMEOUT") {
          await postToBridge("/sms/browser/finish", {
            id:intent.id,token:intent.token,result:"UNKNOWN"
          });
        }
        const details = result.message || result.code || "نتیجه نامشخص";
        toast("ارسال خودکار تکمیل نشد: " + details +
          "\nممکن است پیش‌نویس آماده شده باشد. شماره را بررسی کن." +
          "\nبرای جلوگیری از تکرار، پیش از ارسال دوباره یا تغییر وضعیت، مکالمه را بررسی کن." +
          "\nدرخواست مرورگری ثبت شده، ولی هیچ رکوردی در صف اندروید نرفته است.",
          "error", form);
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
