/* No phone-side gateway, no SMS API, no remote relay and no credentials.
   One explicitly clicked Hesab send -> a dedicated Google Messages Web tab. */
"use strict";

const TRUSTED_SITE = "https://hesab.filmjadiid.ir";
const GOOGLE_NEW = "https://messages.google.com/web/conversations/new";
let busy = false;

function validRequest(message, sender) {
  if (!sender || !sender.tab || typeof sender.url !== "string") return false;
  let site;
  try { site = new URL(sender.url); } catch (_) { return false; }
  if (site.origin !== TRUSTED_SITE) return false;
  if (message?.type !== "HESAB_SEND_IN_GOOGLE_MESSAGES") return false;
  if (!/^\+989\d{9}$/.test(message.phone || "")) return false;
  if (typeof message.message !== "string" || !message.message.trim() ||
      message.message.length > 1000) return false;
  if (!["debt", "manual"].includes(message.source)) return false;
  return true;
}

function tabReady(tabId) {
  return new Promise((resolve, reject) => {
    let resolved = false;
    const timer = setTimeout(() => {
      if (!resolved) {
        resolved = true; chrome.tabs.onUpdated.removeListener(listener);
        reject(new Error("GOOGLE_MESSAGES_LOAD_TIMEOUT"));
      }
    }, 25000);
    const listener = (id, info, tab) => {
      if (id !== tabId || info.status !== "complete") return;
      if (resolved) return;
      resolved = true;
      clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(listener);
      resolve(tab);
    };
    chrome.tabs.onUpdated.addListener(listener);
    chrome.tabs.get(tabId, tab => {
      if (chrome.runtime.lastError) return;
      if (tab?.status === "complete" && !resolved) {
        resolved = true; clearTimeout(timer);
        chrome.tabs.onUpdated.removeListener(listener);
        resolve(tab);
      }
    });
  });
}

/**
 * Runs in Google's MAIN world: Angular/Material observes native input/change
 * events there. No extension APIs, eval, remote code or Google credentials.
 * Fail closed: only auto-click Send after a matching phone option was selected.
 */
