import { MESSAGE_TYPES } from "./lib/constants.mjs";
import {
  buildSafePreview,
  buildSyncPayload,
  normalizeDouyinReferer
} from "./lib/cookie-security.mjs";

const elements = {
  connectionStatus: document.querySelector("#connection-status"),
  loginStatus: document.querySelector("#login-status"),
  lastSyncStatus: document.querySelector("#last-sync-status"),
  pairingPanel: document.querySelector("#pairing-panel"),
  pairingCode: document.querySelector("#pairing-code"),
  pairButton: document.querySelector("#pair-button"),
  captureButton: document.querySelector("#capture-button"),
  previewPanel: document.querySelector("#preview-panel"),
  previewCookie: document.querySelector("#preview-cookie"),
  previewPairs: document.querySelector("#preview-pairs"),
  previewLoginKeys: document.querySelector("#preview-login-keys"),
  previewUserAgent: document.querySelector("#preview-user-agent"),
  previewDomain: document.querySelector("#preview-domain"),
  syncButton: document.querySelector("#sync-button"),
  feedback: document.querySelector("#feedback"),
  rePairButton: document.querySelector("#re-pair-button"),
  clearButton: document.querySelector("#clear-button")
};

let extensionState = {
  paired: false,
  last_synced_at: "",
  extension_version: ""
};
let capturedPayload = null;
let busy = false;

void initialize();

elements.pairButton.addEventListener("click", completePairing);
elements.captureButton.addEventListener("click", captureLoginState);
elements.syncButton.addEventListener("click", syncLoginState);
elements.rePairButton.addEventListener("click", resetPairing);
elements.clearButton.addEventListener("click", clearLoginState);
elements.pairingCode.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    void completePairing();
  }
});

async function initialize() {
  setBusy(true);
  setFeedback("正在检查本机配对状态。");
  try {
    const state = await sendMessage({ type: MESSAGE_TYPES.getState });
    extensionState = { ...extensionState, ...state };
    renderState();
    if (extensionState.paired) {
      await refreshBackendStatus();
    } else {
      setFeedback("请先输入 short-video-agent 设置页生成的配对码。");
    }
  } catch (error) {
    showError(error);
  } finally {
    setBusy(false);
  }
}

async function completePairing() {
  if (busy) {
    return;
  }
  const pairingCode = elements.pairingCode.value.trim();
  if (!pairingCode) {
    showError({ message: "请输入配对码。" });
    return;
  }

  setBusy(true);
  setFeedback("正在与本机 short-video-agent 配对。");
  try {
    const result = await sendMessage({
      type: MESSAGE_TYPES.pair,
      pairingCode
    });
    extensionState.paired = result.paired === true;
    extensionState.last_synced_at = "";
    elements.pairingCode.value = "";
    renderState();
    setFeedback("配对成功。以后同步任意主页登录状态都不需要重新配对。", "success");
    await refreshBackendStatus();
  } catch (error) {
    showError(error);
  } finally {
    setBusy(false);
  }
}

async function captureLoginState() {
  if (busy) {
    return;
  }
  setBusy(true);
  setFeedback("正在读取 douyin.com 登录状态，仅在当前 Popup 内存中处理。");
  try {
    const [cookies, referer] = await Promise.all([
      chrome.cookies.getAll({
        url: "https://www.douyin.com/aweme/v1/web/aweme/post/"
      }),
      getActiveDouyinReferer()
    ]);
    capturedPayload = buildSyncPayload(cookies, {
      userAgent: navigator.userAgent,
      referer,
      capturedAt: new Date().toISOString(),
      extensionVersion:
        extensionState.extension_version ||
        chrome.runtime.getManifest().version
    });
    renderPreview(buildSafePreview(capturedPayload));
    elements.loginStatus.textContent = capturedPayload.login_key_count
      ? `已读取 ${capturedPayload.login_key_count} 个登录态字段`
      : "未识别登录态字段";
    setFeedback(
      `读取完成：${capturedPayload.pair_count} 个可同步字段。Cookie 原文不会显示或保存到插件 storage。`,
      capturedPayload.login_key_count ? "success" : ""
    );
  } catch (error) {
    capturedPayload = null;
    elements.previewPanel.hidden = true;
    elements.loginStatus.textContent = "读取失败";
    showError(error);
  } finally {
    setBusy(false);
    renderState();
  }
}

async function syncLoginState() {
  if (busy || !capturedPayload) {
    return;
  }
  if (!extensionState.paired) {
    showError({ message: "请先完成一次配对。" });
    return;
  }

  setBusy(true);
  setFeedback("正在签名并同步到本机 short-video-agent。");
  try {
    const result = await sendMessage({
      type: MESSAGE_TYPES.sync,
      payload: capturedPayload
    });
    extensionState.last_synced_at = result.last_synced_at || "";
    capturedPayload = null;
    renderState();
    setFeedback("同步成功。后续主页扫描会复用本机保存的登录状态。", "success");
  } catch (error) {
    showError(error);
  } finally {
    setBusy(false);
  }
}

