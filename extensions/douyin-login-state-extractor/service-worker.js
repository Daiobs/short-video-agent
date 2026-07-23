import {
  API_ORIGIN,
  API_PATHS,
  MESSAGE_TYPES,
  SCHEMA_VERSION,
  STORAGE_KEYS
} from "./lib/constants.mjs";
import {
  buildPersistedPairingState,
  buildSignedHeaders
} from "./lib/signing.mjs";

const SAFE_ERROR_MESSAGES = Object.freeze({
  API_UNAVAILABLE: "无法连接本机 short-video-agent，请确认服务正在运行。",
  CLEAR_FAILED: "清除失败，请确认本机服务和配对状态。",
  DOUYIN_LOGIN_REQUIRED: "没有识别到有效登录态，请先在 Chrome 登录抖音。",
  INVALID_RESPONSE: "本机服务返回了无法识别的响应。",
  LOCAL_HELPER_FORBIDDEN: "本地登录状态接口只允许从本机访问。",
  LOCAL_LOGIN_PAIR_CODE_EXPIRED: "配对码已过期，请在设置页重新生成。",
  LOCAL_LOGIN_PAIR_CODE_INVALID: "配对码无效，请核对后重试。",
  LOCAL_LOGIN_STATE_AUTH_FAILED: "签名校验失败，请重新配对。",
  LOCAL_LOGIN_STATE_INVALID: "登录状态结构无效，请重新获取。",
  LOCAL_LOGIN_STATE_NOT_PAIRED: "后端配对状态已失效，请重新配对。",
  LOCAL_LOGIN_STATE_PAYLOAD_TOO_LARGE: "同步请求超过安全大小限制。",
  LOCAL_LOGIN_STATE_REPLAY: "请求 nonce 已使用，请重新操作。",
  LOCAL_LOGIN_STATE_TIMESTAMP_INVALID: "本机时间偏差过大，请校准系统时间。",
  LOCAL_LOGIN_STATE_VERSION_UNSUPPORTED: "插件版本与本机服务不兼容。",
  NOT_PAIRED: "插件尚未配对，请先输入设置页生成的配对码。",
  PAIRING_CODE_EXPIRED: "配对码已过期，请在设置页重新生成。",
  PAIRING_CODE_INVALID: "配对码无效，请核对后重试。",
  PAIRING_FAILED: "配对失败，请重新生成配对码后重试。",
  REQUEST_BODY_TOO_LARGE: "同步请求超过 64 KiB，已拒绝发送。",
  SIGNATURE_INVALID: "签名校验失败，请重新配对。",
  SYNC_FAILED: "同步失败，请检查本机服务状态后重试。",
  TIMESTAMP_EXPIRED: "本机时间偏差过大，请校准系统时间后重试。"
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  handleMessage(message)
    .then((result) => sendResponse({ ok: true, ...result }))
    .catch((error) => {
      const code = safeErrorCode(error);
      sendResponse({
        ok: false,
        error_code: code,
        message:
          SAFE_ERROR_MESSAGES[code] ||
          safeLocalMessage(error) ||
          "操作失败，请重试。"
      });
    });
  return true;
});

async function handleMessage(message) {
  switch (message?.type) {
    case MESSAGE_TYPES.getState:
      return getExtensionState();
    case MESSAGE_TYPES.pair:
      return completePairing(message?.pairingCode);
    case MESSAGE_TYPES.resetPairing:
      return resetPairing();
    case MESSAGE_TYPES.backendStatus:
      return getBackendStatus();
    case MESSAGE_TYPES.sync:
      return syncDouyinLoginState(message?.payload);
    case MESSAGE_TYPES.clear:
      return clearDouyinLoginState();
    default:
      throw localError("INVALID_REQUEST", "无法识别的插件操作。");
  }
}

async function getStoredState() {
  return chrome.storage.local.get([
    STORAGE_KEYS.sharedSecret,
    STORAGE_KEYS.lastSyncedAt
  ]);
}

async function getExtensionState() {
  const stored = await getStoredState();
  return {
    paired: Boolean(stored[STORAGE_KEYS.sharedSecret]),
    last_synced_at: String(stored[STORAGE_KEYS.lastSyncedAt] || ""),
    extension_version: chrome.runtime.getManifest().version,
    schema_version: SCHEMA_VERSION
  };
}

async function completePairing(pairingCode) {
  const code = String(pairingCode || "").trim();
  if (!/^[A-Za-z0-9_-]{6,128}$/.test(code)) {
    throw localError("PAIRING_CODE_INVALID", "配对码格式无效。");
  }

  const response = await localFetch(API_PATHS.pairComplete, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      schema_version: SCHEMA_VERSION,
      pairing_code: code,
      extension_version: chrome.runtime.getManifest().version
    })
  });
  const data = await parseSafeJson(response);
  if (!response.ok || data?.ok === false) {
    throw apiError(data, "PAIRING_FAILED");
  }

  const persisted = buildPersistedPairingState(data?.pairing?.shared_key);
  await chrome.storage.local.set(persisted);
  return {
    paired: true,
    last_synced_at: ""
  };
}