async function prepareGoogleCompose(phone, body, autoSend) {
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const digits = input => String(input || "")
    .replace(/[۰-۹]/g, ch => String("۰۱۲۳۴۵۶۷۸۹".indexOf(ch)))
    .replace(/[٠-٩]/g, ch => String("٠١٢٣٤٥٦٧٨٩".indexOf(ch)))
    .replace(/\D/g, "");
  const expected = digits(phone).slice(-10);
  const visible = el => {
    if (!el || !(el instanceof HTMLElement)) return false;
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 1 && rect.height > 1 &&
      style.display !== "none" && style.visibility !== "hidden";
  };
  const waitFor = async (get, timeout = 18000) => {
    const until = Date.now() + timeout;
    while (Date.now() < until) {
      const x = get();
      if (x) return x;
      await sleep(150);
    }
    return null;
  };
  const nativeSet = (el, value) => {
    el.focus();
    if (el instanceof HTMLTextAreaElement || el instanceof HTMLInputElement) {
      const proto = el instanceof HTMLTextAreaElement ?
        HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const set = Object.getOwnPropertyDescriptor(proto, "value")?.set;
      if (set) set.call(el, value);
      else el.value = value;
    } else if (el.isContentEditable) {
      el.textContent = value;
    } else throw new Error("NO_EDITABLE_INPUT");
    el.dispatchEvent(new InputEvent("input", {
      bubbles: true, composed: true, inputType: "insertText", data: value
    }));
    el.dispatchEvent(new Event("change", {bubbles:true, composed:true}));
  };

  if (location.hostname !== "messages.google.com" ||
      location.protocol !== "https:") {
    return {ok:false,code:"UNTRUSTED_GOOGLE_PAGE"};
  }

  if (location.pathname.includes("authentication") ||
      location.pathname.includes("welcome")) {
    return {ok:false,code:"PAIRING_REQUIRED",message:"Google Messages Web needs pairing"};
  }

  const recipientInput = await waitFor(() => {
    const choices = [...document.querySelectorAll(
      'input[placeholder], input[aria-label], input[role="combobox"], input[type="text"]'
    )].filter(visible);
    const preferred = choices.find(el =>
      /phone|recipient|name|email|to\b|number|شماره|مخاطب/i.test(
        (el.getAttribute("placeholder") || "") + " " +
        (el.getAttribute("aria-label") || "")
      ));
    if (preferred) return preferred;
    // In the new conversation route there is normally exactly one input.
    return choices.length === 1 ? choices[0] : null;
  }, 16000);

  if (!recipientInput) {
    return {ok:false,code:"RECIPIENT_INPUT_NOT_FOUND",
      message:"Google Messages may need pairing or its layout changed"};
  }
  if (recipientInput.value?.trim()) {
    return {ok:false,code:"EXISTING_RECIPIENT",
      message:"The recipient field is not empty; no changes made"};
  }

  nativeSet(recipientInput, phone);

  // Google Messages contact suggestions are asynchronous, and their custom
  // element/role layout may differ between releases. The old one-second
  // snapshot frequently missed an otherwise correct, visible suggestion.
  const findMatchingRecipientOption = () => {
    const selector = [
      "mws-contact-list-item", "mw-contact-list-item", "mat-option",
      '[data-e2e-contact-list-item]', '[role="option"]',
      '[role="listitem"]', '[class*="contact-list-item"]',
      '[class*="contact-result"]'
    ].join(", ");
    const rows = [...document.querySelectorAll(selector)].filter(visible)
      .filter(el => !el.contains(recipientInput));

    const numbersIn = el => {
      const raw = (el.innerText || el.textContent || "") + " " +
        (el.getAttribute("aria-label") || "");
      const latin = String(raw)
        .replace(/[۰-۹]/g, c => String("۰۱۲۳۴۵۶۷۸۹".indexOf(c)))
        .replace(/[٠-٩]/g, c => String("٠١٢٣٤٥٦٧٨٩".indexOf(c)));
      const matches = latin.match(/(?:\+?\s*98|0)?\s*9(?:[\s().-]*\d){9}(?!\d)/g) || [];
      return [...new Set(matches.map(value => digits(value).slice(-10)))];
    };
    const leafRows = rowsToReduce => rowsToReduce.filter(el =>
      !rowsToReduce.some(other => other !== el && el.contains(other))
    );

    // Highest confidence: a UNIQUE selectable row explicitly displays
    // exactly the requested phone, and no different phone.
    const verified = leafRows(rows.filter(el => {
      const phones = numbersIn(el);
      return phones.length === 1 && phones[0] === expected;
    }));
    if (verified.length === 1) return {el:verified[0], verified:true};
    if (verified.length > 1) return null;

    // Some Google releases display only a contact name. A sole explicit
    // contact suggestion may be opened as DRAFT ONLY; the phone is then
    // unverified and auto-send will be blocked even if enabled in the popup.
    const contactRows = leafRows(rows.filter(el => {
      const tag = el.tagName.toLowerCase();
      return tag.includes("contact") || tag === "mat-option" ||
        el.getAttribute("role") === "option" ||
        el.hasAttribute("data-e2e-contact-list-item");
    }));
    if (contactRows.length === 1 &&
        numbersIn(contactRows[0]).length === 0 &&
        digits(recipientInput.value).slice(-10) === expected) {
      return {el:contactRows[0], verified:false};
    }
    return null;
  };

  // Wait for Google's asynchronously rendered suggestions.
  const selection = await waitFor(findMatchingRecipientOption, 9000);
  if (selection) selection.el.click();

  // If the selector cannot recognize a row, allow the operator to click the
  // correct suggestion manually. Continue waiting and automatically populate
  // the Persian draft once the chat composer becomes available. Never send
  // automatically when the recipient was not verified from a phone-number row.

  const composer = await waitFor(() => {
    const candidates = [...document.querySelectorAll(
      'mws-autosize-textarea textarea, ' +
      'mws-message-compose textarea, textarea, ' +
      '[contenteditable="true"][role="textbox"], [contenteditable="true"]'
    )].filter(visible);
    return candidates.find(el => el instanceof HTMLTextAreaElement) ||
      candidates.find(el => el.isContentEditable) || null;
  }, selection ? 18000 : 28000);

  if (!composer) {
    return {ok:false,code:selection ? "COMPOSE_NOT_FOUND" : "MANUAL_RECIPIENT",
      message:selection
        ? "The suggestion was clicked but the chat composer did not appear; no message sent"
        : "Click the correct suggestion in Google Messages. No message was sent."};
  }

  const existing = composer instanceof HTMLTextAreaElement ?
    composer.value : composer.textContent;
  if (String(existing || "").trim()) {
    return {ok:false,code:"EXISTING_DRAFT",
      message:"The conversation already has a draft. Refusing to overwrite it."};
  }

  nativeSet(composer, body);
  await sleep(650);
  const typed = composer instanceof HTMLTextAreaElement ?
    composer.value : composer.textContent;
  if (typed !== body) {
    return {ok:false,code:"COMPOSE_TEXT_MISMATCH",
      message:"Google Messages did not accept the exact message text"};
  }

  // Without an exact phone shown in a matching contact row, do not permit
  // auto-send. The user must verify the destination and click Send manually.
  if (!selection?.verified) {
    return {ok:true,code:"DRAFT_READY_REVIEW_RECIPIENT",
      message:"Draft filled. Verify the recipient in Google Messages; click Send manually."};
  }
  if (!autoSend) {
    return {ok:true,code:"DRAFT_READY"};
  }

  // Auto-send only after exact recipient and exact message were matched.
  const sendButton = await waitFor(() => {
    const nodes = [...document.querySelectorAll(
      'button[data-e2e-send-text-button], ' +
      'mws-message-send-button button, ' +
      'mws-message-send-button[role="button"], ' +
      'button[aria-label*="send" i], button[title*="send" i]'
    )].filter(visible);
    return nodes.find(el => !el.disabled &&
      el.getAttribute("aria-disabled") !== "true") || null;
  }, 6000);

  if (!sendButton) {
    return {ok:true,code:"DRAFT_READY",
      message:"Send button not recognized; click it manually in Google Messages"};
  }

  // Exactly one automated click. Do not retry if the UI stays nonempty:
  // a retry might send twice after a delayed network response.
  sendButton.click();
  await sleep(1500);
  const after = composer instanceof HTMLTextAreaElement ?
    composer.value : composer.textContent;
  return after === "" ?
    {ok:true,code:"SUBMITTED"} :
    {ok:false,code:"AMBIGUOUS_SEND",
      message:"Send was clicked, but UI completion could not be confirmed"};
}

