import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import {
  buildDouyinCookieHeader,
  buildSafePreview,
  buildSyncPayload,
  isAllowedCookieDomain,
  isSafeCookieName
} from "./lib/cookie-security.mjs";
import {
  buildPersistedPairingState,
  buildSignedHeaders,
  canonicalSignedMessage,
  hmacSha256Hex
} from "./lib/signing.mjs";

const root = fileURLToPath(new URL(".", import.meta.url));
const sharedKey = "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE";
const manifest = JSON.parse(
  await readFile(new URL("manifest.json", import.meta.url), "utf8")
);

assert.deepEqual(manifest.permissions, ["cookies", "storage", "activeTab"]);
assert.deepEqual(manifest.host_permissions, [
  "https://www.douyin.com/*",
  "https://*.douyin.com/*",
  "http://127.0.0.1:8765/*"
]);
assert.equal(manifest.manifest_version, 3);
assert.equal(manifest.background.type, "module");
assert.equal(manifest.action.default_popup, "popup.html");

for (const forbidden of [
  "<all_urls>",
  "history",
  "debugger",
  "webRequest",
  "clipboardRead"
]) {
  assert.equal(manifest.permissions.includes(forbidden), false);
}

assert.equal(isAllowedCookieDomain("douyin.com"), true);
assert.equal(isAllowedCookieDomain(".douyin.com"), true);
assert.equal(isAllowedCookieDomain("www.douyin.com"), false);
assert.equal(isAllowedCookieDomain(".evil-douyin.com"), false);
assert.equal(isSafeCookieName("sessionid_ss"), true);
assert.equal(isSafeCookieName("bad name"), false);
assert.equal(isSafeCookieName("bad;name"), false);

const ordered = buildDouyinCookieHeader([
  {
    domain: ".douyin.com",
    name: "second",
    value: "2",
    httpOnly: true
  },
  {
    domain: ".example.com",
    name: "foreign",
    value: "no"
  },
  {
    domain: "douyin.com",
    name: "sessionid",
    value: "first-value"
  },
  {
    domain: ".douyin.com",
    name: "bad name",
    value: "no"
  },
  {
    domain: ".douyin.com",
    name: "third",
    value: "3"
  }
]);
assert.equal(ordered.cookieHeader, "second=2; sessionid=first-value; third=3");
assert.equal(ordered.pairCount, 3);
assert.equal(ordered.loginKeyCount, 1);
assert.equal(ordered.rejectedCount, 2);
assert.equal(ordered.containsHttpOnly, true);

assert.throws(
  () =>
    buildDouyinCookieHeader(
      Array.from({ length: 257 }, (_, index) => ({
        domain: ".douyin.com",
        name: `key${index}`,
        value: "value"
      }))
    ),
  (error) => error.code === "COOKIE_COUNT_LIMIT"
);

assert.throws(
  () =>
    buildDouyinCookieHeader([
      {
        domain: ".douyin.com",
        name: "oversized",
        value: "x".repeat(33 * 1024)
      }
    ]),
  (error) => error.code === "COOKIE_HEADER_TOO_LARGE"
);

const payload = buildSyncPayload(
  [
    {
      domain: ".douyin.com",
      name: "sessionid",
      value: "sensitive-value",
      httpOnly: true
    }
  ],
  {
    userAgent: "Test Browser",
    referer: "https://www.douyin.com/user/example#fragment",
    capturedAt: "2026-07-24T00:00:00.000Z",
    extensionVersion: "1.0.0"
  }
);
assert.equal(payload.cookie_header, "sessionid=sensitive-value");
assert.equal(payload.referer, "https://www.douyin.com/user/example");
assert.equal(payload.pair_count, 1);

const preview = buildSafePreview(payload);
assert.equal(preview.maskedCookie, "********");
assert.equal(JSON.stringify(preview).includes("sensitive-value"), false);

const persisted = buildPersistedPairingState(sharedKey, "recent");
assert.deepEqual(Object.keys(persisted).sort(), [
  "last_synced_at",
  "pairing_shared_secret"
]);
assert.equal(JSON.stringify(persisted).includes("cookie_header"), false);
assert.equal(JSON.stringify(persisted).includes("sensitive-value"), false);

const canonical = canonicalSignedMessage({
  timestamp: "123",
  nonce: "abc",
  bodyText: "{\"ok\":true}"
});
assert.equal(
  canonical,
  "123\nabc\n{\"ok\":true}"
);

const signatureA = await hmacSha256Hex(sharedKey, canonical);
const signatureB = await hmacSha256Hex(sharedKey, canonical);
assert.match(signatureA, /^[a-f0-9]{64}$/);
assert.equal(signatureA, signatureB);
assert.equal(
  signatureA,
  "d4c011969359085411c3c3bf83e71e627a734afe8ddf2e7be48196edab067bdf"
);

const signedHeaders = await buildSignedHeaders({
  bodyText: "{\"ok\":true}",
  sharedSecret: sharedKey,
  extensionVersion: "1.0.0",
  now: 123000,
  nonce: "00112233445566778899aabbccddeeff"
});
assert.equal(signedHeaders["X-SVA-Timestamp"], "123");
assert.equal(
  signedHeaders["X-SVA-Nonce"],
  "00112233445566778899aabbccddeeff"
);
assert.match(signedHeaders["X-SVA-Signature"], /^[a-f0-9]{64}$/);

const popupSource = await readFile(new URL("popup.js", import.meta.url), "utf8");
assert.match(
  popupSource,
  /chrome\.cookies\.getAll\(\{\s*url:\s*"https:\/\/www\.douyin\.com\/aweme\/v1\/web\/aweme\/post\/"\s*\}\)/
);
assert.equal(popupSource.includes("clipboard"), false);
assert.equal(popupSource.includes("chrome.storage"), false);

const workerSource = await readFile(
  new URL("service-worker.js", import.meta.url),
  "utf8"
);
assert.equal(workerSource.includes("console."), false);
assert.equal(workerSource.includes("redirect: \"error\""), true);

const popupHtml = await readFile(new URL("popup.html", import.meta.url), "utf8");
assert.equal(/<script[^>]+https?:\/\//i.test(popupHtml), false);
assert.equal(popupHtml.includes("复制 Cookie"), false);

console.log(`Extension self-test passed: ${root}`);
