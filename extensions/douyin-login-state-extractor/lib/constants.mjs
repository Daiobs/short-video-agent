export const API_ORIGIN = "http://127.0.0.1:8765";
export const SCHEMA_VERSION = 1;

export const API_PATHS = Object.freeze({
  pairStart: "/api/local-login-state/pair/start",
  pairComplete: "/api/local-login-state/pair/complete",
  status: "/api/local-login-state/status",
  douyinSync: "/api/local-login-state/douyin/sync",
  douyinClear: "/api/local-login-state/douyin"
});

export const DEFAULT_REFERER = "https://www.douyin.com/";
export const MAX_COOKIE_COUNT = 256;
export const MAX_COOKIE_HEADER_BYTES = 32 * 1024;
export const MAX_REQUEST_BODY_BYTES = 64 * 1024;
export const ALLOWED_COOKIE_DOMAINS = Object.freeze([
  "douyin.com",
  ".douyin.com"
]);

export const STORAGE_KEYS = Object.freeze({
  sharedSecret: "pairing_shared_secret",
  lastSyncedAt: "last_synced_at"
});

export const MESSAGE_TYPES = Object.freeze({
  getState: "GET_EXTENSION_STATE",
  pair: "COMPLETE_PAIRING",
  resetPairing: "RESET_PAIRING",
  backendStatus: "GET_BACKEND_STATUS",
  sync: "SYNC_DOUYIN_LOGIN_STATE",
  clear: "CLEAR_DOUYIN_LOGIN_STATE"
});