async function handleBridge(message) {
  if (busy) return {ok:false,code:"BUSY",
    message:"Another Google Messages request is in progress"};
  busy = true;
  try {
    // Idempotency and duplicate blocking now live in the authenticated
    // Hesab browser-intent endpoint, not in volatile extension memory.
    // One explicit click creates at most one server-guarded intent.
    const {autoSend} = await chrome.storage.local.get({autoSend:true});
    const tab = await chrome.tabs.create({url:GOOGLE_NEW,active:true});
    await tabReady(tab.id);
    const out = await chrome.scripting.executeScript({
      target:{tabId:tab.id}, world:"MAIN", injectImmediately:false,
      func:prepareGoogleCompose,
      args:[message.phone,message.message,!!autoSend]
    });
    const result=out?.[0]?.result || {ok:false,code:"NO_COMPOSE_RESULT"};
    return {...result, googleTabId:tab.id};
  } catch (error) {
    return {ok:false,code:"BROWSER_AUTOMATION_ERROR",
      message:String(error?.message || error).slice(0,200)};
  } finally {
    busy = false;
  }
}

chrome.runtime.onMessage.addListener((message,sender,sendResponse)=>{
  if (message?.type === "HESAB_FOCUS_ORIGINAL") {
    if (!sender?.tab?.id || !sender.url ||
        new URL(sender.url).origin !== TRUSTED_SITE) {
      sendResponse({ok:false});
      return false;
    }
    chrome.tabs.update(sender.tab.id,{active:true}).then(
      () => sendResponse({ok:true}),
      () => sendResponse({ok:false})
    );
    return true;
  }
  if (message?.type !== "HESAB_SEND_IN_GOOGLE_MESSAGES") return false;
  if (!validRequest(message,sender)) {
    sendResponse({ok:false,code:"UNAUTHORIZED_SITE_OR_INVALID_MESSAGE",
      message:"Only explicitly submitted SMS forms on Hesab are accepted"});
    return false;
  }
  handleBridge(message).then(sendResponse).catch(err =>
    sendResponse({ok:false,code:"UNEXPECTED_ERROR",
      message:String(err?.message || err).slice(0,150)}));
  return true;
});
