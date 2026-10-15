"use strict";
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const {test} = require("node:test");

const source = fs.readFileSync(path.join(__dirname, "..", "background.js"), "utf8");
const start = source.indexOf("  const findMatchingRecipientOption = () => {");
const end = source.indexOf("\n  // Wait for Google's asynchronously rendered suggestions.", start);
assert(start >= 0 && end > start, "Recipient selector must be present in injected function");
const helper = source.slice(start, end);

function digits(input) {
  return String(input).replace(/[۰-۹]/g, c => String("۰۱۲۳۴۵۶۷۸۹".indexOf(c)))
    .replace(/[٠-٩]/g, c => String("٠١٢٣٤٥٦٧٨٩".indexOf(c)))
    .replace(/\D/g, "");
}

function makeRow(text, {tag = "MWS-CONTACT-LIST-ITEM", role = "", children = []} = {}) {
  const row = {
    innerText: text, textContent: text, tagName: tag,
    getAttribute(name) {return name === "role" ? role : null;},
    hasAttribute(name) {return name === "data-e2e-contact-list-item" && tag === "MWS-CONTACT-LIST-ITEM";},
    contains(other) {return other === this || children.some(child => child.contains(other));}
  };
  return row;
}

function identify(rows, input = "+989123456789", target = input) {
  const recipientInput = {value:input};
  const f = vm.runInNewContext(helper + "\nfindMatchingRecipientOption;", {
    document: {querySelectorAll() {return rows;}},
    recipientInput,
    visible() {return true;},
    digits,
    expected:digits(target).slice(-10),
  });
  return f();
}

test("explicit unique phone suggestion is verified", () => {
  const row = makeRow("Ali - +98 912 345 6789");
  const result = identify([row]);
  assert.equal(result.el, row);
  assert.equal(result.verified, true);
});

test("late-format local Persian phone is verified", () => {
  const row = makeRow("مخاطب\n۰۹۱۲ ۳۴۵ ۶۷۸۹");
  assert.equal(identify([row]).verified, true);
});

test("phone inside row with extra unrelated date still matches", () => {
  const row = makeRow("Ali 09123456789\nثبت 1405/07/23");
  assert.equal(identify([row]).verified, true);
});

test("a nested matching row is selected once, not seen as duplicate", () => {
  const leaf = makeRow("09123456789");
  const parent = makeRow("09123456789", {tag:"DIV",role:"listitem",children:[leaf]});
  const result = identify([parent, leaf]);
  assert.equal(result.el, leaf);
  assert.equal(result.verified, true);
});

test("a sole contact-name suggestion is draft-only, not verified", () => {
  const row = makeRow("مخاطب من", {tag:"DIV",role:"option"});
  const result = identify([row]);
  assert.equal(result.el, row);
  assert.equal(result.verified, false);
});

test("wrong phone must not be automatically selected", () => {
  const row = makeRow("دیگری 09125556677");
  assert.equal(identify([row]), null);
});

test("two separate suggestions with matching phone are ambiguous", () => {
  assert.equal(identify([
    makeRow("09123456789 - A"),makeRow("09123456789 - B")
  ]), null);
});

test("suggestion containing two different phone numbers is ambiguous", () => {
  const row=makeRow("09123456789 / 09129998877");
  assert.equal(identify([row]), null);
});

test("without a visible candidate nothing is clicked", () => {
  assert.equal(identify([]), null);
});

test("name-only suggestion is not selected if input does not match requested phone", () => {
  const row = makeRow("مخاطب من", {tag:"DIV",role:"option"});
  assert.equal(identify([row], "+989128887766", "+989123456789"), null);
});

test("unverified recipient must block automatic sending", () => {
  assert(source.includes('if (!selection?.verified)'));
  assert(source.indexOf("if (!selection?.verified)") <
         source.indexOf("sendButton.click();"));
  assert(source.includes('code:"DRAFT_READY_REVIEW_RECIPIENT"'));
});

test("manual contact selection still proceeds to filling draft", () => {
  assert(source.includes("selection ? 18000 : 28000"));
  assert(source.includes("nativeSet(composer, body);"));
});
