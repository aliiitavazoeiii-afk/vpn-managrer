"use strict";
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const {test} = require("node:test");

// Exercise the real injected function without adding npm/browser dependencies.
// Browser integration still requires a paired Chrome test.
const source = fs.readFileSync(path.join(__dirname, "..", "hesab.js"), "utf8");
const start = source.indexOf("  function readMessage(form, params) {");
const end = source.indexOf("\n  function getFields(form) {", start);
assert(start >= 0 && end > start, "readMessage extraction should match actual content script");
const functionSource = source.slice(start, end);

class Textarea {
  constructor(value) { this.value = value; this.disabled = false; }
}
class Input {
  constructor(value) { this.value = value; this.disabled = false; }
}

function readFixture({id, submitted = "", local = null, external = null, fields = {}, linked = null}) {
  const named = fields.message || null;
  const form = {
    id,
    elements: {namedItem(name) { return name === "message" ? named : null; }},
    querySelector(selector) {
      if (selector === "#sms-message") return local;
      if (selector.includes('[name="message"]')) return local;
      return null;
    },
    closest(selector) {
      if (selector !== ".debt-message-actions" || !linked) return null;
      return {querySelector() {
        return {getAttribute(name) {return name === "data-copy-target" ? linked : null;}};
      }};
    },
  };
  const doc = {
    querySelector(selector) {
      if (external && selector.includes('[form="' + id + '"]')) return external;
      return null;
    },
    getElementById(fieldId) { return fields[fieldId] || null; },
  };
  const read = vm.runInNewContext(functionSource + "\nreadMessage;", {
    HTMLTextAreaElement: Textarea,
    HTMLInputElement: Input,
    CSS: {escape: value => value},
    document: doc,
  });
  return read(form, {get(name) {return name === "message" ? submitted : null;}});
}

test("plain SMS form uses the submitted Persian text", () => {
  assert.equal(readFixture({id:"sms-form", submitted:"سلام، تست فارسی"}), "سلام، تست فارسی");
});

test("manual composer can use its own textarea if FormData is blank", () => {
  assert.equal(readFixture({id:"sms-form", local:new Textarea("درود")}), "درود");
});

test("debt form can read corresponding textarea even without name/form attributes", () => {
  assert.equal(readFixture({id:"debt-sms-form-4", fields:{"debt-message-4":new Textarea("یادآوری تمدید")}}), "یادآوری تمدید");
});

test("externally associated textarea is still accepted", () => {
  assert.equal(readFixture({id:"debt-sms-form-0", external:new Textarea("متن خارجی")}), "متن خارجی");
});

test("never use another customer's textarea as fallback", () => {
  assert.equal(readFixture({id:"debt-sms-form-4", fields:{"debt-message-5":new Textarea("متن مشتری دیگر")}}), "");
});

test("only the exact matching debt index is read", () => {
  assert.equal(readFixture({
    id:"debt-sms-form-7", linked:"debt-message-7",
    fields:{"debt-message-7":new Textarea("برای همین مشتری")}
  }), "برای همین مشتری");
});