async function resetPairing() {
  await chrome.storage.local.remove([
    STORAGE_KEYS.sharedSecret,
    STORAGE_KEYS.lastSyncedAt
  ]);
  return {
    paired: false,
    last_synced_at: ""
  };
}

async function getBackendStatus() {
  const response = await localFetch(API_PATHS.status, {
    method: "GET",
    headers: { Accept: "application/json" }
  });
  const data = await parseSafeJson(response);
  if (!response.ok || data?.ok === false) {
    throw apiError(data, "API_UNAVAILABLE");
  }
  return {
    status: sanitizeBackendStatus(data?.login_state)
  };
}

async function syncDouyinLoginState(payload) {
  assertSyncPayloadShape(payload);
  const data = await signedRequest("POST", API_PATHS.douyinSync, payload);
  const status = sanitizeBackendStatus(data?.login_state);
  const syncedAt = status.last_synced_at || new Date().toISOString();
  await chrome.storage.local.set({
    [STORAGE_KEYS.lastSyncedAt]: syncedAt
  });
  return {
    synced: true,
    last_synced_at: syncedAt,
    status
  };
}

async function clearDouyinLoginState() {
  const data = await signedRequest("DELETE", API_PATHS.douyinClear);
  await chrome.storage.local.remove(STORAGE_KEYS.lastSyncedAt);
  return {
    cleared: true,
    last_synced_at: "",
    status: sanitizeBackendStatus(data?.login_state)
  };
}

async function signedRequest(method, path, payload = undefined) {
  const stored = await getStoredState();
  const sharedSecret = stored[STORAGE_KEYS.sharedSecret];
  if (!sharedSecret) {
    throw localError("NOT_PAIRED", "插件尚未配对。");
  }

  const bodyText = payload === undefined ? "" : JSON.stringify(payload);
  const headers = await buildSignedHeaders({
    bodyText,
    sharedSecret,
    extensionVersion: chrome.runtime.getManifest().version
  });
  const response = await localFetch(path, {
    method,
    headers,
    body: bodyText || undefined
  });
  const data = await parseSafeJson(response);
  if (!response.ok || data?.ok === false) {
    const fallback = method === "DELETE" ? "CLEAR_FAILED" : "SYNC_FAILED";
    throw apiError(data, fallback);
  }
  return data;
}

async function localFetch(path, init) {
  try {
    return await fetch(`${API_ORIGIN}${path}`, {
      ...init,
      cache: "no-store",
      credentials: "omit",
      redirect: "error"
    });
  } catch {
    throw localError("API_UNAVAILABLE", "本机服务不可访问。");
  }
}

async function parseSafeJson(response) {
  const contentType = String(response.headers.get("Content-Type") || "");
  if (!contentType.toLowerCase().includes("application/json")) {
    if (response.ok) {
      throw localError("INVALID_RESPONSE", "本机服务没有返回 JSON。");
    }
    return {};
  }
  try {
    return await response.json();
  } catch {
    throw localError("INVALID_RESPONSE", "本机服务返回了无效 JSON。");
  }
}

function assertSyncPayloadShape(payload) {
  if (
    !payload ||
    payload.schema_version !== SCHEMA_VERSION ||
    typeof payload.cookie_header !== "string" ||
    !payload.cookie_header ||
    typeof payload.user_agent !== "string" ||
    typeof payload.referer !== "string" ||
    typeof payload.captured_at !== "string" ||
    !Number.isInteger(payload.pair_count) ||
    !Number.isInteger(payload.login_key_count) ||
    payload.extension_version !== chrome.runtime.getManifest().version
  ) {
    throw localError("INVALID_REQUEST", "登录状态结构无效，请重新获取。");
  }
}

function sanitizeBackendStatus(data) {
  return {
    configured: data?.configured === true,
    source:
      data?.source === "chrome_extension" ? "chrome_extension" : "",
    pair_count: safeCount(data?.pair_count),
    login_key_count: safeCount(data?.login_key_count),
    last_synced_at: safeIsoString(data?.last_synced_at)
  };
}

function safeCount(value) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 0 && parsed <= 256 ? parsed : 0;
}

function safeIsoString(value) {
  const text = String(value || "");
  if (!text || Number.isNaN(Date.parse(text))) {
    return "";
  }
  return new Date(text).toISOString();
}

function apiError(data, fallbackCode) {
  const candidate = String(data?.error_code || "");
  const code = /^[A-Z][A-Z0-9_]{2,63}$/.test(candidate)
    ? candidate
    : fallbackCode;
  return localError(code, SAFE_ERROR_MESSAGES[code] || "");
}

function localError(code, message) {
  const error = new Error(message);
  error.code = code;
  return error;
}

function safeErrorCode(error) {
  const code = String(error?.code || "");
  return /^[A-Z][A-Z0-9_]{2,63}$/.test(code) ? code : "API_UNAVAILABLE";
}

function safeLocalMessage(error) {
  const message = String(error?.message || "");
  return message.length <= 160 && !/cookie|secret|authorization/i.test(message)
    ? message
    : "";
}
