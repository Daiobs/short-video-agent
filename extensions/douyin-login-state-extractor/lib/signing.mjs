import {
  MAX_REQUEST_BODY_BYTES,
  SCHEMA_VERSION,
  STORAGE_KEYS
} from "./constants.mjs";

const encoder = new TextEncoder();

export class SigningError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "SigningError";
    this.code = code;
  }
}

function bytesToHex(bytes) {
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join(
    ""
  );
}

function decodeSharedKey(value) {
  const encoded = String(value || "");
  if (!/^[A-Za-z0-9_-]{43}$/.test(encoded)) {
    throw new SigningError(
      "PAIRING_SECRET_INVALID",
      "本机配对密钥无效，请重新配对。"
    );
  }
  const base64 = encoded.replaceAll("-", "+").replaceAll("_", "/") + "=";
  let binary;
  try {
    binary = globalThis.atob(base64);
  } catch {
    throw new SigningError(
      "PAIRING_SECRET_INVALID",
      "本机配对密钥无效，请重新配对。"
    );
  }
  const bytes = Uint8Array.from(binary, (character) =>
    character.charCodeAt(0)
  );
  if (bytes.byteLength !== 32) {
    throw new SigningError(
      "PAIRING_SECRET_INVALID",
      "本机配对密钥无效，请重新配对。"
    );
  }
  return bytes;
}

export function createNonce(randomSource = globalThis.crypto) {
  if (!randomSource?.getRandomValues) {
    throw new SigningError(
      "CRYPTO_UNAVAILABLE",
      "当前浏览器不支持安全随机数。"
    );
  }
  const bytes = new Uint8Array(16);
  randomSource.getRandomValues(bytes);
  return Array.from(bytes, (byte) =>
    byte.toString(16).padStart(2, "0")
  ).join("");
}

export function canonicalSignedMessage({
  timestamp,
  nonce,
  bodyText
}) {
  return [
    String(timestamp || ""),
    String(nonce || ""),
    String(bodyText || "")
  ].join("\n");
}

export async function hmacSha256Hex(secret, message) {
  const key = await globalThis.crypto.subtle.importKey(
    "raw",
    decodeSharedKey(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const signature = await globalThis.crypto.subtle.sign(
    "HMAC",
    key,
    encoder.encode(String(message || ""))
  );
  return bytesToHex(new Uint8Array(signature));
}

export function assertRequestBodySize(bodyText) {
  const size = encoder.encode(String(bodyText || "")).byteLength;
  if (size > MAX_REQUEST_BODY_BYTES) {
    throw new SigningError(
      "REQUEST_BODY_TOO_LARGE",
      "同步请求超过 64 KiB，已拒绝发送。"
    );
  }
  return size;
}

export async function buildSignedHeaders({
  method,
  path,
  bodyText,
  sharedSecret,
  extensionVersion,
  now = Date.now(),
  nonce
}) {
  assertRequestBodySize(bodyText);
  const timestamp = String(Math.floor(now / 1000));
  const requestNonce = nonce || createNonce();
  const canonical = canonicalSignedMessage({
    timestamp,
    nonce: requestNonce,
    bodyText
  });
  const signature = await hmacSha256Hex(sharedSecret, canonical);

  return {
    "Content-Type": "application/json",
    "X-SVA-Schema-Version": String(SCHEMA_VERSION),
    "X-SVA-Extension-Version": String(extensionVersion || ""),
    "X-SVA-Timestamp": timestamp,
    "X-SVA-Nonce": requestNonce,
    "X-SVA-Signature": signature
  };
}

export function buildPersistedPairingState(sharedSecret, lastSyncedAt = "") {
  const secret = String(sharedSecret || "");
  decodeSharedKey(secret);
  return {
    [STORAGE_KEYS.sharedSecret]: secret,
    [STORAGE_KEYS.lastSyncedAt]: String(lastSyncedAt || "")
  };
}