async function resetPairing() {
  if (busy) {
    return;
  }
  setBusy(true);
  try {
    await sendMessage({ type: MESSAGE_TYPES.resetPairing });
    extensionState.paired = false;
    extensionState.last_synced_at = "";
    capturedPayload = null;
    elements.previewPanel.hidden = true;
    elements.loginStatus.textContent = "待获取";
    elements.connectionStatus.textContent = "未配对";
    renderState();
    setFeedback("本机配对已清除。请在设置页生成新的配对码。");
  } catch (error) {
    showError(error);
  } finally {
    setBusy(false);
  }
}

async function clearLoginState() {
  if (busy || !extensionState.paired) {
    return;
  }
  if (
    !window.confirm(
      "确认清除 short-video-agent 保存的抖音登录状态？这不会退出 Chrome 中的抖音账号。"
    )
  ) {
    return;
  }
  setBusy(true);
  setFeedback("正在清除 short-video-agent 保存的抖音登录状态。");
  try {
    await sendMessage({ type: MESSAGE_TYPES.clear });
    extensionState.last_synced_at = "";
    capturedPayload = null;
    elements.previewPanel.hidden = true;
    elements.loginStatus.textContent = "已清除";
    renderState();
    setFeedback(
      "已清除本机保存的登录状态；Chrome 中的抖音账号没有退出。",
      "success"
    );
  } catch (error) {
    showError(error);
  } finally {
    setBusy(false);
  }
}

async function refreshBackendStatus() {
  try {
    const result = await sendMessage({
      type: MESSAGE_TYPES.backendStatus
    });
    const status = result.status || {};
    elements.connectionStatus.textContent = "已配对";
    if (status.configured) {
      elements.loginStatus.textContent = status.login_key_count
        ? `已同步 ${status.login_key_count} 个登录态字段`
        : "已同步";
      extensionState.last_synced_at =
        status.last_synced_at || extensionState.last_synced_at;
      renderState();
    }
  } catch (error) {
    elements.connectionStatus.textContent = "服务不可用";
    showError(error);
  }
}

async function getActiveDouyinReferer() {
  try {
    const tabs = await chrome.tabs.query({
      active: true,
      currentWindow: true
    });
    return normalizeDouyinReferer(tabs[0]?.url);
  } catch {
    return normalizeDouyinReferer("");
  }
}

function renderState() {
  elements.pairingPanel.hidden = extensionState.paired;
  elements.rePairButton.hidden = !extensionState.paired;
  elements.clearButton.disabled = busy || !extensionState.paired;
  elements.syncButton.disabled =
    busy || !extensionState.paired || !capturedPayload;
  elements.captureButton.disabled = busy;
  elements.pairButton.disabled = busy;

  if (extensionState.paired && elements.connectionStatus.textContent === "检查中") {
    elements.connectionStatus.textContent = "已配对";
  } else if (!extensionState.paired) {
    elements.connectionStatus.textContent = "未配对";
  }
  elements.lastSyncStatus.textContent = formatDateTime(
    extensionState.last_synced_at
  );
}

function renderPreview(preview) {
  elements.previewPanel.hidden = false;
  elements.previewCookie.textContent = preview.maskedCookie;
  elements.previewPairs.textContent = String(preview.pairCount);
  elements.previewLoginKeys.textContent = String(preview.loginKeyCount);
  elements.previewUserAgent.textContent =
    preview.userAgent || "未读取";
  elements.previewDomain.textContent = preview.targetDomain;
}

function setBusy(value) {
  busy = Boolean(value);
  renderState();
}

function setFeedback(message, tone = "") {
  elements.feedback.textContent = String(message || "");
  elements.feedback.classList.toggle("is-success", tone === "success");
  elements.feedback.classList.toggle("is-error", tone === "error");
}

function showError(error) {
  const code = String(error?.error_code || error?.code || "");
  const message = String(error?.message || "操作失败，请重试。");
  setFeedback(code ? `${code}：${message}` : message, "error");
}

async function sendMessage(message) {
  const response = await chrome.runtime.sendMessage(message);
  if (!response?.ok) {
    const error = new Error(response?.message || "插件操作失败。");
    error.error_code = response?.error_code || "EXTENSION_REQUEST_FAILED";
    throw error;
  }
  return response;
}

function formatDateTime(value) {
  const timestamp = Date.parse(String(value || ""));
  if (Number.isNaN(timestamp)) {
    return "尚未同步";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date(timestamp));
}
