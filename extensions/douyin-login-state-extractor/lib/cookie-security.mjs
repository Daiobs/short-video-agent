import {
  ALLOWED_COOKIE_DOMAINS,
  DEFAULT_REFERER,
  MAX_COOKIE_COUNT,
  MAX_COOKIE_HEADER_BYTES,
  SCHEMA_VERSION
} from "./constants.mjs";

const COOKIE_NAME_PATTERN = /^[A-Za-z0-9_.-]{1,128}$/;
const COOKIE_VALUE_PATTERN = /^[\x21-\x3A\x3C-\x7E]*$/;
const LOGIN_COOKIE_NAMES = new Set([
  "sessionid",
  "sessionid_ss",
  "sid_guard",
  "sid_tt",
  "uid_tt",
  "uid_tt_ss"
]);

export class CookieCaptureError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "CookieCaptureError";
    this.code = code;
  }
}

export function isAllowedCookieDomain(domain) {
  return ALLOWED_COOKIE_DOMAINS.includes(String(domain || ""));
}

export function isSafeCookieName(name) {
  return COOKIE_NAME_PATTERN.test(String(name || ""));
}

export function isSafeCookieValue(value) {
  return COOKIE_VALUE_PATTERN.test(String(value ?? ""));
}

export function normalizeDouyinReferer(value) {
  try {
    const url = new URL(String(value || ""));
    const hostname = url.hostname.toLowerCase();
    if (
      url.protocol !== "https:" ||
      (hostname !== "douyin.com" && !hostname.endsWith(".douyin.com"))
    ) {
      return DEFAULT_REFERER;
    }
    url.hash = "";
    return url.href.length <= 2048 ? url.href : DEFAULT_REFERER;
  } catch {
    return DEFAULT_REFERER;
  }
}

export function buildDouyinCookieHeader(
  cookies,
  {
    maxCookieCount = MAX_COOKIE_COUNT,
    maxHeaderBytes = MAX_COOKIE_HEADER_BYTES
  } = {}
) {
  if (!Array.isArray(cookies)) {
    throw new CookieCaptureError(
      "COOKIE_CAPTURE_INVALID",
      "Chrome 未返回有效的 Cookie 列表。"
    );
  }

  const accepted = [];
  let rejectedCount = 0;

  for (const cookie of cookies) {
    if (
      !cookie ||
      !isAllowedCookieDomain(cookie.domain) ||
      !isSafeCookieName(cookie.name) ||
      !isSafeCookieValue(cookie.value)
    ) {
      rejectedCount += 1;
      continue;
    }
    accepted.push(cookie);
  }

  if (accepted.length > maxCookieCount) {
    throw new CookieCaptureError(
      "COOKIE_COUNT_LIMIT",
      `抖音 Cookie 字段超过 ${maxCookieCount} 条，已拒绝同步。`
    );
  }

  const cookieHeader = accepted
    .map((cookie) => `${cookie.name}=${cookie.value}`)
    .join("; ");
  const headerBytes = new TextEncoder().encode(cookieHeader).byteLength;

  if (headerBytes > maxHeaderBytes) {
    throw new CookieCaptureError(
      "COOKIE_HEADER_TOO_LARGE",
      "抖音 Cookie Header 超过 32 KiB，已拒绝同步。"
    );
  }

  const loginNames = new Set(
    accepted
      .map((cookie) => cookie.name)
      .filter((name) => LOGIN_COOKIE_NAMES.has(name))
  );

  return {
    cookieHeader,
    pairCount: accepted.length,
    loginKeyCount: loginNames.size,
    rejectedCount,
    headerBytes,
    containsHttpOnly: accepted.some((cookie) => cookie.httpOnly === true)
  };
}

export function buildSyncPayload(
  cookies,
  {
    userAgent,
    referer,
    capturedAt,
    extensionVersion
  }
) {
  const capture = buildDouyinCookieHeader(cookies);
  if (!capture.pairCount) {
    throw new CookieCaptureError(
      "DOUYIN_COOKIE_EMPTY",
      "没有读取到可同步的抖音 Cookie，请先在 Chrome 登录抖音。"
    );
  }

  return {
    schema_version: SCHEMA_VERSION,
    cookie_header: capture.cookieHeader,
    user_agent: String(userAgent || "").slice(0, 1024),
    referer: normalizeDouyinReferer(referer),
    captured_at: String(capturedAt || new Date().toISOString()),
    pair_count: capture.pairCount,
    login_key_count: capture.loginKeyCount,
    extension_version: String(extensionVersion || "")
  };
}

export function buildSafePreview(payload) {
  return {
    maskedCookie: payload?.cookie_header ? "********" : "未读取",
    pairCount: Number(payload?.pair_count || 0),
    loginKeyCount: Number(payload?.login_key_count || 0),
    userAgent: String(payload?.user_agent || ""),
    targetDomain: "douyin.com",
    capturedAt: String(payload?.captured_at || "")
  };
}
