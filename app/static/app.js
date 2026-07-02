// Settings
const settingsToggle = document.getElementById("settings-toggle");
const settingsModal = document.getElementById("settings-modal");
const settingsDrawer = document.getElementById("settings-drawer");
const settingsClose = document.getElementById("settings-close");
const singleForm = document.getElementById("single-form");
const singleButton = document.getElementById("single-button");
const singleResult = document.getElementById("single-result");
const qualityPreference = document.getElementById("quality-preference");
const parseStatus = document.getElementById("parse-status");
const downloadStatus = document.getElementById("download-status");
const packageStatus = document.getElementById("package-status");
const analysisStatus = document.getElementById("analysis-status");
const llmStatusBadge = document.getElementById("llm-status-badge");
const llmStatusList = document.getElementById("llm-status-list");
const llmConfigHint = document.getElementById("llm-config-hint");
const llmSettingsForm = document.getElementById("llm-settings-form");
const llmProviderInput = document.getElementById("llm-provider-input");
const llmApiBaseInput = document.getElementById("llm-api-base-input");
const llmModelInput = document.getElementById("llm-model-input");
const llmApiKeyInput = document.getElementById("llm-api-key-input");
const llmTimeoutInput = document.getElementById("llm-timeout-input");
const llmTemperatureInput = document.getElementById("llm-temperature-input");
const llmClearKeyInput = document.getElementById("llm-clear-key-input");
const saveLlmSettingsButton = document.getElementById("save-llm-settings-button");
const llmSaveResult = document.getElementById("llm-save-result");
const testLlmButton = document.getElementById("test-llm-button");
const llmTestResult = document.getElementById("llm-test-result");
const refreshPreflightButton = document.getElementById("refresh-preflight-button");
const preflightSummary = document.getElementById("preflight-summary");
const preflightList = document.getElementById("preflight-list");
const dataSourceStatusBadge = document.getElementById("data-source-status-badge");
const dataSourceStatusList = document.getElementById("data-source-status-list");
const douyinSettingsForm = document.getElementById("douyin-settings-form");
const douyinCookieInput = document.getElementById("douyin-cookie-input");
const douyinUserAgentInput = document.getElementById("douyin-user-agent-input");
const douyinRefererInput = document.getElementById("douyin-referer-input");
const douyinClearCookieInput = document.getElementById("douyin-clear-cookie-input");
const saveDouyinSettingsButton = document.getElementById("save-douyin-settings-button");
const douyinSaveResult = document.getElementById("douyin-save-result");
const testDouyinCookieButton = document.getElementById("test-douyin-cookie-button");
const douyinCookieTestResult = document.getElementById("douyin-cookie-test-result");
const resultCard = document.getElementById("result-card");
const caseSummary = document.getElementById("case-summary");
const homeCaseView = document.getElementById("home-case-view");
const homeContactSheet = document.getElementById("home-contact-sheet");
const homeCaseMeta = document.getElementById("home-case-meta");
const homeAiStatus = document.getElementById("home-ai-status");
const homeAiReport = document.getElementById("home-ai-report");
const openFullCaseLink = document.getElementById("open-full-case-link");
const copyHomePromptButton = document.getElementById("copy-home-prompt-button");
const downloadHomeAnalysisInputButton = document.getElementById("download-home-analysis-input-button");
const uploadResult = document.getElementById("upload-result");
const buildCaseButton = document.getElementById("build-case-button");
const jobCard = document.getElementById("job-card");
const progressBar = document.getElementById("progress-bar");
const jobMessage = document.getElementById("job-message");
const jobPhase = document.getElementById("job-phase");
const jobResult = document.getElementById("job-result");
const homeRouteButtons = Array.from(document.querySelectorAll("[data-home-route]"));
const homePanels = Array.from(document.querySelectorAll("[data-home-panel]"));

const profileForm = document.getElementById("profile-form");

// Creator Clone: import
const profileImportModeButtons = Array.from(document.querySelectorAll("[data-profile-import-mode]"));
const profileImportPanels = Array.from(document.querySelectorAll("[data-profile-import-panel]"));
const creatorCloneFlowSteps = Array.from(document.querySelectorAll("[data-profile-stage-nav]"));
const profileStageSections = Array.from(document.querySelectorAll("[data-profile-stage-section]"));
const creatorCloneNextBar = document.getElementById("creator-clone-next-bar");
const creatorCloneCurrentStep = document.getElementById("creator-clone-current-step");
const creatorCloneNextSummary = document.getElementById("creator-clone-next-summary");
const creatorCloneNextButton = document.getElementById("creator-clone-next-button");
const creatorCloneRecommendation = document.getElementById("creator-clone-recommendation");
const profilePublicSection = document.getElementById("profile-public-section");
const profileSort = document.getElementById("profile-sort");
const profileMediaFilter = document.getElementById("profile-media-filter");
const profileEvidenceFilter = document.getElementById("profile-evidence-filter");
const profileScanButton = document.getElementById("profile-scan-button");
const profileBrowserHelperButton = document.getElementById("profile-browser-helper-button");
const profileChromeStatus = document.getElementById("profile-chrome-status");
const profileChromeConfirm = document.getElementById("profile-chrome-confirm");
const profileSelectedBuildButton = document.getElementById("profile-selected-build-button");
const profileSelectAllButton = document.getElementById("profile-select-all-button");
const profileClearSelectionButton = document.getElementById("profile-clear-selection-button");
const profilePresetKind = document.getElementById("profile-preset-kind");
const profileContinueChromeButton = document.getElementById("profile-continue-chrome-button");
const profileAutoDistill = document.getElementById("profile-auto-distill");
const profileScanStatus = document.getElementById("profile-scan-status");
const profileFallbackHint = document.getElementById("profile-fallback-hint");
const profileManualSection = document.getElementById("profile-manual-section");
const profileManualLinks = document.getElementById("profile-manual-links");
const profileHandoffFile = document.getElementById("profile-handoff-file");
const profileHandoffManifest = document.getElementById("profile-handoff-manifest");
const profileResultsCard = document.getElementById("profile-results-card");
const profileProviderBadge = document.getElementById("profile-provider-badge");
const profileWarnings = document.getElementById("profile-warnings");
const profileQuickInput = document.getElementById("profile-quick-input");
const profileScanPanel = document.querySelector(".profile-scan-panel");
const profileCaptureAudit = document.getElementById("profile-capture-audit");
const profileSummary = document.getElementById("profile-summary");
const profileNextAction = document.getElementById("profile-next-action");
const profileDecisionBoard = document.getElementById("profile-decision-board");
const profileSegmentsPreview = document.getElementById("profile-segments-preview");
const profileResultsBody = document.getElementById("profile-results-body");
const profileEnrichmentSection = document.getElementById("profile-enrichment-section");
const profileDistillationSection = document.getElementById("profile-distillation-section");
const profileQueueCard = document.getElementById("profile-queue-card");
const profileQueueSummary = document.getElementById("profile-queue-summary");
const profileQueueItems = document.getElementById("profile-queue-items");
const creatorCloneDistillButton = document.getElementById("creator-clone-distill-button");
const creatorCloneBatchDistillButton = document.getElementById("creator-clone-batch-distill-button");
const profileContentProfile = document.getElementById("profile-content-profile");
const creatorCloneSelectionStatus = document.getElementById("creator-clone-selection-status");
const profileEvidenceStatus = document.getElementById("profile-evidence-status");
const profileDistillReadinessStatus = document.getElementById("profile-distill-readiness");
const creatorCloneResultCard = document.getElementById("creator-clone-result-card");
const creatorCloneResult = document.getElementById("creator-clone-result");
const creatorCloneConfidence = document.getElementById("creator-clone-confidence");
const creatorCloneExportActions = document.getElementById("creator-clone-export-actions");
const copyCreatorCloneSpecButton = document.getElementById("copy-creator-clone-spec-button");
const copyDistillPromptButton = document.getElementById("copy-distill-prompt-button");
const downloadCreatorCloneJson = document.getElementById("download-creator-clone-json");
const downloadCreatorCloneMd = document.getElementById("download-creator-clone-md");
const PROFILE_BUILD_MAX_ITEMS = Math.max(1, Number(document.body.dataset.profileBuildMaxItems || 10));
const CREATOR_CLONE_MAX_DISTILL_SAMPLES = Math.max(1, Number(document.body.dataset.creatorCloneMaxDistillSamples || 20));
const HANDOFF_MANIFEST_MAX_BYTES = 2 * 1024 * 1024;

document.querySelectorAll(".summary-actions").forEach((container) => {
  container.addEventListener("click", (event) => {
    const action = event.target.closest("button, a");
    if (!action) {
      return;
    }
    if (action.tagName === "BUTTON") {
      event.preventDefault();
    }
    const submitter = event.target.closest('button[type="submit"]');
    event.stopPropagation();
    if (submitter?.form) {
      event.preventDefault();
      if (submitter.form.requestSubmit) {
        submitter.form.requestSubmit(submitter);
      } else {
        submitter.form.dispatchEvent(new Event("submit", {bubbles: true, cancelable: true}));
      }
    }
  });
});

let currentLocalVideoId = "";
let currentAwemeId = "";
let selectedCandidate = null;
let loadedHomeCase = null;
let runtimeSampleRows = [];
let profileSelectedKeys = new Set();
let profileScanPayload = null;
let currentCloneSetId = "";
let currentDistillPrompt = "";
let currentCreatorRuntimeReport = null;
let currentCreatorIntelligenceProject = null;
let currentCreatorIntelligenceStrategy = null;
let currentCreatorRuntimeState = null;
let chromeHelperStatusLoaded = false;
let profileLastChromeProfileValue = "";
let profileChromeLaunchCommand = "";
let profileChromeAvailable = false;
let creatorCloneEnrichmentRunning = false;
let creatorCloneDistillRunning = false;
let creatorCloneNextActionRunning = false;
let creatorCloneSelectionSyncTimer = 0;
let profileStageView = "import";
let currentCloneProfileFingerprint = "";
let profileQuickInputRestoredValue = "";
let preflightCopySnippets = [];
let recentCreatorCloneRestoreAttempted = false;

const RECENT_CREATOR_CLONE_SET_STORAGE_KEY = "shortVideoAgent.recentCreatorCloneSetId";
const RECENT_PROFILE_BUILD_STATE_STORAGE_KEY = "shortVideoAgent.recentProfileBuildState";
const RECENT_PROFILE_STAGE_STORAGE_KEY = "shortVideoAgent.recentProfileStage";

function setStatus(element, value) {
  if (element) {
    element.textContent = value;
  }
}

function setHomeRoute(route, updateHash = true) {
  const activeRoute = ["single", "profile"].includes(route) ? route : "single";
  homePanels.forEach((panel) => {
    panel.classList.toggle("hidden", panel.dataset.homePanel !== activeRoute);
  });
  homeRouteButtons.forEach((button) => {
    const active = button.dataset.homeRoute === activeRoute;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "page" : "false");
  });
  if (updateHash) {
    history.replaceState(null, "", `#${activeRoute}`);
  }
  if (activeRoute === "profile" && !chromeHelperStatusLoaded) {
    chromeHelperStatusLoaded = true;
    loadChromeHelperStatus({silent: true}).catch(() => {
      if (profileChromeStatus) {
        profileChromeStatus.textContent = "本机 Chrome 辅助状态：检测失败，可直接使用公开扫描或兜底导入。";
      }
    });
  }
  if (activeRoute === "profile") {
    restoreRecentCreatorCloneSet().catch(() => {});
  }
}

function routeFromHash() {
  return window.location.hash.replace("#", "") || "single";
}

function isSafeCreatorCloneSetId(value) {
  return /^clone_[a-f0-9]{32}$/i.test(String(value || ""));
}

function isSafeJobId(value) {
  return /^job_[a-f0-9-]+$/i.test(String(value || ""));
}

function readRecentCreatorCloneSetId() {
  try {
    const value = window.localStorage?.getItem(RECENT_CREATOR_CLONE_SET_STORAGE_KEY) || "";
    return isSafeCreatorCloneSetId(value) ? value : "";
  } catch {
    return "";
  }
}

function rememberRecentCreatorCloneSetId(setId) {
  if (!isSafeCreatorCloneSetId(setId)) {
    return;
  }
  try {
    window.localStorage?.setItem(RECENT_CREATOR_CLONE_SET_STORAGE_KEY, setId);
  } catch {
    // Browser storage can be disabled; restoring the recent pool is optional.
  }
}

function readRecentProfileBuildState() {
  try {
    const raw = window.localStorage?.getItem(RECENT_PROFILE_BUILD_STATE_STORAGE_KEY) || "";
    const value = raw ? JSON.parse(raw) : {};
    const setId = isSafeCreatorCloneSetId(value.set_id) ? value.set_id : "";
    const jobId = isSafeJobId(value.job_id) ? value.job_id : "";
    const selectedSampleIds = normalizeItems(value.selected_sample_ids)
      .map((item) => String(item || ""))
      .filter(Boolean);
    return setId && jobId ? {set_id: setId, job_id: jobId, selected_sample_ids: selectedSampleIds} : null;
  } catch {
    return null;
  }
}

function readRecentProfileStage() {
  try {
    return normalizeProfileStage(window.localStorage?.getItem(RECENT_PROFILE_STAGE_STORAGE_KEY) || "pool");
  } catch {
    return "pool";
  }
}

function rememberRecentProfileStage(stage) {
  try {
    window.localStorage?.setItem(RECENT_PROFILE_STAGE_STORAGE_KEY, normalizeProfileStage(stage));
  } catch {
    // Stage restore is optional.
  }
}

function rememberRecentProfileBuildState({setId = "", jobId = "", selectedSampleIds = []} = {}) {
  if (!isSafeCreatorCloneSetId(setId) || !isSafeJobId(jobId)) {
    return;
  }
  try {
    window.localStorage?.setItem(RECENT_PROFILE_BUILD_STATE_STORAGE_KEY, JSON.stringify({
      set_id: setId,
      job_id: jobId,
      selected_sample_ids: normalizeItems(selectedSampleIds).map((item) => String(item || "")).filter(Boolean),
      saved_at: new Date().toISOString(),
    }));
  } catch {
    // Restoring an in-flight queue is optional.
  }
}

function forgetRecentProfileBuildState() {
  try {
    window.localStorage?.removeItem(RECENT_PROFILE_BUILD_STATE_STORAGE_KEY);
  } catch {
    // Ignore storage failures.
  }
}

function forgetRecentProfileStage() {
  try {
    window.localStorage?.removeItem(RECENT_PROFILE_STAGE_STORAGE_KEY);
  } catch {
    // Ignore storage failures.
  }
}

function forgetRecentCreatorCloneSetId() {
  try {
    window.localStorage?.removeItem(RECENT_CREATOR_CLONE_SET_STORAGE_KEY);
  } catch {
    // Ignore storage failures; they should not affect the main workflow.
  }
  forgetRecentProfileBuildState();
  forgetRecentProfileStage();
}

async function restoreRecentCreatorCloneSet() {
  if (recentCreatorCloneRestoreAttempted || currentCloneSetId || activeCreatorSampleViewItems().length) {
    return false;
  }
  recentCreatorCloneRestoreAttempted = true;
  const setId = readRecentCreatorCloneSetId();
  if (!setId) {
    return false;
  }
  if (profileScanStatus) {
    profileScanStatus.textContent = "正在恢复上次素材池...";
  }
  try {
    const response = await fetch(`/api/creator-intelligence/projects/${encodeURIComponent(setId)}`, {cache: "no-store"});
    const payload = await readJsonResponse(response);
    const profilePayload = profilePayloadFromCreatorIntelligenceProject(payload);
    renderProfileResults(profilePayload);
    setCreatorCloneRestoredInput(creatorCloneSourceInputFromPayload(profilePayload));
    const restoredQueue = await restoreRecentProfileBuildJob(setId);
    if (!restoredQueue) {
      const selected = selectedCreatorSampleViewItems();
      const restoredStage = readRecentProfileStage();
      const fallbackStage = selected.length
        ? (["select", "enrich", "distill", "export"].includes(restoredStage) ? restoredStage : "select")
        : "pool";
      setProfileStageView(fallbackStage);
      if (profileScanStatus) {
        const itemCount = activeCreatorSampleViewItems().length;
        profileScanStatus.textContent = selected.length
          ? `已恢复上次素材池和 ${formatNumber(selected.length)} 条已选样本。`
          : `已恢复上次素材池：${formatNumber(itemCount)} 条素材。`;
      }
    }
    return true;
  } catch {
    forgetRecentCreatorCloneSetId();
    if (profileScanStatus) {
      profileScanStatus.textContent = "上次素材池无法恢复，请重新导入或扫描。";
    }
    return false;
  }
}

async function restoreRecentProfileBuildJob(setId) {
  const state = readRecentProfileBuildState();
  const shouldUseStoredJob = state && state.set_id === setId;
  const selectedKeys = new Set(shouldUseStoredJob ? state.selected_sample_ids : []);
  if (selectedKeys.size) {
    setProfileSelection(activeCreatorSampleViewItems().filter((item) => sampleViewItemMatchesKeySet(item, selectedKeys)));
  }
  try {
    const jobUrl = shouldUseStoredJob
      ? `/api/jobs/${encodeURIComponent(state.job_id)}`
      : `/api/jobs/profile-build-cases/recent?sample_set_id=${encodeURIComponent(setId)}`;
    const response = await fetch(jobUrl, {cache: "no-store"});
    const payload = await readJsonResponse(response);
    const job = payload.job || {};
    if (job.type !== "profile-build-cases") {
      forgetRecentProfileBuildState();
      return false;
    }
    const resultItems = normalizeItems(job.result_json?.items);
    if (!selectedKeys.size && resultItems.length) {
      const queueKeys = new Set(resultItems.map(sampleViewItemKey).filter(Boolean));
      setProfileSelection(activeCreatorSampleViewItems().filter((item) => sampleViewItemMatchesKeySet(item, queueKeys)));
    }
    rememberRecentProfileBuildState({
      setId,
      jobId: job.id,
      selectedSampleIds: selectedCreatorSampleViewItems().map(sampleViewItemKey),
    });
    placeJobCard("profile");
    renderJobStatus(job, "恢复素材包队列");
    if (job.result_json && Object.keys(job.result_json).length) {
      renderProfileQueue(job.result_json);
    } else {
      renderProfileQueue({items: selectedCreatorSampleViewItems().map((item) => ({
        ...queueItemPayload(item),
        status: "pending",
        message: "等待后端写入队列状态",
      }))});
    }
    if (job.status === "running" || job.status === "pending") {
      setProfileStageView("enrich", {scroll: false});
      setCreatorCloneEnrichmentLocked(true);
      profileScanStatus.textContent = "已恢复正在运行的证据富化队列；请等待进度更新，不需要重新点击。";
      pollProfileQueue(job.id).finally(() => {
        setCreatorCloneEnrichmentLocked(false);
        updateCreatorCloneSelectionStatus();
        renderCreatorCloneNextAction();
      });
      return true;
    }
    if (job.status === "success") {
      if (job.result_json?.set) {
        refreshProfilePoolFromSet(job.result_json.set);
      }
      setProfileStageView("distill", {scroll: false});
      profileScanStatus.textContent = "已恢复上次完成的证据富化队列，可继续进入大模型蒸馏。";
      return true;
    }
    if (job.status === "failed") {
      setProfileStageView("enrich", {scroll: false});
      profileScanStatus.textContent = `${job.error_code || "ERROR"}：${job.message || "上次证据富化失败"}`;
      return true;
    }
    return false;
  } catch {
    forgetRecentProfileBuildState();
    return false;
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function firstUrlFromText(value) {
  const match = String(value || "").match(/https?:\/\/[^\s]+/i);
  return match ? match[0] : "";
}

function douyinProfileFingerprint(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return "";
  }
  const firstUrl = firstUrlFromText(raw) || raw;
  const secMatch = firstUrl.match(/MS4w[A-Za-z0-9_.-]+/);
  if (secMatch) {
    return `sec:${secMatch[0]}`;
  }
  try {
    const parsed = new URL(firstUrl);
    const host = parsed.hostname.toLowerCase();
    if (host === "douyin.com" || host.endsWith(".douyin.com")) {
      const pathMatch = parsed.pathname.match(/\/user\/([^/?#]+)/i);
      if (pathMatch?.[1]) {
        return `path:/user/${decodeURIComponent(pathMatch[1])}`;
      }
    }
  } catch {
    // The input may be a raw sec_user_id; the regex above already handles that path.
  }
  return "";
}

function profileFingerprintFromPayload(payload) {
  const set = payload?.set || payload || {};
  const meta = set.profile_metadata || payload?.summary?.profile_metadata || {};
  const audit = payload?.capture_audit || set.capture_audit || {};
  return douyinProfileFingerprint(meta.sec_user_id)
    || douyinProfileFingerprint(meta.profile_url)
    || douyinProfileFingerprint(audit.requested_profile)
    || "";
}

function creatorCloneSourceInputFromPayload(payload = {}) {
  const set = payload?.set || payload || {};
  const meta = set.profile_metadata || payload?.summary?.profile_metadata || {};
  const audit = payload?.capture_audit || set.capture_audit || {};
  const profileValue = [
    meta.profile_url,
    audit.requested_profile,
    meta.sec_user_id,
  ].map((value) => String(value || "").trim()).find(Boolean);
  if (profileValue) {
    return profileValue;
  }
  const sourceUrls = [];
  normalizeItems(payload.items || set.samples).forEach((item) => {
    const sourceUrl = String(item?.source_url || item?.webpage_url || "").trim();
    if (sourceUrl && !sourceUrls.includes(sourceUrl)) {
      sourceUrls.push(sourceUrl);
    }
  });
  return sourceUrls.slice(0, 150).join("\n");
}

function resetCreatorClonePoolForNewProfile() {
  currentCloneSetId = "";
  currentCloneProfileFingerprint = "";
  runtimeSampleRows = [];
  profileSelectedKeys = new Set();
  profileScanPayload = null;
  currentCreatorRuntimeReport = null;
  currentDistillPrompt = "";
  currentCreatorIntelligenceProject = null;
  currentCreatorIntelligenceStrategy = null;
  profileLastChromeProfileValue = "";
  clearCreatorCloneUnifiedInput();
  forgetRecentCreatorCloneSetId();
  profileQueueCard?.classList.add("hidden");
  profileResultsCard?.classList.add("hidden");
  creatorCloneResultCard?.classList.add("hidden");
}

function resetCreatorClonePoolIfProfileChanged(profileValue) {
  const nextFingerprint = douyinProfileFingerprint(profileValue);
  if (!nextFingerprint || !currentCloneProfileFingerprint || nextFingerprint === currentCloneProfileFingerprint) {
    return false;
  }
  resetCreatorClonePoolForNewProfile();
  return true;
}

function showJson(element, payload) {
  element.textContent = JSON.stringify(payload, null, 2);
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("zh-CN");
}

function formatSeconds(value) {
  const number = Number(value || 0);
  return number ? `${number.toFixed(2)} 秒` : "未知";
}

function formatBytes(value) {
  const number = Number(value || 0);
  if (!number) {
    return "未知";
  }
  if (number >= 1024 * 1024) {
    return `${(number / 1024 / 1024).toFixed(2)} MB`;
  }
  return `${Math.round(number / 1024)} KB`;
}

function renderDefinitionList(element, rows) {
  element.innerHTML = `
    <dl>
      ${rows
        .filter(([, value]) => value !== undefined && value !== null && value !== "")
        .map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`)
        .join("")}
    </dl>
  `;
}

function placeJobCard(scope = "profile") {
  if (!jobCard) {
    return;
  }
  if (scope === "single" && resultCard) {
    resultCard.insertAdjacentElement("afterend", jobCard);
    return;
  }
  if (creatorCloneNextBar) {
    creatorCloneNextBar.insertAdjacentElement("afterend", jobCard);
  }
}

function scrollProfileTaskPanel() {
  profileScanPanel?.scrollIntoView({behavior: "smooth", block: "start"});
}

function resetJobCard(message = "") {
  if (!jobCard || !progressBar || !jobMessage) {
    return;
  }
  jobCard.classList.remove("hidden");
  progressBar.style.width = "0%";
  jobMessage.className = "job-message";
  jobMessage.textContent = message;
  renderJobPhase(null);
  if (jobResult) {
    jobResult.textContent = "";
  }
}

function renderJobPhase(job) {
  if (!jobPhase) {
    return;
  }
  const result = job?.result_json || {};
  const phase = result.distill_phase || null;
  if (!phase) {
    jobPhase.classList.add("hidden");
    jobPhase.innerHTML = "";
    return;
  }
  const plan = phase.execution_plan || result.execution_plan || {};
  const timeout = phase.timeout_seconds || plan.timeout_policy?.configured_final_reduce_timeout_seconds || "";
  const recommendedTimeout = plan.timeout_policy?.recommended_final_reduce_timeout_seconds || "";
  const batchLine = Number(phase.batch_count || plan.batch_count || 0)
    ? `批次 ${phase.phase_index ? `${formatNumber(phase.phase_index)} / ` : ""}${formatNumber(phase.batch_count || plan.batch_count)}`
    : "";
  const timeoutLine = timeout
    ? `当前阶段最多等待 ${formatNumber(timeout)} 秒${recommendedTimeout && Number(recommendedTimeout) > Number(timeout) ? ` · 建议上限 ${formatNumber(recommendedTimeout)} 秒` : ""}`
    : "";
  const duration = plan.duration || {};
  const durationLine = Number(duration.known_count || 0)
    ? `已知视频时长 ${formatNumber(duration.known_count)} 条 · 总计 ${formatNumber(duration.total_seconds || 0)} 秒`
    : "";
  const diagnostics = normalizeItems(plan.timeout_policy?.phase_diagnostics)
    .map((item) => item && typeof item === "object" ? `${item.phase}: ${item.meaning}` : formatReportValue(item))
    .filter(isMeaningfulReportText)
    .slice(0, 4);
  const chips = [
    plan.strategy_label || "",
    phase.current_phase_label || "",
    batchLine,
    timeoutLine,
    durationLine,
  ].filter(isMeaningfulReportText);
  jobPhase.classList.remove("hidden");
  jobPhase.innerHTML = `
    <div class="job-phase-header">
      <span>${escapeHtml(phase.current_phase_label || "运行阶段")}</span>
      ${phase.status ? `<strong>${escapeHtml(phase.status)}</strong>` : ""}
    </div>
    ${chips.length ? `<div class="job-phase-chips">${chips.map((chip) => `<span>${escapeHtml(chip)}</span>`).join("")}</div>` : ""}
    ${phase.diagnostic ? `<p>${escapeHtml(phase.diagnostic)}</p>` : ""}
    ${diagnostics.length ? `
      <details class="job-phase-diagnostics">
        <summary>超时诊断阶段</summary>
        <ul>${diagnostics.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      </details>
    ` : ""}
  `;
}

function renderJobStatus(job, fallbackMessage = "") {
  if (!progressBar || !jobMessage || !job) {
    return;
  }
  progressBar.style.width = `${job.progress || 0}%`;
  jobMessage.className = `job-message ${job.status === "failed" ? "failed" : job.status === "success" ? "success" : ""}`;
  jobMessage.textContent = `${job.status || "running"} · ${job.progress || 0}% · ${job.message || fallbackMessage || ""}`;
  renderJobPhase(job);
}

function setCreatorCloneDistillButtonsLocked(locked) {
  creatorCloneDistillRunning = Boolean(locked);
  if (creatorCloneDistillButton) {
    creatorCloneDistillButton.disabled = Boolean(locked);
  }
  if (creatorCloneBatchDistillButton) {
    creatorCloneBatchDistillButton.disabled = Boolean(locked);
  }
  renderCreatorCloneStageChrome();
}

function setCreatorCloneEnrichmentLocked(locked) {
  creatorCloneEnrichmentRunning = Boolean(locked);
  if (profileSelectedBuildButton) {
    profileSelectedBuildButton.disabled = Boolean(locked);
  }
  renderCreatorCloneStageChrome();
}

function normalizeItems(value) {
  if (!value) {
    return [];
  }
  if (Array.isArray(value)) {
    return value.filter((item) => item !== undefined && item !== null && item !== "");
  }
  return [value];
}

function sampleViewItemFromCreatorSample(sample = {}) {
  const metrics = sample.metrics || {};
  const evidence = sample.evidence || {};
  const raw = sample.raw || {};
  return {
    sample_id: sample.sample_id || raw.sample_id || "",
    source_type: sample.source || raw.source_type || "unknown",
    source_url: sample.source_url || raw.source_url || "",
    webpage_url: sample.source_url || raw.webpage_url || raw.source_url || "",
    aweme_id: sample.platform_item_id || raw.aweme_id || "",
    title: sample.title || raw.title || "",
    desc: sample.description || raw.desc || "",
    author: sample.author || raw.author || "",
    cover_url: sample.cover_url || raw.cover_url || "",
    media_type: sample.media_kind || raw.media_type || "unknown",
    like_count: Number(metrics.like_count || raw.like_count || 0),
    comment_count: Number(metrics.comment_count || raw.comment_count || 0),
    share_count: Number(metrics.share_count || raw.share_count || 0),
    collect_count: Number(metrics.collect_count || raw.collect_count || 0),
    view_count: Number(metrics.view_count || raw.view_count || 0),
    engagement_score: Number(metrics.engagement_score || raw.engagement_score || 0),
    create_time: sample.created_at || raw.create_time || "",
    case_id: sample.case_id || raw.case_id || "",
    understanding_level: evidence.level || raw.understanding_level || "metadata_only",
    has_video: Boolean(evidence.has_video || raw.has_video),
    has_frames: Boolean(evidence.has_frames || raw.has_frames),
    has_asr: Boolean(evidence.has_asr || raw.has_asr),
    has_ocr: Boolean(evidence.has_ocr || raw.has_ocr),
    has_comments: Boolean(evidence.has_comments || raw.has_comments),
    enrichment_status: evidence.enrichment_status || raw.enrichment_status || "pending",
    asr_status: evidence.asr_status || raw.asr_status || "pending",
    ocr_status: evidence.ocr_status || raw.ocr_status || "pending",
    analysis_status: evidence.analysis_status || raw.analysis_status || "not_analyzed",
    selected: Boolean(sample.selected || raw.selected),
    tags: normalizeItems(sample.tags || raw.tags),
    notes: raw.notes || "",
  };
}

function creatorSampleFromViewItem(item = {}) {
  const key = sampleViewItemKey(item);
  const evidenceLevel = item.understanding_level || (item.has_frames || item.has_asr || item.has_ocr || item.has_comments ? "partial" : "metadata_only");
  return {
    sample_id: key,
    source: item.source_type || "douyin",
    source_url: item.source_url || item.webpage_url || "",
    platform_item_id: item.aweme_id || "",
    title: item.title || item.desc || "",
    description: item.desc || "",
    author: item.author || "",
    cover_url: item.cover_url || "",
    media_kind: item.media_type || "unknown",
    metrics: {
      like_count: Number(item.like_count || 0),
      comment_count: Number(item.comment_count || 0),
      share_count: Number(item.share_count || 0),
      collect_count: Number(item.collect_count || 0),
      view_count: Number(item.view_count || 0),
      engagement_score: Number(item.engagement_score || 0),
    },
    evidence: {
      level: evidenceLevel,
      has_video: Boolean(item.has_video),
      has_frames: Boolean(item.has_frames),
      has_asr: Boolean(item.has_asr),
      has_ocr: Boolean(item.has_ocr),
      has_comments: Boolean(item.has_comments),
      enrichment_status: item.enrichment_status || "pending",
      asr_status: item.asr_status || "pending",
      ocr_status: item.ocr_status || "pending",
      analysis_status: item.analysis_status || "not_analyzed",
    },
    case_id: item.case_id || "",
    tags: normalizeItems(item.tags),
    created_at: item.create_time || "",
    selected: Boolean(item.selected),
    raw: {...item},
  };
}

function creatorProjectFromCloneSet(set = {}) {
  if (!set?.set_id) {
    return null;
  }
  const profile = set.profile_metadata || {};
  const samples = normalizeItems(set.samples).map(creatorSampleFromViewItem);
  const selected = normalizeItems(set.selected_sample_ids);
  return {
    project_id: set.set_id,
    title: set.title || "创作者蒸馏素材池",
    profile: {
      creator_id: profile.sec_user_id || set.creator_name || set.set_id,
      display_name: set.creator_name || profile.nickname || "",
      platform: set.source_platform || profile.source_platform || "unknown",
      source_url: profile.profile_url || "",
      bio: profile.bio || "",
      audience: profile.audience || "",
      content_direction: set.content_profile || profile.content_direction || "",
      style_bias: profile.style_bias || "",
      raw_profile: {...profile},
    },
    samples,
    selected_sample_ids: selected,
    warnings: normalizeItems(set.warnings),
    sample_count: samples.length,
    selected_count: selected.length || samples.filter((sample) => sample.selected).length,
    created_at: set.created_at || "",
    updated_at: set.updated_at || "",
  };
}

function creatorProjectSampleViewItems() {
  return normalizeItems(currentCreatorIntelligenceProject?.samples).map(sampleViewItemFromCreatorSample);
}

function activeCreatorSampleViewItems() {
  const projectItems = creatorProjectSampleViewItems();
  const localItems = normalizeItems(runtimeSampleRows);
  if (!projectItems.length) {
    return localItems;
  }
  if (!localItems.length) {
    return projectItems;
  }
  const localByKey = new Map(
    localItems
      .map((item) => [sampleViewItemKey(item), item])
      .filter(([key]) => Boolean(key)),
  );
  const merged = projectItems.map((item) => {
    const local = localByKey.get(sampleViewItemKey(item));
    return local ? {...item, ...local} : item;
  });
  const projectKeys = new Set(merged.map(sampleViewItemKey).filter(Boolean));
  localItems.forEach((item) => {
    const key = sampleViewItemKey(item);
    if (key && !projectKeys.has(key)) {
      merged.push(item);
    }
  });
  return merged;
}

function syncCreatorProjectSamplesFromViewItems(items = runtimeSampleRows) {
  if (!currentCreatorIntelligenceProject?.project_id) {
    return;
  }
  const rows = normalizeItems(items);
  const existingSelected = profileSelectedKeys.size
    ? new Set(profileSelectedKeys)
    : new Set(normalizeItems(currentCreatorIntelligenceProject.selected_sample_ids).map(String));
  const samples = rows.map((item) => {
    const key = sampleViewItemKey(item);
    return creatorSampleFromViewItem({
      ...item,
      selected: Boolean(key && existingSelected.has(String(key))),
    });
  });
  const availableKeys = new Set(samples.map((sample) => sample.sample_id).filter(Boolean));
  const selectedSampleIds = [...existingSelected].filter((key) => availableKeys.has(String(key)));
  currentCreatorIntelligenceProject = {
    ...currentCreatorIntelligenceProject,
    samples,
    selected_sample_ids: selectedSampleIds,
    sample_count: samples.length,
    selected_count: selectedSampleIds.length || samples.filter((sample) => sample.selected).length,
    updated_at: new Date().toISOString(),
  };
  if (currentCreatorRuntimeState) {
    currentCreatorRuntimeState = {
      ...currentCreatorRuntimeState,
      project: currentCreatorIntelligenceProject,
    };
  }
}

function invalidateCreatorRuntimeReportForSelectionChange() {
  currentCreatorRuntimeReport = null;
  currentCreatorIntelligenceStrategy = null;
  currentDistillPrompt = "";
  if (currentCreatorRuntimeState?.strategy_output) {
    currentCreatorRuntimeState = {
      ...currentCreatorRuntimeState,
      strategy_output: {},
    };
  }
  creatorCloneResultCard?.classList.add("hidden");
}

function cloneSetFromCreatorIntelligenceProject(payload = {}) {
  const project = payload.project || {};
  if (!project.project_id) {
    return null;
  }
  const profile = project.profile || {};
  const rawProfile = profile.raw_profile || {};
  return {
    set_id: project.project_id,
    title: project.title || "创作者蒸馏素材池",
    creator_name: profile.display_name || "",
    source_platform: profile.platform || "unknown",
    content_profile: rawProfile.content_profile || "auto",
    profile_metadata: {
      ...rawProfile,
      sec_user_id: rawProfile.sec_user_id || profile.creator_id || "",
      profile_url: rawProfile.profile_url || profile.source_url || "",
      bio: rawProfile.bio || profile.bio || "",
      source_platform: rawProfile.source_platform || profile.platform || "unknown",
    },
    samples: normalizeItems(project.samples).map(sampleViewItemFromCreatorSample),
    selected_sample_ids: normalizeItems(project.selected_sample_ids),
    warnings: normalizeItems(project.warnings),
    created_at: project.created_at || "",
    sample_count: project.sample_count || normalizeItems(project.samples).length,
    selected_count: project.selected_count || normalizeItems(project.selected_sample_ids).length,
    performance_segments: payload.behavior_model?.performance_segments || {},
  };
}

function profilePayloadFromCreatorIntelligenceProject(payload = {}) {
  return {
    set: cloneSetFromCreatorIntelligenceProject(payload),
    creator_intelligence: {
      project: payload.project || null,
      workflow: payload.workflow || null,
      behavior_model: payload.behavior_model || null,
      strategy_output: payload.strategy_output || null,
      runtime_state: payload.runtime_state || null,
    },
    exports: payload.exports || {},
    provider: "creator intelligence project",
  };
}

function creatorStrategyFromResult(result = {}) {
  return result?.creator_clone_strategy || currentCreatorIntelligenceStrategy || null;
}

function creatorCloneResultFromStrategyOutput(strategy = {}) {
  if (!strategy || typeof strategy !== "object") {
    return null;
  }
  return {
    summary: strategy.positioning || "创作者策略输出已恢复。",
    creator_clone_strategy: strategy,
    creator_positioning: {
      what_the_creator_sells: strategy.positioning || "",
    },
    topic_buckets: normalizeItems(strategy.content_strategy).map((item) => ({name: formatReportValue(item)})),
    expression_patterns: {
      opening_hooks: normalizeItems(strategy.hooks),
    },
    transferable_formulas: normalizeItems(strategy.templates),
    creator_clone_spec: {
      anti_patterns: normalizeItems(strategy.anti_patterns),
      self_check_rubric: normalizeItems(strategy.validation_rules),
    },
    candidate_ideas: normalizeItems(strategy.idea_bank),
    evidence_gaps: [],
    next_actions: normalizeItems(strategy.validation_rules),
  };
}

function formatReportValue(value) {
  if (Array.isArray(value)) {
    return value.map(formatReportValue).filter(isMeaningfulReportText).join(" / ");
  }
  if (value && typeof value === "object") {
    return Object.entries(value)
      .filter(([, item]) => publicValueHasContent(item))
      .map(([key, item]) => `${key}: ${formatReportValue(item)}`)
      .join("；");
  }
  return String(value ?? "");
}

function reportItemPrimaryText(item) {
  if (!item || typeof item !== "object" || Array.isArray(item)) {
    return formatReportValue(item);
  }
  return (
    item.name
    || item.title
    || item.formula
    || item.summary
    || item.description
    || item.point
    || item.template
    || item.idea
    || item.why_it_works
    || formatReportValue(item)
  );
}

function isMeaningfulReportText(value) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!text) {
    return false;
  }
  if (/^(undefined|null|NaN)$/i.test(text)) {
    return false;
  }
  if (/^暂无/.test(text)) {
    return false;
  }
  const compact = text.replace(/[：:；;,，。、\s/·|｜\-—_]/g, "");
  if (!compact) {
    return false;
  }
  const placeholderPatterns = [
    /^公式适用结构风险$/,
    /^选题强度制作要求$/,
    /^模板$/,
    /^规则$/,
    /^风险$/,
    /^低置信度规则$/,
  ];
  return !placeholderPatterns.some((pattern) => pattern.test(compact));
}

function renderPublicList(items, emptyText = "暂无明确结论。") {
  const seen = new Set();
  const values = normalizeItems(items)
    .map(formatReportValue)
    .map((item) => item.replace(/\s+/g, " ").trim())
    .filter(isMeaningfulReportText)
    .filter((item) => {
      if (seen.has(item)) {
        return false;
      }
      seen.add(item);
      return true;
    });
  if (!values.length) {
    return `<p class="muted compact-copy">${escapeHtml(emptyText)}</p>`;
  }
  return `<ul class="public-report-list">${values.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function publicValueHasContent(value) {
  if (value === undefined || value === null) {
    return false;
  }
  if (Array.isArray(value)) {
    return value.some((item) => publicValueHasContent(item));
  }
  if (typeof value === "object") {
    return Object.values(value).some((item) => publicValueHasContent(item));
  }
  return isMeaningfulReportText(value);
}

function renderSegmentSampleList(items, metricKey, metricLabel, emptyText = "暂无样本。") {
  const values = normalizeItems(items)
    .map((item) => {
      if (!item || typeof item !== "object") {
        return formatReportValue(item);
      }
      const title = item.title || item.desc || item.nickname || item.author || item.source_url || "未命名样本";
      const metricValue = item.metric_value ?? item[metricKey];
      const metrics = [
        metricValue !== undefined && metricValue !== null && metricValue !== "" ? `${metricLabel} ${formatNumber(metricValue)}` : "",
        Number(item.like_count || 0) && metricKey !== "like_count" ? `赞 ${formatNumber(item.like_count)}` : "",
        Number(item.comment_count || 0) && metricKey !== "comment_count" ? `评 ${formatNumber(item.comment_count)}` : "",
        Number(item.share_count || 0) && metricKey !== "share_count" ? `分享 ${formatNumber(item.share_count)}` : "",
        Number(item.collect_count || 0) && metricKey !== "collect_count" ? `收藏 ${formatNumber(item.collect_count)}` : "",
      ].filter(Boolean).slice(0, 3).join(" · ");
      return metrics ? `${title}（${metrics}）` : title;
    })
    .filter(Boolean);
  return renderPublicList(values, emptyText);
}

function renderPublicFields(rows) {
  const values = rows.filter(([, value]) => value !== undefined && value !== null && value !== "");
  if (!values.length) {
    return '<p class="muted compact-copy">暂无明确结论。</p>';
  }
  return `
    <dl class="public-report-fields">
      ${values
        .map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(formatReportValue(value))}</dd>`)
        .join("")}
    </dl>
  `;
}

function renderPublicCard(title, body, tone = "") {
  return `
    <article class="public-report-card ${escapeHtml(tone)}">
      <h4>${escapeHtml(title)}</h4>
      ${body}
    </article>
  `;
}

function renderPublicAnalysisReport(result) {
  const hook = result.hook_analysis || {};
  const visual = result.visual_analysis || {};
  const replication = result.replication || {};
  const publish = result.publish_package || {};
  const category = result.content_category_label || result.content_category || "短视频";
  const confidence = result.confidence ? `置信度 ${result.confidence}` : "";
  return `
    <section class="public-analysis-hero">
      <span>${escapeHtml(category)}${confidence ? ` · ${escapeHtml(confidence)}` : ""}</span>
      <strong>${escapeHtml(result.summary || "AI 已完成拆解，但没有返回摘要。")}</strong>
    </section>
    <div class="public-report-grid">
      ${renderPublicCard(
        "0-3 秒抓人点",
        `
          ${renderPublicFields([
            ["第一眼", hook.first_impression],
            ["停留理由", hook.why_stop_scrolling],
            ["优化方向", hook.optimization],
          ])}
          ${renderPublicList(hook.first_3_seconds, "暂无逐秒观察。")}
        `,
        "featured",
      )}
      ${renderPublicCard(
        "画面 / 人设 / 氛围",
        `
          ${renderPublicFields([
            ["主体", visual.subject],
            ["构图", visual.composition],
            ["光线色彩", visual.lighting_color],
            ["动作节奏", visual.movement_rhythm],
          ])}
          ${renderPublicList(visual.style_keywords, "暂无风格关键词。")}
        `,
      )}
      ${renderPublicCard(
        "可复刻点",
        `
          ${renderPublicFields([
            ["复刻角度", replication.remake_angle],
            ["开头 3 秒", replication.opening_3s],
          ])}
          ${renderPublicList(replication.copyable_points, "暂无可复刻动作。")}
        `,
        "featured",
      )}
      ${renderPublicCard(
        "风险与改编边界",
        `
          <h5>不要照搬</h5>
          ${renderPublicList(replication.avoid_copying, "暂无明确边界。")}
          <h5>风险提醒</h5>
          ${renderPublicList(result.risks, "暂无风险提醒。")}
        `,
      )}
      ${renderPublicCard(
        "标题与发布灵感",
        `
          ${renderPublicFields([["发布文案", publish.caption]])}
          <h5>标题方向</h5>
          ${renderPublicList(publish.titles, "暂无标题建议。")}
          <h5>标签</h5>
          ${renderPublicList(publish.hashtags, "暂无标签建议。")}
        `,
      )}
      ${renderPublicCard("下一步", renderPublicList(result.next_actions, "暂无下一步建议。"))}
    </div>
  `;
}

function renderLlmStatus(llm) {
  const configured = Boolean(llm.configured);
  llmStatusBadge.textContent = configured ? "已启用" : "未配置";
  llmStatusBadge.classList.toggle("success", configured);
  llmStatusBadge.classList.toggle("muted-badge", !configured);
  testLlmButton.disabled = !configured;
  llmConfigHint.classList.toggle("hidden", configured);
  llmStatusList.innerHTML = `
    <dl>
      <dt>Provider</dt><dd>${escapeHtml(llm.provider || "disabled")}</dd>
      <dt>API Base</dt><dd>${escapeHtml(llm.api_base || "")}</dd>
      <dt>Model</dt><dd>${escapeHtml(llm.model || "未配置")}</dd>
      <dt>API Key</dt><dd>${llm.has_api_key ? `已配置 ${escapeHtml(llm.masked_api_key || "")}` : "未配置"}</dd>
      <dt>图片帧数</dt><dd>${escapeHtml(llm.llm_max_keyframes ?? "")}</dd>
      <dt>Temperature</dt><dd>${escapeHtml(llm.temperature ?? "")}</dd>
    </dl>
    <p class="muted compact-copy">${escapeHtml(llm.status_message || "")}</p>
  `;
  if (llmProviderInput) {
    llmProviderInput.value = llm.provider || "disabled";
  }
  if (llmApiBaseInput) {
    llmApiBaseInput.value = llm.api_base || "";
  }
  if (llmModelInput) {
    llmModelInput.value = llm.model || "";
  }
  if (llmTimeoutInput) {
    llmTimeoutInput.value = llm.timeout_seconds || 90;
  }
  if (llmTemperatureInput) {
    llmTemperatureInput.value = llm.temperature ?? 0.2;
  }
  if (llmApiKeyInput) {
    llmApiKeyInput.value = "";
    llmApiKeyInput.placeholder = llm.has_api_key ? `留空保留当前 Key（${llm.masked_api_key || "已配置"}）` : "粘贴 API Key";
  }
  if (llmClearKeyInput) {
    llmClearKeyInput.checked = false;
  }
}

function sortCreatorSampleViewItems(items, sortBy) {
  const key = ["like_count", "comment_count", "share_count", "collect_count", "engagement_score", "create_time"].includes(sortBy)
    ? sortBy
    : "like_count";
  return [...items].sort((left, right) => {
    const leftValue = left[key] || 0;
    const rightValue = right[key] || 0;
    return rightValue > leftValue ? 1 : rightValue < leftValue ? -1 : 0;
  });
}

function filterCreatorSampleViewItems(items, filterBy) {
  const filter = ["all", "buildable", "metadata_only", "has_frames", "ready_evidence"].includes(filterBy)
    ? filterBy
    : "all";
  if (filter === "all") {
    return [...items];
  }
  return items.filter((item) => {
    if (filter === "buildable") return isSampleViewItemBuildable(item);
    if (filter === "metadata_only") return !item.understanding_level || item.understanding_level === "metadata_only";
    if (filter === "has_frames") return Boolean(item.has_frames);
    if (filter === "ready_evidence") return profileEvidenceScore(item) >= 2;
    return true;
  });
}

function filterCreatorSampleViewItemsByMedia(items, mediaType) {
  const filter = ["all", "video", "image", "unknown"].includes(mediaType) ? mediaType : "all";
  if (filter === "all") {
    return [...items];
  }
  return items.filter((item) => {
    const type = item.media_type || "unknown";
    if (filter === "unknown") {
      return !["video", "image"].includes(type);
    }
    return type === filter;
  });
}

function visibleCreatorSampleViewItems() {
  const mediaFiltered = filterCreatorSampleViewItemsByMedia(activeCreatorSampleViewItems(), profileMediaFilter?.value || "all");
  return sortCreatorSampleViewItems(filterCreatorSampleViewItems(mediaFiltered, profileEvidenceFilter?.value || "all"), profileSort?.value || "like_count");
}

function selectedCreatorSampleViewItems() {
  return activeCreatorSampleViewItems().filter((item) => profileSelectedKeys.has(sampleViewItemKey(item)));
}

function sampleViewItemKey(item) {
  return item?.sample_id || item?.aweme_id || item?.case_id || item?.source_url || "";
}

function sampleViewItemMatchesKeySet(item, keySet) {
  return [
    item?.sample_id,
    item?.aweme_id,
    item?.case_id,
    item?.source_url,
    item?.webpage_url,
  ].some((key) => key && keySet.has(String(key)));
}

// Creator Clone: import
function setActiveImportMode(mode = "browser") {
  const activeMode = ["browser", "manual", "structured", "case", "handoff"].includes(mode) ? mode : "browser";
  profileImportModeButtons.forEach((button) => {
    const active = button.dataset.profileImportMode === activeMode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  profileImportPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.profileImportPanel === activeMode);
  });
  renderCreatorCloneNextAction();
}

function activeProfileImportMode() {
  return profileImportModeButtons.find((button) => button.classList.contains("active"))?.dataset.profileImportMode || "browser";
}

function creatorCloneUnifiedInputValue() {
  return String(profileQuickInput?.value || "").trim();
}

function setCreatorCloneRestoredInput(value = "") {
  const restoredValue = String(value || "").trim();
  profileQuickInputRestoredValue = restoredValue;
  if (profileQuickInput) {
    profileQuickInput.value = restoredValue;
  }
}

function clearCreatorCloneUnifiedInput() {
  if (profileQuickInput) {
    profileQuickInput.value = "";
  }
  profileQuickInputRestoredValue = "";
}

function hasPendingQuickImportInput() {
  const value = creatorCloneUnifiedInputValue();
  return Boolean(value && value !== profileQuickInputRestoredValue);
}

function hasCreatorCloneImportInput() {
  const quick = creatorCloneUnifiedInputValue();
  if (quick) return true;
  if (!profileForm) return false;
  const formData = new FormData(profileForm);
  return Boolean(
    String(formData.get("profile_url") || "").trim()
      || String(formData.get("manual_links") || "").trim()
      || String(formData.get("structured_items") || "").trim()
      || String(formData.get("case_ids") || "").trim()
      || String(formData.get("handoff_manifest") || "").trim(),
  );
}

function inferCreatorCloneImportMode() {
  const quick = creatorCloneUnifiedInputValue();
  if (quick) {
    const firstUrl = firstUrlFromText(quick);
    const target = firstUrl || quick;
    if (/^\s*[\[{]/.test(quick) || /^aweme_id\s*,/im.test(quick)) return "structured";
    if (/^case_[A-Za-z0-9_,-\s]+$/.test(quick)) return "case";
    if (/douyin\.com\/user\//i.test(target) || /^MS4w[A-Za-z0-9_.-]+/.test(target)) return "browser";
    return "manual";
  }
  const formData = new FormData(profileForm);
  if (String(formData.get("handoff_manifest") || "").trim()) return "handoff";
  if (String(formData.get("structured_items") || "").trim()) return "structured";
  if (String(formData.get("case_ids") || "").trim()) return "case";
  if (String(formData.get("manual_links") || "").trim()) return "manual";
  if (String(formData.get("profile_url") || "").trim()) return "browser";
  return activeProfileImportMode();
}

function syncUnifiedInputToImportFields(mode) {
  const quick = creatorCloneUnifiedInputValue();
  if (!quick || !profileForm) return;
  if (mode === "browser") {
    profileForm.elements.profile_url.value = firstUrlFromText(quick) || quick;
    return;
  }
  if (mode === "manual" && profileManualLinks) {
    profileManualLinks.value = quick;
    return;
  }
  if (mode === "structured") {
    profileForm.elements.structured_items.value = quick;
    return;
  }
  if (mode === "case") {
    profileForm.elements.case_ids.value = quick;
  }
}

function isSampleViewItemBuildable(item) {
  return Boolean(item?.aweme_id) && item?.can_build_case !== false && !["image", "text"].includes(item?.media_type || "");
}

function hasPendingEnrichment(items = selectedCreatorSampleViewItems()) {
  return normalizeItems(items).some((item) => isSampleViewItemBuildable(item) && !item.case_id && !item.has_frames);
}

function applyCreatorIntelligencePayload(payload = {}) {
  const intelligence = payload?.creator_intelligence || payload?.set?.creator_intelligence || null;
  const runtimeState = intelligence?.runtime_state || payload?.runtime_state || null;
  const nextProject = intelligence?.project || payload?.project || creatorProjectFromCloneSet(payload?.set) || currentCreatorIntelligenceProject;
  const previousProjectId = currentCreatorIntelligenceProject?.project_id || "";
  const nextProjectId = nextProject?.project_id || "";
  const projectChanged = previousProjectId && nextProjectId && previousProjectId !== nextProjectId;
  currentCreatorIntelligenceProject = nextProject;
  const incomingStrategy = intelligence?.strategy_output || payload?.strategy_output || null;
  currentCreatorIntelligenceStrategy = incomingStrategy || (projectChanged ? null : currentCreatorIntelligenceStrategy);
  const legacyWorkflow = intelligence?.workflow || payload?.workflow || null;
  const legacyBehavior = intelligence?.behavior_model || payload?.behavior_model || null;
  currentCreatorRuntimeState = runtimeState || (projectChanged ? null : currentCreatorRuntimeState);
  if (!runtimeState && (legacyWorkflow || legacyBehavior)) {
    currentCreatorRuntimeState = {
      ...(currentCreatorRuntimeState || {}),
      workflow: legacyWorkflow || currentCreatorRuntimeState?.workflow || null,
      behavior_model: legacyBehavior || currentCreatorRuntimeState?.behavior_model || null,
    };
  }
}

function creatorRuntimeCurrentStep() {
  return currentCreatorRuntimeState?.current_step || {};
}

function creatorRuntimePrimaryAction() {
  const action = currentCreatorRuntimeState?.primary_action || {};
  if (action.command || action.label || action.summary) {
    return action;
  }
  const workflow = currentCreatorRuntimeState?.workflow || {};
  const ui = workflow?.ui || {};
  return ui.next_action || workflow?.next_action || {};
}

function creatorRuntimeStage() {
  return normalizeProfileStage(creatorRuntimeCurrentStep().stage || "import");
}

function creatorRuntimeActionState() {
  return creatorRuntimePrimaryAction().state || "";
}

function creatorRuntimeMetaFallback() {
  if (hasCreatorCloneImportInput()) {
    return {
      step: "当前步骤：导入素材",
      button: "下一步：开始导入素材",
      command: "import_input",
      summary: "输入主页 URL、作品链接、aweme_id 或分享文案后，点击主按钮开始。",
      disabled: false,
    };
  }
  return {
    step: "当前步骤：导入素材",
    button: "下一步：开始导入素材",
    command: "import_input",
    summary: "等待输入主页 URL、作品链接、aweme_id 或分享文案。",
    disabled: false,
  };
}

function stageIndexFromName(stage) {
  return {
    import: 0,
    pool: 1,
    select: 2,
    enrich: 3,
    distill: 4,
    export: 5,
  }[stage] ?? 0;
}

function normalizeProfileStage(stage) {
  return ["import", "pool", "select", "enrich", "distill", "export"].includes(stage) ? stage : "import";
}

function setProfileStageView(stage, {scroll = false} = {}) {
  profileStageView = normalizeProfileStage(stage);
  rememberRecentProfileStage(profileStageView);
  renderProfileStageView();
  renderCreatorCloneStageChrome();
  if (scroll) {
    document.querySelector(".profile-main-flow")?.scrollIntoView({behavior: "smooth", block: "start"});
  }
}

function activeProfileStage() {
  if (hasPendingQuickImportInput()) {
    return "import";
  }
  return normalizeProfileStage(profileStageView || creatorRuntimeStage());
}

function creatorWorkflowProgressStage() {
  if (hasPendingQuickImportInput()) {
    return "import";
  }
  const runtimeStage = creatorRuntimeCurrentStep().stage;
  if (runtimeStage) {
    return normalizeProfileStage(runtimeStage);
  }
  return activeProfileStage();
}

function lockedProfileNavigationStage() {
  if (creatorCloneEnrichmentRunning) {
    return "enrich";
  }
  if (creatorCloneDistillRunning) {
    return "distill";
  }
  return "";
}

function canNavigateProfileStage(stage) {
  const lockedStage = lockedProfileNavigationStage();
  return !lockedStage || normalizeProfileStage(stage) === lockedStage;
}

function renderProfileStageView() {
  const activeStage = activeProfileStage();
  profileStageSections.forEach((section) => {
    const stages = String(section.dataset.profileStageSection || "").split(/\s+/).filter(Boolean);
    const isActive = stages.includes(activeStage);
    section.classList.toggle("stage-hidden", !isActive);
    if (isActive) {
      section.classList.remove("hidden");
    }
  });
  if (profileResultsCard) {
    const shouldShowResultContainer = activeStage !== "import" && (activeCreatorSampleViewItems().length || currentCloneSetId || currentCreatorRuntimeReport);
    profileResultsCard.classList.toggle("hidden", !shouldShowResultContainer);
  }
}

function revealProfileQueueCard() {
  profileEnrichmentSection?.classList.remove("hidden");
  profileEnrichmentSection?.classList.remove("stage-hidden");
  profileQueueCard?.classList.remove("hidden");
}

function syncProfileStageToWizard({scroll = false} = {}) {
  setProfileStageView(creatorRuntimeStage(), {scroll});
}

function creatorCloneStageMeta(stage = activeProfileStage()) {
  void stage;
  const step = creatorRuntimeCurrentStep();
  const action = creatorRuntimePrimaryAction();
  if (step.label || action.command || action.label) {
    return {
      step: step.label || "当前步骤：导入素材",
      button: action.label || "等待状态更新",
      command: action.command || "wait",
      summary: action.summary || "",
      disabled: creatorCloneNextActionRunning || Boolean(action.disabled),
    };
  }
  return creatorRuntimeMetaFallback();
}

function creatorCloneStateMeta(state = creatorRuntimeActionState()) {
  void state;
  return creatorCloneStageMeta();
}

function creatorCloneActionStateForCurrentView(state = creatorRuntimeActionState()) {
  return creatorRuntimePrimaryAction().state || state;
}

function renderCreatorCloneRecommendation() {
  if (!creatorCloneRecommendation) {
    return;
  }
  creatorCloneRecommendation.classList.add("hidden");
  creatorCloneRecommendation.innerHTML = "";
}

function renderWizardPrimaryAction(state = creatorCloneActionStateForCurrentView()) {
  const meta = creatorCloneStateMeta(state);
  const command = meta.command || "";
  if (creatorCloneNextButton) {
    creatorCloneNextButton.textContent = creatorCloneNextActionRunning ? "处理中..." : meta.button;
    creatorCloneNextButton.dataset.creatorCloneAction = command;
    creatorCloneNextButton.disabled = creatorCloneNextActionRunning || command === "wait" || Boolean(meta.disabled);
  }
}

function renderCreatorCloneStageChrome() {
  const state = creatorCloneActionStateForCurrentView();
  const meta = creatorCloneStateMeta(state);
  const activeStage = creatorWorkflowProgressStage();
  const viewedStage = activeProfileStage();
  const activeStageIndex = stageIndexFromName(activeStage);
  const lockedStage = lockedProfileNavigationStage();
  creatorCloneFlowSteps.forEach((step) => {
    const stage = normalizeProfileStage(step.dataset.profileStageNav || "");
    const index = stageIndexFromName(stage);
    const locked = Boolean(lockedStage && stage !== lockedStage);
    step.classList.toggle("active", index === activeStageIndex);
    step.classList.toggle("completed", index < activeStageIndex);
    step.classList.toggle("viewing", stage === viewedStage && index !== activeStageIndex);
    step.classList.toggle("locked", locked);
    step.disabled = locked;
    step.title = locked ? "当前任务正在运行，完成后会自动进入下一步。" : "";
    step.setAttribute("aria-current", index === activeStageIndex ? "step" : "false");
  });
  if (creatorCloneCurrentStep) {
    creatorCloneCurrentStep.textContent = meta.step;
  }
  if (creatorCloneNextSummary) {
    creatorCloneNextSummary.textContent = meta.summary;
  }
  if (profileNextAction) {
    profileNextAction.textContent = meta.step;
  }
  renderWizardPrimaryAction(state);
  renderCreatorCloneRecommendation();
}

function renderCreatorCloneNextAction() {
  renderCreatorCloneStageChrome();
  renderProfileStageView();
}

// Creator Clone: sample pool
function setCreatorCloneStep(step = creatorRuntimeActionState()) {
  void step;
  profileEnrichmentSection?.classList.remove("hidden");
  profileDistillationSection?.classList.remove("hidden");
  renderCreatorCloneNextAction();
}

function renderCreatorCloneOverview(summary = {}) {
  if (!profileSummary) {
    return;
  }
  const items = activeCreatorSampleViewItems();
  const selected = selectedCreatorSampleViewItems();
  const buildable = items.filter(isSampleViewItemBuildable);
  const coverage = profileEvidenceCoverageSummary(items);
  const nextAction = creatorCloneStateMeta().summary || "等待当前步骤完成。";
  const total = summary.scanned_count || items.length;
  profileSummary.innerHTML = `
    <article><span>素材数量</span><strong>${formatNumber(total)}</strong></article>
    <article><span>已选样本</span><strong>${formatNumber(selected.length)}</strong></article>
    <article><span>可富化视频</span><strong>${formatNumber(buildable.length)}</strong></article>
    <article class="wide"><span>证据覆盖</span><strong>${escapeHtml(coverage)}</strong></article>
    <article class="wide"><span>下一步建议</span><strong>${escapeHtml(nextAction)}</strong></article>
  `;
  setCreatorCloneStep();
}

// Creator Clone: selection
function updateCreatorCloneSelectionStatus() {
  const selected = selectedCreatorSampleViewItems();
  const buildable = selected.filter(isSampleViewItemBuildable);
  const unbuildableCount = selected.length - buildable.length;
  const counts = selected.reduce(
    (acc, item) => {
      const level = item.understanding_level || "metadata_only";
      acc[level] = (acc[level] || 0) + 1;
      return acc;
    },
    {full: 0, partial: 0, metadata_only: 0},
  );
  if (creatorCloneSelectionStatus) {
    creatorCloneSelectionStatus.textContent = `已选 ${selected.length} 条；可富化 ${buildable.length}/${PROFILE_BUILD_MAX_ITEMS} 条；不可富化 ${unbuildableCount} 条；单次蒸馏最多 ${CREATOR_CLONE_MAX_DISTILL_SAMPLES} 条，分批蒸馏最多 ${PROFILE_BUILD_MAX_ITEMS} 条。完整 ${counts.full || 0}，部分 ${counts.partial || 0}，仅元数据 ${counts.metadata_only || 0}。`;
  }
  if (profileSelectedBuildButton) {
    const disabledReason = creatorCloneEnrichmentRunning
      ? "证据富化任务正在运行。"
      : !selected.length
      ? "请先选择代表样本。"
      : buildable.length > PROFILE_BUILD_MAX_ITEMS
        ? `可下载视频超过当前富化上限 ${PROFILE_BUILD_MAX_ITEMS} 条。`
        : "";
    profileSelectedBuildButton.disabled = Boolean(disabledReason);
    profileSelectedBuildButton.title = disabledReason || (buildable.length
      ? `将富化 ${buildable.length} 条可解析视频，并保留 ${unbuildableCount} 条参考样本`
      : `保存 ${selected.length} 条参考样本，不执行视频下载`);
  }
  const shouldBatchDistill = selected.length > CREATOR_CLONE_MAX_DISTILL_SAMPLES;
  if (creatorCloneDistillButton) {
    creatorCloneDistillButton.classList.toggle("hidden", shouldBatchDistill);
    creatorCloneDistillButton.textContent = "高级：执行蒸馏";
    const distillDisabledReason = creatorCloneDistillRunning
      ? "大模型蒸馏任务正在运行。"
      : !selected.length
      ? "请先选择要蒸馏的样本。"
      : shouldBatchDistill
        ? `超过 ${CREATOR_CLONE_MAX_DISTILL_SAMPLES} 条时请使用分批蒸馏。`
        : "";
    creatorCloneDistillButton.disabled = Boolean(distillDisabledReason);
    creatorCloneDistillButton.title = distillDisabledReason || `将蒸馏 ${selected.length} 条样本`;
  }
  if (creatorCloneBatchDistillButton) {
    creatorCloneBatchDistillButton.classList.toggle("hidden", !shouldBatchDistill);
    creatorCloneBatchDistillButton.textContent = "高级：分批蒸馏";
    const batchDisabledReason = creatorCloneDistillRunning
      ? "大模型蒸馏任务正在运行。"
      : !selected.length
      ? "请先选择要分批蒸馏的样本。"
      : selected.length <= CREATOR_CLONE_MAX_DISTILL_SAMPLES
        ? `${CREATOR_CLONE_MAX_DISTILL_SAMPLES} 条以内请使用执行蒸馏。`
      : selected.length > PROFILE_BUILD_MAX_ITEMS
        ? `分批蒸馏最多支持 ${PROFILE_BUILD_MAX_ITEMS} 条样本。`
        : "";
    creatorCloneBatchDistillButton.disabled = Boolean(batchDisabledReason);
    creatorCloneBatchDistillButton.title = batchDisabledReason || `将 ${selected.length} 条样本按每 ${CREATOR_CLONE_MAX_DISTILL_SAMPLES} 条一批蒸馏并汇总`;
  }
  renderProfileEnrichmentPlan(selected, buildable);
  renderProfileDistillReadiness(selected);
  renderCreatorCloneOverview(profileScanPayload?.summary || cloneSummaryFromSet(profileScanPayload?.set) || {});
}

function selectedSampleReason(item) {
  const key = sampleViewItemKey(item);
  if (!key) {
    return "手动选择";
  }
  const highestLikes = topCreatorSampleViewItemsBy("like_count", 3).some((candidate) => sampleViewItemKey(candidate) === key);
  const highestComments = topCreatorSampleViewItemsBy("comment_count", 3).some((candidate) => sampleViewItemKey(candidate) === key);
  const highestShares = topCreatorSampleViewItemsBy("share_count", 3).some((candidate) => sampleViewItemKey(candidate) === key);
  const highestCollects = topCreatorSampleViewItemsBy("collect_count", 3).some((candidate) => sampleViewItemKey(candidate) === key);
  const newest = topCreatorSampleViewItemsBy("create_time", 3).some((candidate) => sampleViewItemKey(candidate) === key);
  const reasons = [];
  if (highestLikes) reasons.push("高赞");
  if (highestComments) reasons.push("高评");
  if (highestShares) reasons.push("高分享");
  if (highestCollects) reasons.push("高收藏");
  if (newest) reasons.push("最新");
  if (isSampleViewItemBuildable(item) && !item.has_frames) reasons.push("待富化");
  return reasons.join(" / ") || "手动选择";
}

function profileMetricText(item) {
  return [
    Number(item.like_count || 0) ? `赞 ${formatNumber(item.like_count)}` : "",
    Number(item.comment_count || 0) ? `评 ${formatNumber(item.comment_count)}` : "",
    Number(item.share_count || 0) ? `分享 ${formatNumber(item.share_count)}` : "",
    Number(item.collect_count || 0) ? `收藏 ${formatNumber(item.collect_count)}` : "",
  ].filter(Boolean).join(" · ");
}

function profileEvidenceText(item) {
  return [
    item.case_id ? "已有素材包" : "",
    item.has_frames ? "关键帧" : "",
    item.has_asr ? "ASR" : "",
    item.has_ocr ? "OCR" : "",
    item.has_comments ? "评论" : "",
    item.understanding_level || "metadata_only",
  ].filter(Boolean).join(" · ");
}

function profileSampleMetaLine(item) {
  const typeLabel = {video: "视频", image: "图文", unknown: "未知"}[item.media_type] || "未知";
  const evidence = `证据 ${profileEvidenceScore(item)}/5`;
  const buildable = isSampleViewItemBuildable(item) ? "可富化" : "参考样本";
  return [
    selectedSampleReason(item),
    profileMetricText(item),
    typeLabel,
    evidence,
    buildable,
    profileEvidenceText(item),
  ].filter(Boolean).join(" · ");
}

function profileEvidenceCounts(selected) {
  return normalizeItems(selected).reduce(
    (acc, item) => {
      acc.video += item.has_video ? 1 : 0;
      acc.frames += item.has_frames ? 1 : 0;
      acc.asr += item.has_asr ? 1 : 0;
      acc.ocr += item.has_ocr ? 1 : 0;
      acc.comments += item.has_comments ? 1 : 0;
      if (item.asr_status && item.asr_status !== "pending") acc.asrChecked += 1;
      if (item.ocr_status && item.ocr_status !== "pending") acc.ocrChecked += 1;
      if (item.asr_status === "provider_missing") acc.asrProviderMissing += 1;
      if (item.ocr_status === "provider_missing") acc.ocrProviderMissing += 1;
      return acc;
    },
    {video: 0, frames: 0, asr: 0, ocr: 0, comments: 0, asrChecked: 0, ocrChecked: 0, asrProviderMissing: 0, ocrProviderMissing: 0},
  );
}

function renderProfileEnrichmentPlan(selected, buildable) {
  if (!profileEvidenceStatus) {
    return;
  }
  const selectedItems = normalizeItems(selected);
  const buildableItems = normalizeItems(buildable);
  const referenceOnlyCount = Math.max(0, selectedItems.length - buildableItems.length);
  const counts = profileEvidenceCounts(selectedItems);
  const missingFrames = buildableItems.filter((item) => !item.has_frames).length;
  const missingAsr = buildableItems.filter((item) => !item.has_asr).length;
  const missingOcr = buildableItems.filter((item) => !item.has_ocr).length;
  const warning = buildableItems.length > PROFILE_BUILD_MAX_ITEMS;
  profileEvidenceStatus.classList.toggle("warning", warning);
  if (!selectedItems.length) {
    profileEvidenceStatus.innerHTML = "先从素材池选择代表样本；富化后会回填视频、关键帧、OCR、ASR 等证据，再进入大模型蒸馏。";
    return;
  }
  const limitNote = buildableItems.length > PROFILE_BUILD_MAX_ITEMS
    ? `可下载视频超过当前富化上限 ${PROFILE_BUILD_MAX_ITEMS} 条，请减少视频样本，避免误批量下载。`
    : "";
  const distillLimitNote = selectedItems.length > CREATOR_CLONE_MAX_DISTILL_SAMPLES
    ? `本轮可先富化全部样本；单次蒸馏上限 ${CREATOR_CLONE_MAX_DISTILL_SAMPLES} 条，超过后请使用“高级：分批蒸馏”做账号级汇总。`
    : "";
  const providerNote = [
    counts.asrProviderMissing ? `ASR provider 未配置 ${counts.asrProviderMissing} 条` : "",
    counts.ocrProviderMissing ? `OCR provider 未配置 ${counts.ocrProviderMissing} 条` : "",
  ].filter(Boolean).join("；");
  const headline = limitNote
    || (buildableItems.length
      ? `点击主按钮“开始富化证据”后，将处理 ${buildableItems.length} 条可下载视频，并保留 ${referenceOnlyCount} 条参考样本。`
      : `已选择 ${referenceOnlyCount} 条参考样本，不执行视频下载，可直接进入大模型蒸馏。`);
  const steps = buildableItems.length
    ? ["下载视频", "生成素材包", "抽关键帧", "OCR 画面文字", "ASR 语音", "写入蒸馏输入"]
    : ["保存参考样本", "整理标题/封面/指标", "写入蒸馏输入"];
  profileEvidenceStatus.innerHTML = `
    <div class="enrichment-plan-head">
      <strong>富化计划</strong>
      <p>${escapeHtml(headline)}</p>
    </div>
    <dl class="enrichment-plan-metrics">
      <div><dt>可下载视频</dt><dd>${formatNumber(buildableItems.length)}</dd></div>
      <div><dt>参考样本</dt><dd>${formatNumber(referenceOnlyCount)}</dd></div>
      <div><dt>待补关键帧</dt><dd>${formatNumber(missingFrames)}</dd></div>
      <div><dt>待补 OCR</dt><dd>${formatNumber(missingOcr)}</dd></div>
      <div><dt>待补 ASR</dt><dd>${formatNumber(missingAsr)}</dd></div>
    </dl>
    <div class="enrichment-plan-steps" aria-label="本轮富化步骤">
      ${steps.map((step) => `<span>${escapeHtml(step)}</span>`).join("")}
    </div>
    <p class="enrichment-plan-note">当前证据：视频 ${counts.video}/${selectedItems.length}，关键帧 ${counts.frames}/${selectedItems.length}，OCR ${counts.ocr}/${selectedItems.length}，ASR ${counts.asr}/${selectedItems.length}，评论 ${counts.comments}/${selectedItems.length}。${providerNote ? `${escapeHtml(providerNote)}。` : ""}${distillLimitNote ? `${escapeHtml(distillLimitNote)}。` : ""}</p>
  `;
}

function renderProfileEvidenceQueueProgress(result = {}) {
  if (!profileEvidenceStatus) {
    return;
  }
  const pipelineSummary = result.pipeline_summary || {};
  const selectedCount = Number(pipelineSummary.selected_count || selectedCreatorSampleViewItems().length || 0);
  const downloadableCount = Number(pipelineSummary.downloadable_count || 0);
  const referenceOnlyCount = Number(pipelineSummary.reference_only_count || 0);
  const downloadedCount = Number(pipelineSummary.downloaded_count || 0);
  const caseCount = Number(pipelineSummary.case_count || result.completed_count || 0);
  const enrichedCount = Number(pipelineSummary.enriched_count || 0);
  const asrCount = Number(pipelineSummary.asr_success_count || 0);
  const ocrCount = Number(pipelineSummary.ocr_success_count || 0);
  const readyCount = Number(pipelineSummary.ready_for_distill_count || 0);
  const failedCount = Number(result.failed_count || 0);
  const totalTarget = downloadableCount || selectedCount || 0;
  const notes = normalizeItems(pipelineSummary.notes).slice(-2);
  profileEvidenceStatus.classList.toggle("warning", Boolean(failedCount));
  profileEvidenceStatus.innerHTML = `
    <div class="enrichment-plan-head">
      <strong>富化进度</strong>
      <p>已选 ${formatNumber(selectedCount)} 条；视频 ${formatNumber(downloadableCount)} 条，参考 ${formatNumber(referenceOnlyCount)} 条。素材包 ${formatNumber(caseCount)}/${formatNumber(totalTarget)}，失败 ${formatNumber(failedCount)}。</p>
    </div>
    <dl class="enrichment-plan-metrics">
      <div><dt>下载</dt><dd>${formatNumber(downloadedCount)}</dd></div>
      <div><dt>素材包</dt><dd>${formatNumber(caseCount)}</dd></div>
      <div><dt>富化</dt><dd>${formatNumber(enrichedCount)}</dd></div>
      <div><dt>ASR</dt><dd>${formatNumber(asrCount)}</dd></div>
      <div><dt>OCR</dt><dd>${formatNumber(ocrCount)}</dd></div>
      <div><dt>可蒸馏</dt><dd>${formatNumber(readyCount)}</dd></div>
    </dl>
    ${notes.length ? `<ul class="profile-queue-note-list">${notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul>` : ""}
  `;
}

function updateProfileChromeContinueButton() {
  if (!profileContinueChromeButton) {
    return;
  }
  const canContinue = Boolean(currentCloneSetId && profileLastChromeProfileValue);
  profileContinueChromeButton.classList.toggle("hidden", !canContinue);
  profileContinueChromeButton.disabled = !canContinue;
}

function profileItemStatus(item) {
  if (item.case_id) {
    const bits = ["已生成素材包"];
    if (item.has_frames) bits.push("关键帧");
    if (item.asr_status && item.asr_status !== "pending") bits.push(`ASR ${item.asr_status}`);
    if (item.ocr_status && item.ocr_status !== "pending") bits.push(`OCR ${item.ocr_status}`);
    return bits.join(" · ");
  }
  if (item.can_build_case === false || item.media_type === "image") {
    return "暂不支持生成视频素材包";
  }
  if (item.media_type === "unknown") {
    return "待解析确认";
  }
  return "可解析";
}

function profileEvidenceBadges(item) {
  const evidence = [
    {id: "case", label: "素材包", ready: Boolean(item.case_id), checked: Boolean(item.case_id)},
    {id: "video", label: "视频", ready: Boolean(item.has_video), checked: Boolean(item.has_video)},
    {id: "frames", label: "关键帧", ready: Boolean(item.has_frames), checked: Boolean(item.has_frames)},
    {
      id: "asr",
      label: "ASR",
      ready: Boolean(item.has_asr),
      checked: Boolean(item.asr_status && item.asr_status !== "pending"),
      status: item.asr_status || "pending",
    },
    {
      id: "ocr",
      label: "OCR",
      ready: Boolean(item.has_ocr),
      checked: Boolean(item.ocr_status && item.ocr_status !== "pending"),
      status: item.ocr_status || "pending",
    },
    {id: "comments", label: "评论", ready: Boolean(item.has_comments), checked: Boolean(item.has_comments)},
    {
      id: "analysis",
      label: "AI",
      ready: item.analysis_status === "success",
      checked: Boolean(item.analysis_status && item.analysis_status !== "not_analyzed" && item.analysis_status !== "pending"),
      status: item.analysis_status || "not_analyzed",
    },
  ];
  return `
    <div class="profile-evidence-badges" aria-label="样本证据完整度">
      ${evidence
        .map((entry) => {
          const state = entry.ready ? "ready" : entry.checked ? "checked" : "missing";
          const title = entry.status ? `${entry.label}: ${entry.status}` : entry.ready ? `${entry.label}: 已具备` : `${entry.label}: 缺失`;
          return `<span class="evidence-chip ${state}" title="${escapeHtml(title)}">${escapeHtml(entry.label)}</span>`;
        })
        .join("")}
    </div>
  `;
}

function profileEvidenceCoverageSummary(items) {
  const rows = normalizeItems(items);
  const counts = rows.reduce(
    (acc, item) => {
      acc.total += 1;
      acc.video += item.has_video ? 1 : 0;
      acc.frames += item.has_frames ? 1 : 0;
      acc.asr += item.has_asr ? 1 : 0;
      acc.ocr += item.has_ocr ? 1 : 0;
      acc.comments += item.has_comments ? 1 : 0;
      acc.full += item.understanding_level === "full" ? 1 : 0;
      acc.partial += item.understanding_level === "partial" ? 1 : 0;
      acc.metadataOnly += !item.understanding_level || item.understanding_level === "metadata_only" ? 1 : 0;
      return acc;
    },
    {total: 0, video: 0, frames: 0, asr: 0, ocr: 0, comments: 0, full: 0, partial: 0, metadataOnly: 0},
  );
  if (!counts.total) {
    return "暂无素材";
  }
  return `完整 ${counts.full} / 部分 ${counts.partial} / 仅元数据 ${counts.metadataOnly}；视频 ${counts.video}，关键帧 ${counts.frames}，ASR ${counts.asr}，OCR ${counts.ocr}，评论 ${counts.comments}`;
}

function renderProfileSummary(summary) {
  if (!summary || !profileSummary) {
    return;
  }
  renderCreatorCloneOverview(summary);
}

function renderProfileDecisionBoard(payload) {
  if (!profileDecisionBoard) {
    return;
  }
  const items = activeCreatorSampleViewItems();
  if (!items.length) {
    profileDecisionBoard.classList.add("hidden");
    profileDecisionBoard.innerHTML = "";
    return;
  }
  const buildable = items.filter(isSampleViewItemBuildable);
  const videoCount = items.filter((item) => item.media_type === "video").length;
  const imageCount = items.filter((item) => item.media_type === "image").length;
  const unknownCount = items.filter((item) => item.media_type === "unknown").length;
  const referenceCount = Math.max(0, items.length - buildable.length);
  const metricCount = items.filter((item) => Number(item.like_count || 0) || Number(item.comment_count || 0) || Number(item.share_count || 0) || Number(item.collect_count || 0)).length;
  const profileMeta = payload?.set?.profile_metadata || payload?.summary?.profile_metadata || {};
  const creatorName = profileMeta.nickname || payload?.set?.creator_name || "当前账号";
  const evidenceText = profileEvidenceCoverageSummary(items);
  const topLike = topCreatorSampleViewItemsBy("like_count", 1)[0];
  const topComment = topCreatorSampleViewItemsBy("comment_count", 1)[0];
  const topShare = topCreatorSampleViewItemsBy("share_count", 1)[0];
  const latest = topCreatorSampleViewItemsBy("create_time", 1)[0];
  const qualityText = metricCount
    ? `${formatNumber(metricCount)}/${formatNumber(items.length)} 条带互动数据，可按点赞、评论、分享、收藏排序。`
    : "互动指标不足，建议改用 JSON / CSV 或本机 Chrome 辅助补充。";
  profileDecisionBoard.classList.remove("hidden");
  profileDecisionBoard.innerHTML = `
    <div class="section-heading-row compact-row">
      <div>
        <div class="entry-label">Decision Board</div>
        <h3>素材池决策概览</h3>
      </div>
      <span class="status-badge muted-badge">${escapeHtml(creatorName)}</span>
    </div>
    <div class="profile-decision-grid">
      <article class="profile-decision-card">
        <span>样本结构</span>
        <strong>${formatNumber(items.length)} 条素材 · ${formatNumber(buildable.length)} 条可富化</strong>
        <p>视频 ${formatNumber(videoCount)} / 图文 ${formatNumber(imageCount)} / 未知 ${formatNumber(unknownCount)} / 参考样本 ${formatNumber(referenceCount)}</p>
      </article>
      <article class="profile-decision-card">
        <span>互动数据</span>
        <strong>${escapeHtml(qualityText)}</strong>
        <p>排序和筛选集中在下一步“选择样本”中完成。</p>
      </article>
      <article class="profile-decision-card">
        <span>证据覆盖</span>
        <strong>${escapeHtml(evidenceText)}</strong>
        <p>富化后会补齐视频、关键帧、ASR、OCR，供大模型蒸馏使用。</p>
      </article>
      <article class="profile-decision-card wide">
        <span>代表样本线索</span>
        <strong>${escapeHtml([
          topLike ? `高赞：${topLike.title || topLike.aweme_id || topLike.sample_id}` : "",
          topComment ? `高评：${topComment.title || topComment.aweme_id || topComment.sample_id}` : "",
          topShare ? `高分享：${topShare.title || topShare.aweme_id || topShare.sample_id}` : "",
          latest ? `最新：${latest.title || latest.aweme_id || latest.sample_id}` : "",
        ].filter(Boolean).join(" / ") || "暂无可排序样本")}</strong>
        <p>下一步进入样本选择，用推荐组合或表头筛选手动确认 N 条代表样本。</p>
      </article>
      <article class="profile-decision-card featured">
        <span>下一步</span>
        <strong>进入样本选择，按表头筛选确认代表样本。</strong>
        <div class="decision-card-actions">
          <button type="button" data-profile-stage-go="select">进入样本选择</button>
        </div>
      </article>
    </div>
  `;
}

function renderProfileSegmentsPreview(segments) {
  if (!profileSegmentsPreview) {
    return;
  }
  const items = activeCreatorSampleViewItems();
  const latestItems = items.length
    ? sortCreatorSampleViewItems(items, "create_time").slice(0, 5).map((item) => ({
        ...item,
        metric_value: item.create_time || "",
      }))
    : [];
  const sectionDefs = [
    ["高赞样本", "like_count", segments?.highest_like_samples, "top_likes"],
    ["高评论样本", "comment_count", segments?.highest_comment_samples, "top_comments"],
    ["高分享样本", "share_count", segments?.highest_share_samples, "top_shares"],
    ["高收藏样本", "collect_count", segments?.highest_collect_samples, "top_collects"],
    ["最新样本", "create_time", latestItems, "latest"],
    ["低表现 / 对照样本", "engagement_score", segments?.weak_or_reference_samples, "low_performance"],
  ];
  const hasAny = sectionDefs.some(([, , items]) => normalizeItems(items).length);
  if (!hasAny) {
    profileSegmentsPreview.classList.add("hidden");
    profileSegmentsPreview.innerHTML = "";
    return;
  }
  profileSegmentsPreview.classList.remove("hidden");
  profileSegmentsPreview.innerHTML = `
    <div class="section-heading-row compact-row">
      <div>
        <div class="entry-label">Performance Segments</div>
        <h3>表现分层预览</h3>
      </div>
      <span class="status-badge muted-badge">蒸馏前参考</span>
    </div>
    <div class="profile-segment-grid">
      ${sectionDefs
        .map(([title, metricKey, items, preset]) => renderProfileSegmentColumn(title, metricKey, items, preset))
        .join("")}
    </div>
  `;
}

function renderProfileSegmentColumn(title, metricKey, items, preset) {
  const rows = normalizeItems(items).slice(0, 3);
  const metricLabel = {
    like_count: "赞",
    comment_count: "评",
    share_count: "分享",
    collect_count: "收藏",
    engagement_score: "综合",
    create_time: "时间",
  }[metricKey] || "指标";
  return `
    <article class="profile-segment-column">
      <div class="profile-segment-column-head">
        <strong>${escapeHtml(title)}</strong>
      </div>
      ${
        rows.length
          ? `<ol>${rows
              .map((item) => {
                const value = item.metric_value ?? item[metricKey] ?? 0;
                return `<li><span>${escapeHtml(item.title || item.aweme_id || item.sample_id || "未命名样本")}</span><em>${escapeHtml(metricLabel)} ${formatNumber(value)}</em></li>`;
              })
              .join("")}</ol>`
          : `<p class="muted compact-copy">暂无可用数据。</p>`
      }
    </article>
  `;
}

function renderProfileResults(payload) {
  profileScanPayload = payload;
  currentCreatorRuntimeReport = null;
  currentDistillPrompt = "";
  currentCreatorIntelligenceStrategy = null;
  applyCreatorIntelligencePayload(payload);
  creatorCloneResultCard?.classList.add("hidden");
  const cloneSet = payload.set || null;
  currentCloneSetId = cloneSet?.set_id || "";
  if (profileContentProfile && cloneSet?.content_profile) {
    profileContentProfile.value = cloneSet.content_profile;
  }
  currentCloneProfileFingerprint = profileFingerprintFromPayload(payload);
  if (currentCloneSetId) {
    rememberRecentCreatorCloneSetId(currentCloneSetId);
  }
  runtimeSampleRows = normalizeItems(payload.items || cloneSet?.samples);
  const persistedSelected = normalizeItems(cloneSet?.selected_sample_ids);
  profileSelectedKeys = persistedSelected.length
    ? new Set(persistedSelected)
    : new Set([...profileSelectedKeys].filter((key) => runtimeSampleRows.some((item) => sampleViewItemKey(item) === key)));
  profileResultsCard.classList.remove("hidden");
  profileQueueCard.classList.add("hidden");
  profileProviderBadge.textContent = cloneSet ? "creator clone lab" : (payload.provider || "profile");
  const warnings = normalizeItems(payload.warnings || cloneSet?.warnings);
  profileWarnings.classList.toggle("hidden", !warnings.length);
  profileWarnings.textContent = warnings.join(" ");
  renderProfileCaptureAudit(payload.capture_audit || cloneSet?.capture_audit || null);
  renderProfileSummary(payload.summary || cloneSummaryFromSet(cloneSet) || {});
  renderProfileDecisionBoard(payload);
  renderProfileSegmentsPreview(payload.performance_segments || cloneSet?.performance_segments || null);
  renderProfileTable();
  updateCreatorCloneSelectionStatus();
  updateProfileChromeContinueButton();
  if (profileStageView === "import") {
    setProfileStageView("pool");
  } else {
    renderProfileStageView();
  }
  const restoredStrategy = payload.creator_intelligence?.strategy_output || null;
  const workflowState = payload.creator_intelligence?.workflow?.state || "";
  if (restoredStrategy && workflowState === "DONE") {
    renderCreatorCloneResult(
      creatorCloneResultFromStrategyOutput(restoredStrategy),
      cloneSet,
      currentDistillPrompt,
      payload.exports || {},
      {scroll: false},
    );
  }
  clearCreatorCloneUnifiedInput();
}

function renderProfileCaptureAudit(audit) {
  if (!profileCaptureAudit) {
    return;
  }
  if (!audit || typeof audit !== "object" || !audit.capture_method) {
    profileCaptureAudit.classList.add("hidden");
    profileCaptureAudit.innerHTML = "";
    return;
  }
  const safety = audit.safety || {};
  const contract = audit.security_contract || {};
  const authorization = audit.authorization || {};
  const mediaSummary = audit.media_summary || {};
  const fieldCoverage = audit.field_coverage || {};
  const fieldTotal = Number(fieldCoverage.total || audit.final_sample_count || audit.captured_count || 0);
  const safetyItems = [
    ["本机访问", safety.loopback_only],
    ["一次性 token", safety.one_time_token_required],
    ["页面确认", safety.page_confirmation_required],
    ["未读取 Cookie", safety.cookie_read === false],
    ["未返回 Cookie", safety.cookie_returned === false],
    ["未写 Cookie 日志", safety.cookie_logged === false],
    ["只读 DOM 元数据", safety.dom_visible_metadata_only],
    ["敏感字段过滤", safety.sensitive_fields_redacted],
  ];
  const contractItems = [
    ["请求来源", contract.requests_from_user_machine ? "用户本机 Chrome / 本机 IP" : "未知"],
    ["公开站接收", contract.public_site_cookie_free ? "仅净化元数据" : "需复核"],
    ["Cookie", contract.cookie_read === false && contract.cookie_returned === false && contract.cookie_logged === false ? "不读 / 不传 / 不记" : "需复核"],
    ["签名媒体 URL", contract.signed_media_url_returned === false ? "不返回" : "需复核"],
  ];
  const authorizationItems = [
    ["页面确认", authorization.page_confirmed === true ? "已确认" : "未记录"],
    ["一次性 token", authorization.one_time_token_consumed === true ? "已消费" : "未记录"],
    ["触发来源", authorization.trigger || "unknown"],
  ];
  const returnedScope = normalizeItems(contract.returned_data_scope)
    .map((item) => String(item))
    .filter(Boolean);
  const coverageItems = [
    ["标题", fieldCoverage.with_title],
    ["来源链接", fieldCoverage.with_source_url],
    ["封面", fieldCoverage.with_cover_url],
    ["作者", fieldCoverage.with_author],
    ["发布时间", fieldCoverage.with_create_time],
    ["标签", fieldCoverage.with_tags],
    ["互动指标", fieldCoverage.with_any_visible_metric],
  ];
  const boundaryOk = safetyItems.every(([, ok]) => Boolean(ok))
    && contract.public_site_cookie_free === true
    && contract.requests_from_user_machine === true
    && contract.cookie_read === false
    && contract.cookie_returned === false
    && contract.cookie_logged === false
    && contract.signed_media_url_returned === false;
  const nextStep = Number(mediaSummary.buildable_item_count || 0) > 0
    ? "下一步：按点赞、评论、时间等维度选择代表视频，点击主按钮开始富化证据。"
    : "下一步：当前多为图文/元数据参考，可直接选样蒸馏，或继续采集更多可富化视频。";
  profileCaptureAudit.classList.remove("hidden");
  profileCaptureAudit.innerHTML = `
    <div class="capture-audit-heading">
      <strong>最近采集审计</strong>
      <span>${escapeHtml(audit.capture_method || "unknown")}</span>
    </div>
    <div class="capture-audit-verdict ${boundaryOk ? "safe" : "warning"}">
      <strong>${boundaryOk ? "本机辅助采集边界通过" : "本机辅助采集边界需复核"}</strong>
      <p>${boundaryOk ? "请求由用户本机 Chrome / 本机 IP 发起；页面只接收净化后的作品列表和元数据，不接收 Cookie、登录 token、签名媒体 URL 或原始请求头。" : "请先复核安全契约：本轮采集必须只返回可见作品元数据，且不读取、不上传、不记录 Cookie。"}</p>
      <p>${escapeHtml(nextStep)}</p>
    </div>
    <dl class="capture-audit-metrics">
      <dt>采集时间</dt><dd>${escapeHtml(audit.captured_at || "未知")}</dd>
      <dt>滚动轮数</dt><dd>${formatNumber(audit.scroll_count)}</dd>
      <dt>采集样本</dt><dd>${formatNumber(audit.captured_count)}</dd>
      <dt>当前素材池</dt><dd>${formatNumber(audit.final_sample_count)}</dd>
      <dt>合并采集</dt><dd>${audit.merged_into_existing_set ? "是" : "否"}</dd>
      <dt>可富化素材</dt><dd>${formatNumber(mediaSummary.buildable_item_count)}</dd>
      <dt>图文/照片</dt><dd>${formatNumber(mediaSummary.image_count)}</dd>
      <dt>仅元数据</dt><dd>${formatNumber(mediaSummary.metadata_only_count)}</dd>
    </dl>
    <div class="capture-field-coverage" aria-label="字段覆盖率">
      <strong>字段覆盖</strong>
      <div class="capture-field-grid">
        ${coverageItems
          .map(([label, value]) => {
            const count = Number(value || 0);
            const ratio = fieldTotal ? Math.round((count / fieldTotal) * 100) : 0;
            return `<span title="${escapeHtml(label)}覆盖 ${formatNumber(count)}/${formatNumber(fieldTotal)}">${escapeHtml(label)} ${formatNumber(count)}/${formatNumber(fieldTotal)} · ${formatNumber(ratio)}%</span>`;
          })
          .join("")}
      </div>
    </div>
    <div class="capture-audit-safety">
      ${safetyItems
        .map(([label, ok]) => `<span class="${ok ? "ok" : "warn"}">${escapeHtml(label)}：${ok ? "是" : "否"}</span>`)
        .join("")}
    </div>
    <div class="security-contract-card">
      <strong>安全契约</strong>
      <dl>
        ${contractItems.map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`).join("")}
      </dl>
      <p>回传范围：${escapeHtml(returnedScope.join(" / ") || "账号可见元数据 / 可见作品列表 / 可见互动指标 / 净化作品链接")}</p>
    </div>
    <div class="security-contract-card">
      <strong>本次授权</strong>
      <dl>
        ${authorizationItems.map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd>`).join("")}
      </dl>
      <p>只有页面按钮触发并消费一次性 token 后，才会执行真正的本机 Chrome 作品列表读取。</p>
    </div>
    <div class="handoff-manifest-callout">
      <strong>安全交接包</strong>
      <p>已准备 handoff_manifest.json：只包含账号素材清单、可见互动指标和安全审计；公开网站只接收净化后的元数据，不接收 Cookie、登录 token、签名 URL 或原始请求头。</p>
      ${
        currentCloneSetId
          ? `<a class="button-link" href="/api/creator-clone/sets/${encodeURIComponent(currentCloneSetId)}/files/handoff_manifest.json" target="_blank" rel="noreferrer">下载 handoff_manifest.json</a>`
          : ""
      }
    </div>
    <p class="muted compact-copy">该审计只记录采集方式、安全边界、滚动轮数和样本数，不包含 Cookie、签名 URL 或登录 token。</p>
  `;
}

function cloneSummaryFromSet(set) {
  if (!set) {
    return null;
  }
  const samples = normalizeItems(set.samples);
  return {
    scanned_count: set.sample_count || samples.length,
    video_count: samples.filter((item) => item.media_type === "video").length,
    max_engagement_score: Math.max(0, ...samples.map((item) => Number(item.engagement_score || 0))),
    avg_like_count: averageMetric(samples, "like_count"),
    avg_comment_count: averageMetric(samples, "comment_count"),
    avg_share_count: averageMetric(samples, "share_count"),
    top_items: sortCreatorSampleViewItems(samples, "engagement_score").slice(0, 3),
    profile_metadata: set.profile_metadata || {},
    content_keywords: [],
  };
}

function averageMetric(items, key) {
  const values = normalizeItems(items).map((item) => Number(item[key] || 0));
  if (!values.length) {
    return 0;
  }
  return Math.round(values.reduce((sum, value) => sum + value, 0) / values.length);
}

function isProfileFallbackError(error) {
  return ["DOUYIN_RISK_CONTROL", "PROFILE_SCAN_NEEDS_FALLBACK", "PROFILE_SCAN_FAILED"].includes(error?.error_code);
}

function showProfileFallback(error, options = {}) {
  const chromeFirst = Boolean(options.chromeFirst);
  profileFallbackHint.classList.remove("hidden");
  profileFallbackHint.innerHTML = `
    <strong>${chromeFirst ? "公开扫描受限，准备切换到本机 Chrome 辅助采集。" : "已切换到稳定兜底方式：多作品链接粘贴。"}</strong>
    <p>${chromeFirst ? "当前公开主页没有返回可解析作品列表，系统会引导你使用本机已打开的抖音主页做只读采集；如果 Chrome 辅助仍不可用，再使用多作品链接粘贴兜底。" : "主页被平台限制，当前不登录、不使用 Cookie、不绕风控，因此无法直接读取作品列表。建议复制多条作品链接到下方输入框，系统会整理成账号作品池。"}</p>
    <p class="muted compact-copy">调试信息：${escapeHtml(error.error_code || "PROFILE_SCAN_FAILED")}：${escapeHtml(error.message || "主页扫描失败")}</p>
  `;
  if (!chromeFirst) {
    profileManualSection.open = true;
    profileManualLinks.focus();
  }
}

async function prepareChromeProfileFallback(error) {
  showProfileFallback(error, {chromeFirst: true});
  if (profilePublicSection) {
    profilePublicSection.open = true;
  }
  if (profileChromeConfirm) {
    profileChromeConfirm.checked = false;
  }
  profileScanStatus.textContent = `${error.error_code || "PROFILE_SCAN_FAILED"}：公开扫描受限。请确认本机 Chrome 辅助采集边界后，点击“本机 Chrome 辅助入口”。`;
  try {
    await loadChromeHelperStatus({silent: true});
  } catch (statusError) {
    profileScanStatus.textContent = `${error.error_code || "PROFILE_SCAN_FAILED"}：公开扫描受限。请在本机 Chrome 打开目标抖音主页，完成登录/验证后再点击“本机 Chrome 辅助入口”。`;
  }
}

function chromeHelperNextAction(status) {
  if (status.ready_for_profile_scan) {
    return "下一步：点击“本机 Chrome 辅助入口”。页面会先申请一次性 token，再由你确认后读取当前主页可见作品。";
  }
  if (!status.chrome_available) {
    return "下一步：在本机 Chrome 打开目标抖音主页；如果本地助手需要调试 Chrome，请按设置预检中的提示启动。";
  }
  if (Number(status.douyin_profile_tab_count || 0) <= 0) {
    return "下一步：在已登录的本机 Chrome 中打开目标主页，页面加载完成后回到这里点击“本机 Chrome 辅助入口”。";
  }
  return "下一步：确认目标主页已经加载完成，然后点击“本机 Chrome 辅助入口”。";
}

function renderChromeHelperStatus(status) {
  if (!profileChromeStatus) {
    return;
  }
  const tabs = normalizeItems(status.douyin_tabs);
  const tabText = tabs.length
    ? `检测到 ${tabs.length} 个抖音标签页：${tabs.map((tab, index) => tab.label || (tab.is_profile ? `抖音主页 #${index + 1}` : `抖音标签页 #${index + 1}`)).slice(0, 2).join(" / ")}`
    : "未检测到抖音标签页";
  const launchHint = status.launch_hint ? ` 启动命令：${status.launch_hint}` : "";
  profileChromeAvailable = Boolean(status.chrome_available);
  profileChromeLaunchCommand = status.launch_hint || "";
  profileChromeStatus.classList.toggle("ready", Boolean(status.ready_for_profile_scan));
  profileChromeStatus.classList.toggle("blocked", !status.ready_for_profile_scan);
  const securityItems = normalizeItems(status.security).slice(0, 4);
  const dataScope = normalizeItems(status.returned_data_scope).map((item) => item.replaceAll("_", " ")).join(" / ");
  const requestOrigin = status.request_origin === "user_local_chrome_and_user_local_ip"
    ? "用户本机 Chrome / 本机 IP"
    : String(status.request_origin || "本机");
  const readinessLabel = status.ready_for_profile_scan ? "可扫描" : "未就绪";
  profileChromeStatus.innerHTML = `
    <strong>本机 Chrome 辅助状态：<span class="helper-readiness ${status.ready_for_profile_scan ? "ready" : "blocked"}">${readinessLabel}</span></strong>
    <p>${escapeHtml(status.status_message || "状态未知。")}</p>
    ${status.profile_note ? `<p>${escapeHtml(status.profile_note)}</p>` : ""}
    <span>${escapeHtml(tabText)}。</span>
    <p>${escapeHtml(status.next_action || chromeHelperNextAction(status))}</p>
    <p>请求来源：${escapeHtml(requestOrigin)}；返回范围：${escapeHtml(dataScope || "账号资料和作品元数据")}。</p>
    ${launchHint ? `<code>${escapeHtml(launchHint)}</code>` : ""}
    ${securityItems.length ? `<ul>${securityItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
  `;
}

async function loadChromeHelperStatus({silent = false} = {}) {
  if (profileChromeStatus && !silent) {
    profileChromeStatus.textContent = "本机 Chrome 辅助状态：正在检测...";
  }
  const response = await fetch("/api/local-helper/chrome/status", {cache: "no-store"});
  const payload = await readJsonResponse(response);
  renderChromeHelperStatus(payload);
  return payload;
}

async function requestChromeScanToken() {
  const tokenResponse = await fetch("/api/local-helper/chrome/scan-token", {method: "POST"});
  return readJsonResponse(tokenResponse);
}

function requireProfileChromeConfirmation() {
  if (!profileChromeConfirm || profileChromeConfirm.checked) {
    return true;
  }
  const advanced = profileChromeConfirm.closest("details");
  if (advanced) {
    advanced.open = true;
  }
  profileScanStatus.textContent = "请先勾选本次辅助采集确认：请求由本机 Chrome / 本机 IP 发起，只读取页面可见作品列表和元数据，不读取 Cookie。";
  return false;
}

function resetProfileChromeConfirmation() {
  if (profileChromeConfirm) {
    profileChromeConfirm.checked = false;
  }
}

function localChromeConfirmationPayload(extra = {}) {
  return {
    ...extra,
    page_confirmed: Boolean(profileChromeConfirm?.checked),
  };
}

async function openProfileInLocalChrome(profileValue) {
  const tokenPayload = await requestChromeScanToken();
  const response = await fetch("/api/local-helper/chrome/open-profile", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(localChromeConfirmationPayload({profile_url: profileValue, token: tokenPayload.token})),
  });
  return readJsonResponse(response);
}

async function launchLocalChrome(profileValue = "") {
  const tokenPayload = await requestChromeScanToken();
  const response = await fetch("/api/local-helper/chrome/launch", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(localChromeConfirmationPayload({profile_url: profileValue, token: tokenPayload.token})),
  });
  return readJsonResponse(response);
}

async function copyTextToClipboard(value) {
  if (!value) {
    return false;
  }
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return true;
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "readonly");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  return copied;
}

function currentProfileTargetValue() {
  const formData = new FormData(profileForm);
  const rawProfileValue = String(formData.get("profile_url") || "").trim();
  return firstUrlFromText(rawProfileValue) || rawProfileValue || profileLastChromeProfileValue;
}

// Creator Clone: sample table
function renderProfileTable() {
  renderCompactProfileTable();
}

function renderCompactProfileTable() {
  const sorted = visibleCreatorSampleViewItems();
  if (!sorted.length) {
    profileResultsBody.innerHTML = '<tr><td colspan="7" class="muted">当前筛选下没有素材。可以切换证据筛选，或改用粘贴作品链接、JSON / CSV、已有 Case 导入。</td></tr>';
    return;
  }
  const groupOrder = profileMediaFilter?.value === "all" ? ["video", "image", "unknown"] : [profileMediaFilter?.value || "all"];
  const groups = groupOrder
    .map((type) => {
      const rows = sorted.filter((item) => {
        const mediaType = item.media_type || "unknown";
        return type === "unknown" ? !["video", "image"].includes(mediaType) : mediaType === type;
      });
      return {type, rows};
    })
    .filter((group) => group.rows.length);
  profileResultsBody.innerHTML = groups
    .map((group) => {
      const label = {video: "视频素材", image: "图文/照片素材", unknown: "未知类型素材"}[group.type] || "素材";
      return `
        <tr class="profile-group-row"><td colspan="7">${escapeHtml(label)} · ${formatNumber(group.rows.length)} 条</td></tr>
        ${group.rows.map(renderProfileTableRow).join("")}
      `;
    })
    .join("");
  installProfileCoverFallbacks();
}

function profileCoverMarkup(item) {
  const title = item.title || item.desc || item.aweme_id || item.sample_id || "素材";
  if (!item.cover_url) {
    return profileCoverFallbackMarkup(item, "无封面");
  }
  return `<img src="${escapeHtml(item.cover_url)}" alt="${escapeHtml(title)}" class="profile-cover" loading="lazy" referrerpolicy="no-referrer" data-profile-cover-url="${escapeHtml(item.cover_url)}" data-profile-cover-fallback="${escapeHtml(profileCoverFallbackLabel(item))}">`;
}

function profileCoverFallbackLabel(item) {
  const type = item.media_type || "unknown";
  return type === "video" ? "视频" : type === "image" ? "图文" : "无封面";
}

function profileCoverFallbackMarkup(item, label = "") {
  const coverUrl = item.cover_url || "";
  const text = label || profileCoverFallbackLabel(item);
  if (coverUrl) {
    return `<div class="profile-cover placeholder"><span>封面受限</span><small>${escapeHtml(text)}</small></div>`;
  }
  return `<div class="profile-cover placeholder"><span>${escapeHtml(text)}</span></div>`;
}

function installProfileCoverFallbacks() {
  profileResultsBody.querySelectorAll("img.profile-cover").forEach((image) => {
    image.addEventListener("error", () => {
      const label = image.dataset.profileCoverFallback || "无封面";
      const coverUrl = image.dataset.profileCoverUrl || "";
      if (coverUrl) {
        const fallback = document.createElement("div");
        fallback.className = "profile-cover placeholder";
        fallback.innerHTML = `<span>封面受限</span><small>${escapeHtml(label)}</small>`;
        image.replaceWith(fallback);
        return;
      }
      const fallback = document.createElement("div");
      fallback.className = "profile-cover placeholder";
      fallback.innerHTML = `<span>${escapeHtml(label)}</span>`;
      image.replaceWith(fallback);
    }, {once: true});
  });
}

function renderProfileTableRow(item) {
  const typeLabel = {video: "视频", image: "图文/照片", unknown: "未知"}[item.media_type] || "未知";
  const status = profileItemStatus(item);
  const level = item.understanding_level || "metadata_only";
  const levelLabel = {full: "完整", partial: "部分", metadata_only: "仅元数据"}[level] || "仅元数据";
  const evidenceBadges = profileEvidenceBadges(item);
  const key = sampleViewItemKey(item);
  const checked = profileSelectedKeys.has(key) ? " checked" : "";
  const awemeLabel = item.aweme_id || item.case_id || item.sample_id || "无";
  const titleText = item.title || item.desc || awemeLabel;
  const secondaryText = [item.desc, item.source_url || item.webpage_url]
    .map((value) => String(value || "").trim())
    .find((value) => value && value !== titleText) || "";
  const sourceHref = item.source_url || item.webpage_url || (item.aweme_id ? `https://www.douyin.com/video/${item.aweme_id}` : "");
  const sourceLink = sourceHref
    ? `<a class="text-link profile-source-link" href="${escapeHtml(sourceHref)}" target="_blank" rel="noreferrer">来源</a>`
    : "";
  const caseLink = item.case_id
    ? `<a class="text-link profile-source-link" href="/cases/${escapeHtml(item.case_id)}" target="_blank" rel="noreferrer">打开 Case</a>`
    : "";
  const primaryAction = item.case_id
    ? caseLink
    : isSampleViewItemBuildable(item)
      ? `<button type="button" class="text-button" data-profile-select-action="${escapeHtml(key)}">选入富化</button>`
      : sourceLink || `<span class="muted">仅参考</span>`;
  const metricLines = [
    `赞 ${formatNumber(item.like_count)}`,
    `评 ${formatNumber(item.comment_count)}`,
    `分享 ${formatNumber(item.share_count)}`,
    `收藏 ${formatNumber(item.collect_count)}`,
    `综合 ${formatNumber(item.engagement_score)}`,
  ];
  return `
    <tr>
      <td><input type="checkbox" data-profile-select value="${escapeHtml(key)}"${checked}></td>
      <td>
        <div class="profile-material-cell">
          ${profileCoverMarkup(item)}
          <div>
            <strong>${escapeHtml(titleText)}</strong>
            ${secondaryText ? `<p>${escapeHtml(secondaryText)}</p>` : ""}
            <code>${escapeHtml(awemeLabel)}</code>
          </div>
        </div>
      </td>
      <td><span class="profile-media-type ${escapeHtml(item.media_type || "unknown")}">${escapeHtml(typeLabel)}</span></td>
      <td>
        <div class="profile-metric-stack">${metricLines.map((line) => `<span>${escapeHtml(line)}</span>`).join("")}</div>
      </td>
      <td><span class="profile-item-status ${escapeHtml(level)}">${escapeHtml(levelLabel)}</span>${evidenceBadges}</td>
      <td><span class="profile-item-status ${escapeHtml(item.media_type || "unknown")}">${escapeHtml(status)}</span></td>
      <td><div class="profile-row-actions">${primaryAction}${caseLink && sourceLink ? sourceLink : ""}</div></td>
    </tr>
  `;
}

function profileScanMaxPagesForCount(count) {
  const target = Number(count || 20);
  return Math.max(1, Math.min(20, Math.ceil(target / 10)));
}

async function scanProfile(sourceMode = "public") {
  let activeSource = "public";
  profileScanButton.disabled = true;
  profileScanStatus.textContent = "正在扫描主页并生成账号素材清单...";
  profileResultsCard.classList.add("hidden");
  profileFallbackHint.classList.add("hidden");
  profileLastChromeProfileValue = "";
  updateProfileChromeContinueButton();
  try {
    const formData = new FormData(profileForm);
    const rawProfileValue = String(formData.get("profile_url") || "").trim();
    const profileValue = firstUrlFromText(rawProfileValue) || rawProfileValue;
    const isUrl = /^https?:\/\//i.test(profileValue);
    activeSource = ["public", "manual", "structured", "handoff", "case"].includes(sourceMode) ? sourceMode : "public";
    if (activeSource === "public" && resetCreatorClonePoolIfProfileChanged(profileValue)) {
      profileScanStatus.textContent = "检测到新的主页链接，已清空上一次素材池，正在重新扫描...";
    }
    const requestedCount = Number(formData.get("count") || 20);
    const requestedMaxPages = activeSource === "public" ? profileScanMaxPagesForCount(requestedCount) : 1;
    const profilePayload = {
      profile_url: activeSource === "public" && isUrl ? profileValue : "",
      sec_user_id: activeSource === "public" && !isUrl ? profileValue : "",
      manual_links: activeSource === "manual" ? String(formData.get("manual_links") || "") : "",
      structured_items: activeSource === "structured" ? String(formData.get("structured_items") || "") : "",
      count: requestedCount,
      max_pages: requestedMaxPages,
      sort_by: String(profileSort?.value || "like_count"),
    };
    const clonePayload = {
      title: "创作者蒸馏素材池",
      source_platform: "douyin",
      profile_url: profilePayload.profile_url,
      sec_user_id: profilePayload.sec_user_id,
      manual_links: profilePayload.manual_links,
      structured_items: profilePayload.structured_items,
      case_ids: activeSource === "case" ? String(formData.get("case_ids") || "") : "",
      count: profilePayload.count,
      max_pages: profilePayload.max_pages,
      sort_by: profilePayload.sort_by,
    };
    let endpoint = "/api/creator-clone/import";
    let requestBody = clonePayload;
    if (activeSource === "handoff") {
      const rawHandoff = String(formData.get("handoff_manifest") || "").trim();
      if (!rawHandoff) {
        throw {error_code: "HANDOFF_MANIFEST_INVALID", message: "请先粘贴 handoff_manifest.json。"};
      }
      try {
        const tokenResponse = await fetch("/api/creator-clone/handoff-token", {method: "POST"});
        const tokenPayload = await readJsonResponse(tokenResponse);
        requestBody = {handoff_manifest: JSON.parse(rawHandoff), handoff_token: tokenPayload.token};
      } catch (error) {
        if (error?.error_code) {
          throw error;
        }
        throw {error_code: "HANDOFF_MANIFEST_INVALID", message: "handoff_manifest.json 不是合法 JSON。"};
      }
      endpoint = "/api/creator-clone/import-handoff";
    }
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(requestBody),
    });
    const result = await readJsonResponse(response);
    const stats = result.import_stats || {};
    const itemCount = result.items?.length || result.set?.sample_count || 0;
    const statsText = stats.input_count
      ? ` 成功识别 ${stats.recognized_count || 0} 条，去重 ${stats.duplicate_count || 0} 条，忽略 ${stats.invalid_count || 0} 条。`
      : "";
    profileScanStatus.textContent = `账号素材清单已生成：${itemCount} 条素材。${statsText}`;
    renderProfileResults(result);
  } catch (error) {
    if (activeSource === "public" && isProfileFallbackError(error)) {
      await prepareChromeProfileFallback(error);
    } else {
      profileScanStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "导入失败，请改用多作品链接粘贴、JSON / CSV 或已有 Case。"}`;
      if (isProfileFallbackError(error)) {
        showProfileFallback(error);
      }
    }
  } finally {
    profileScanButton.disabled = false;
    renderCreatorCloneNextAction();
  }
}

async function scanProfileWithLocalChrome(options = {}) {
  const profileValue = currentProfileTargetValue();
  const profileChanged = resetCreatorClonePoolIfProfileChanged(profileValue);
  const continueScan = Boolean(options.continueScan) && !profileChanged && Boolean(currentCloneSetId);
  if (!profileValue) {
    profileScanStatus.textContent = "请先填写主页 URL / sec_user_id，并在 Chrome 中打开该主页。";
    return;
  }
  if (!requireProfileChromeConfirmation()) {
    return;
  }
  let status;
  try {
    status = await loadChromeHelperStatus();
  } catch (error) {
    profileScanStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "无法检测本机 Chrome 辅助状态"}`;
    return;
  }
  if (!status.ready_for_profile_scan) {
    if (status.chrome_available && !continueScan) {
      const profileModeHint = status.profile_mode === "dedicated"
        ? "当前连接的是项目专用调试 Chrome，不是你的日常 Chrome；日常 Chrome 里已经打开的抖音主页不会被识别。"
        : "当前连接的是已配置的本机调试 Chrome。";
      const shouldOpen = window.confirm(
        `${profileModeHint} 是否先在这个调试 Chrome 中打开目标主页？这个动作只打开页面，不读取 Cookie，不上传 Cookie；页面加载并完成登录/验证后，再点击“本机 Chrome 辅助采集”执行扫描。`,
      );
      if (!shouldOpen) {
        profileScanStatus.textContent = status.profile_mode === "dedicated"
          ? "已连接专用调试 Chrome，但没有找到抖音主页标签页。请在该调试 Chrome 中打开目标主页，或在 .env 中切换 existing 模式。"
          : "已连接 Chrome，但没有找到抖音主页标签页。你可以先打开目标主页，再重新点击本机 Chrome 辅助采集。";
        return;
      }
      profileBrowserHelperButton.disabled = true;
      profileScanStatus.textContent = "正在本机调试 Chrome 中打开主页...";
      try {
        await openProfileInLocalChrome(profileValue);
        profileLastChromeProfileValue = profileValue;
        profileScanStatus.textContent = "已打开目标主页。请等待页面加载并完成登录/验证后，再点击“本机 Chrome 辅助采集”开始扫描。";
        window.setTimeout(() => {
          loadChromeHelperStatus({silent: true}).catch(() => {});
        }, 900);
      } catch (error) {
        profileScanStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "无法在调试 Chrome 中打开主页"}`;
      } finally {
        profileBrowserHelperButton.disabled = false;
        resetProfileChromeConfirmation();
      }
      return;
    }
    if (!status.chrome_available && profileChromeLaunchCommand) {
      try {
        await launchLocalChrome(profileValue);
        profileLastChromeProfileValue = profileValue;
        profileScanStatus.textContent = "未检测到 Chrome DevTools，已尝试启动调试 Chrome。请等待页面加载并完成登录/验证后，再点击“本机 Chrome 辅助采集”。";
        window.setTimeout(() => {
          loadChromeHelperStatus({silent: true}).catch(() => {});
        }, 1200);
      } catch (error) {
        try {
          await copyTextToClipboard(profileChromeLaunchCommand);
          profileScanStatus.textContent = "未检测到 Chrome DevTools，自动启动失败，已尝试复制启动命令。请关闭普通 Chrome 后用该命令启动，再打开目标主页。";
        } catch (copyError) {
          profileScanStatus.textContent = "未检测到 Chrome DevTools。请复制状态区里的启动命令，用 remote debugging 模式启动 Chrome。";
        }
      }
      resetProfileChromeConfirmation();
      return;
    }
    profileScanStatus.textContent = status.chrome_available
      ? "已连接 Chrome，但没有找到抖音主页标签页。请先打开目标主页。"
      : "未检测到 Chrome DevTools。请按页面提示用 remote debugging 模式启动 Chrome。";
    resetProfileChromeConfirmation();
    return;
  }
  const confirmed = window.confirm(
    continueScan
      ? "将继续使用本机 Chrome 在当前抖音主页做更多受控滚动，把新出现的作品去重合并进当前素材池。请求由你的本机发起，不读取 Cookie，不上传 Cookie。确认继续？"
      : "将使用本机 Chrome 辅助采集当前已打开的抖音主页，并在该标签页内进行几轮受控滚动以读取更多可见作品。请求由你的本机发起，不读取 Cookie，不上传 Cookie，只返回页面可见作品列表和元数据。确认继续？",
  );
  if (!confirmed) {
    resetProfileChromeConfirmation();
    return;
  }
  profileBrowserHelperButton.disabled = true;
  if (profileContinueChromeButton) {
    profileContinueChromeButton.disabled = true;
  }
  profileScanStatus.textContent = continueScan ? "正在继续采集更多可见作品..." : "正在连接本机 Chrome DevTools...";
  if (!continueScan) {
    profileResultsCard.classList.add("hidden");
  }
  profileFallbackHint.classList.add("hidden");
  try {
    const tokenPayload = await requestChromeScanToken();
    const scanResponse = await fetch("/api/local-helper/chrome/scan-profile", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(localChromeConfirmationPayload({
        profile_url: profileValue,
        token: tokenPayload.token,
        max_items: continueScan ? 200 : 100,
        scroll_rounds: continueScan ? 12 : 6,
        sample_set_id: continueScan ? currentCloneSetId : "",
      })),
    });
    const result = await readJsonResponse(scanResponse);
    profileLastChromeProfileValue = profileValue;
    profileScanStatus.textContent = continueScan
      ? `继续采集完成：当前素材池 ${result.set?.sample_count || 0} 条。`
      : `本机 Chrome 辅助采集完成：${result.set?.sample_count || 0} 条素材。`;
    renderProfileResults(result);
  } catch (error) {
    if (!continueScan && error.error_code === "LOCAL_CHROME_TAB_NOT_FOUND") {
      try {
        profileScanStatus.textContent = "当前调试 Chrome 中没有找到你输入的目标主页，正在打开新主页...";
        await openProfileInLocalChrome(profileValue);
        profileLastChromeProfileValue = profileValue;
        profileScanStatus.textContent = "已在调试 Chrome 中打开你输入的目标主页。请等待页面加载完成并确认账号正确后，再点击“本机 Chrome 辅助采集”。";
        window.setTimeout(() => {
          loadChromeHelperStatus({silent: true}).catch(() => {});
        }, 900);
      } catch (openError) {
        profileScanStatus.textContent = `${openError.error_code || "ERROR"}：${openError.message || "无法在调试 Chrome 中打开目标主页"}`;
      }
      return;
    }
    profileScanStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "本机 Chrome 辅助采集失败"}`;
  } finally {
    profileBrowserHelperButton.disabled = false;
    resetProfileChromeConfirmation();
    updateProfileChromeContinueButton();
    renderCreatorCloneNextAction();
  }
}

async function readHandoffManifestFile(file) {
  if (!file || !profileHandoffManifest) {
    return;
  }
  if (file.size > HANDOFF_MANIFEST_MAX_BYTES) {
    if (profileHandoffFile) {
      profileHandoffFile.value = "";
    }
    profileScanStatus.textContent = "HANDOFF_MANIFEST_INVALID：handoff_manifest.json 文件过大，请确认这是本机助手导出的安全交接包。";
    return;
  }
  try {
    const text = await file.text();
    JSON.parse(text);
    profileHandoffManifest.value = text;
    profileScanStatus.textContent = `已读取 ${file.name || "handoff_manifest.json"}，可点击“导入交接包”。`;
  } catch (error) {
    profileScanStatus.textContent = "HANDOFF_MANIFEST_INVALID：handoff_manifest.json 不是合法 JSON。";
  }
}

async function runCreatorCloneImportStep() {
  const mode = inferCreatorCloneImportMode();
  if (!hasCreatorCloneImportInput()) {
    profileScanStatus.textContent = "请先输入主页 URL、作品链接、aweme_id，或展开“换一种导入方式”导入 JSON / CSV / Case。";
    profileQuickInput?.focus();
    return;
  }
  syncUnifiedInputToImportFields(mode);
  setActiveImportMode(mode);
  if (mode === "browser") {
    let status = null;
    try {
      status = await loadChromeHelperStatus({silent: true});
    } catch (error) {
      status = null;
    }
    if (status?.ready_for_profile_scan) {
      await scanProfileWithLocalChrome();
      return;
    }
    await scanProfile("public");
    if (!activeCreatorSampleViewItems().length) {
      setActiveImportMode("manual");
      profileManualLinks?.focus();
      profileScanStatus.textContent = profileScanStatus.textContent || "主页导入未得到素材，已切换到作品链接粘贴方式。";
    }
    return;
  }
  const sourceMode = {manual: "manual", structured: "structured", case: "case", handoff: "handoff"}[mode] || "manual";
  await scanProfile(sourceMode);
}

async function syncCreatorCloneWorkflowSelection() {
  if (!currentCloneSetId) {
    return null;
  }
  const selectedIds = selectedCreatorSampleViewItems().map(sampleViewItemKey).filter(Boolean);
  if (!selectedIds.length) {
    return null;
  }
  return dispatchCreatorIntelligenceWorkflowAction("SELECT_SAMPLES", {selected_sample_ids: selectedIds});
}

async function dispatchCreatorIntelligenceWorkflowAction(action, requestPayload = {}) {
  if (!currentCloneSetId) {
    return null;
  }
  const response = await fetch(`/api/creator-intelligence/projects/${encodeURIComponent(currentCloneSetId)}/workflow`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      action,
      ...requestPayload,
    }),
  });
  const responsePayload = await readJsonResponse(response);
  const profilePayload = profilePayloadFromCreatorIntelligenceProject(responsePayload);
  applyCreatorIntelligencePayload(profilePayload);
  if (profilePayload.set) {
    refreshProfilePoolFromSet(profilePayload.set);
  }
  return responsePayload;
}

function scheduleCreatorCloneSelectionSync() {
  if (!currentCloneSetId) {
    return;
  }
  window.clearTimeout(creatorCloneSelectionSyncTimer);
  creatorCloneSelectionSyncTimer = window.setTimeout(async () => {
    try {
      await syncCreatorCloneWorkflowSelection();
      renderCreatorCloneNextAction();
    } catch {
      // Keep local selection responsive; explicit actions surface sync errors.
    }
  }, 250);
}

async function markCreatorCloneDistillationStarted() {
  if (!currentCloneSetId) {
    return null;
  }
  await dispatchCreatorIntelligenceWorkflowAction("MARK_EVIDENCE_READY");
  return dispatchCreatorIntelligenceWorkflowAction("START_DISTILLATION");
}

async function useRecommendedProfileSamples() {
  const recommended = recommendedProfileSampleMix();
  if (!recommended.length) {
    profileScanStatus.textContent = "当前素材池还没有可推荐样本，请展开“手动调整样本”自行选择。";
    return;
  }
  setProfileSelection(recommended);
  try {
    await syncCreatorCloneWorkflowSelection();
  } catch (error) {
    profileScanStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "样本选择同步失败"}`;
    return;
  }
  setProfileStageView("select", {scroll: true});
  profileScanStatus.textContent = `已使用推荐样本继续：${recommended.length} 条。`;
}

async function handleWizardPrimaryAction() {
  let command = creatorCloneNextButton?.dataset.creatorCloneAction || creatorCloneStateMeta().command || "";
  if (command === "select_recommended_samples" && selectedCreatorSampleViewItems().length) {
    try {
      await syncCreatorCloneWorkflowSelection();
      renderCreatorCloneNextAction();
      command = creatorCloneNextButton?.dataset.creatorCloneAction || creatorCloneStateMeta().command || command;
    } catch (error) {
      profileScanStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "样本选择同步失败"}`;
      return;
    }
  }
  if (command === "import_input") {
    await runCreatorCloneImportStep();
    if (activeCreatorSampleViewItems().length || currentCloneSetId) {
      setProfileStageView("pool", {scroll: true});
    } else {
      setProfileStageView("import", {scroll: true});
    }
    return;
  }
  if (command === "show_pool") {
    setProfileStageView("pool", {scroll: true});
    renderCreatorCloneNextAction();
    return;
  }
  if (command === "show_select") {
    setProfileStageView("select", {scroll: true});
    renderCreatorCloneNextAction();
    return;
  }
  if (command === "show_distill") {
    setProfileStageView("distill", {scroll: true});
    renderCreatorCloneNextAction();
    return;
  }
  if (command === "select_recommended_samples") {
    await useRecommendedProfileSamples();
    return;
  }
  if (command === "select_samples") {
    setProfileStageView("select", {scroll: true});
    renderCreatorCloneNextAction();
    return;
  }
  if (command === "build_evidence") {
    setProfileStageView("enrich", {scroll: true});
    await buildSelectedProfileQueue();
    return;
  }
  if (command === "start_distillation") {
    setProfileStageView("distill", {scroll: true});
    await distillSelectedCreatorClone();
    return;
  }
  if (command === "start_batch_distillation") {
    setProfileStageView("distill", {scroll: true});
    await batchDistillSelectedCreatorClone({confirm: true});
    return;
  }
  if (command === "export_report") {
    if (downloadCreatorCloneMd?.href && downloadCreatorCloneMd.href !== "#") {
      window.open(downloadCreatorCloneMd.href, "_blank", "noopener,noreferrer");
      return;
    }
    creatorCloneResultCard?.scrollIntoView({behavior: "smooth", block: "start"});
    return;
  }
  renderCreatorCloneNextAction();
}

async function runCreatorCloneNextAction() {
  return handleWizardPrimaryAction();
}

function setProfileSelection(items) {
  const selectedIds = new Set(items.map(sampleViewItemKey));
  profileSelectedKeys = selectedIds;
  invalidateCreatorRuntimeReportForSelectionChange();
  document.querySelectorAll("[data-profile-select]").forEach((input) => {
    input.checked = selectedIds.has(input.value) && !input.disabled;
  });
  updateCreatorCloneSelectionStatus();
  scheduleCreatorCloneSelectionSync();
}

function selectedBuildableSampleViewItems() {
  return selectedCreatorSampleViewItems().filter(isSampleViewItemBuildable);
}

function queueItemPayload(item) {
  const awemeId = item.aweme_id || "";
  const fallbackTitle = item.title || item.desc || item.case_id || item.sample_id || item.source_url || "参考样本";
  return {
    aweme_id: awemeId,
    sample_id: item.sample_id || "",
    case_id: item.case_id || "",
    source_url: item.source_url || "",
    webpage_url: item.webpage_url || item.source_url || (awemeId ? `https://www.douyin.com/video/${awemeId}` : ""),
    title: fallbackTitle,
    media_type: item.media_type || "unknown",
  };
}

function mergeProfileQueueItems(items) {
  const queueItems = normalizeItems(items);
  const baseItems = activeCreatorSampleViewItems();
  if (!queueItems.length || !baseItems.length) {
    return;
  }
  runtimeSampleRows = baseItems.map((item) => {
    const itemKeys = new Set([
      item.sample_id,
      item.aweme_id,
      item.case_id,
      item.source_url,
      item.webpage_url,
    ].filter(Boolean).map(String));
    const queueItem = queueItems.find((candidate) => sampleViewItemMatchesKeySet(candidate, itemKeys));
    if (!queueItem) {
      return item;
    }
    const caseId = queueItem.case_id || item.case_id || "";
    const asrStatus = queueItem.asr_status || item.asr_status || "";
    const ocrStatus = queueItem.ocr_status || item.ocr_status || "";
    const enrichmentStatus = queueItem.enrichment_status || item.enrichment_status || "";
    return {
      ...item,
      case_id: caseId,
      local_video_id: queueItem.local_video_id || item.local_video_id || "",
      has_video: Boolean(item.has_video || queueItem.local_video_id || caseId),
      has_frames: Boolean(item.has_frames || caseId),
      has_asr: Boolean(item.has_asr || ["success", "no_speech"].includes(asrStatus)),
      has_ocr: Boolean(item.has_ocr || ["success", "no_text"].includes(ocrStatus)),
      enrichment_status: enrichmentStatus,
      asr_status: asrStatus,
      ocr_status: ocrStatus,
      analysis_status: queueItem.analysis_status || item.analysis_status || "",
      understanding_level: caseId ? "partial" : (item.understanding_level || "metadata_only"),
    };
  });
  syncCreatorProjectSamplesFromViewItems(runtimeSampleRows);
  renderProfileTable();
}

function renderProfileQueue(result) {
  const items = normalizeItems(result.items);
  revealProfileQueueCard();
  mergeProfileQueueItems(items);
  renderProfileEvidenceQueueProgress(result);
  const completedCount = Number(result.completed_count || 0);
  const failedCount = Number(result.failed_count || 0);
  const referenceOnlyCount = Number(result.reference_only_count || 0);
  const skippedCount = Number(result.skipped_count || 0);
  const otherSkippedCount = Math.max(0, skippedCount - referenceOnlyCount);
  profileQueueSummary.innerHTML = renderProfileQueueSummary({
    completedCount,
    failedCount,
    referenceOnlyCount,
    otherSkippedCount,
    pipelineSummary: result.pipeline_summary || {},
  });
  profileQueueItems.innerHTML = items.length
    ? items
    .map((item) => {
      const caseLink = item.case_id
        ? `<a class="button-link small-link" href="/cases/${escapeHtml(item.case_id)}" target="_blank" rel="noreferrer">打开 Case</a>`
        : "";
      const isReferenceOnly = item.status === "skipped" && item.error_code === "UNSUPPORTED_PROFILE_ITEM";
      const message = isReferenceOnly
        ? item.message || "参考样本已保留，不执行视频下载。"
        : item.error_code
          ? `${item.error_code}：${item.message || ""}`
          : item.message || "";
      const statusLabel = isReferenceOnly ? "参考样本" : item.status || "pending";
      const itemLabel = item.aweme_id || item.case_id || item.sample_id || item.source_url || "参考样本";
      const pipeline = renderProfileQueuePipeline(item);
      return `
        <article class="profile-queue-item ${escapeHtml(item.status || "pending")}">
          <div class="profile-queue-main">
            <strong>${escapeHtml(item.title || itemLabel)}</strong>
            <p><code>${escapeHtml(itemLabel)}</code></p>
          </div>
          <span class="profile-queue-status">${escapeHtml(statusLabel)}</span>
          <p class="profile-queue-message">${escapeHtml(message)}</p>
          ${pipeline}
          ${caseLink}
        </article>
      `;
    })
    .join("")
    : `<p class="muted compact-copy">队列准备中，稍后会显示每条样本的处理状态。</p>`;
}

function renderProfileQueueSummary({completedCount, failedCount, referenceOnlyCount, otherSkippedCount, pipelineSummary}) {
  const notes = normalizeItems(pipelineSummary.notes);
  const actions = normalizeItems(pipelineSummary.next_actions);
  const missingBits = [
    pipelineSummary.asr_provider_missing_count ? `ASR 未配置 ${formatNumber(pipelineSummary.asr_provider_missing_count)} 条` : "",
    pipelineSummary.ocr_provider_missing_count ? `OCR 未配置 ${formatNumber(pipelineSummary.ocr_provider_missing_count)} 条` : "",
  ].filter(Boolean);
  const statusBits = [
    `完成 ${formatNumber(completedCount)} 条`,
    referenceOnlyCount ? `参考 ${formatNumber(referenceOnlyCount)} 条` : "",
    failedCount ? `失败 ${formatNumber(failedCount)} 条` : "",
    otherSkippedCount ? `其他跳过 ${formatNumber(otherSkippedCount)} 条` : "",
  ].filter(Boolean);
  return `
    <p>${escapeHtml(statusBits.join("，") || "队列准备中")}。上方显示总进度，下方显示每条素材的处理状态。</p>
    ${missingBits.length ? `<p class="compact-copy">${missingBits.map(escapeHtml).join("；")}。这是可选富化缺口，不影响已生成素材包继续进入蒸馏。</p>` : ""}
    ${notes.length ? `<p class="compact-copy">${escapeHtml(notes.slice(-1)[0])}</p>` : ""}
    ${
      actions.length
        ? `<p class="compact-copy">${escapeHtml(actions[0])}</p>`
        : ""
    }
  `;
}

function profilePipelineStatusClass(status) {
  const value = String(status || "pending").toLowerCase();
  if (["success", "completed"].includes(value)) {
    return "ready";
  }
  if (["failed", "error"].includes(value)) {
    return "failed";
  }
  if (["provider_missing", "skipped", "not_analyzed"].includes(value)) {
    return "skipped";
  }
  return "pending";
}

function renderProfileQueuePipeline(item) {
  const stages = [
    ["下载", item.local_video_id ? "success" : (["downloading", "building_case", "enriching", "asr_optional", "ocr_optional", "analyzing_optional", "completed"].includes(item.status) ? "success" : "pending")],
    ["素材包", item.case_id ? "success" : (item.status === "building_case" ? "pending" : "")],
    ["富化", item.enrichment_status],
    ["ASR", item.asr_status],
    ["OCR", item.ocr_status],
    ["AI", item.analysis_status],
  ].filter(([, status]) => status !== "");
  if (!stages.length) {
    return "";
  }
  return `
    <div class="profile-queue-pipeline" aria-label="样本处理流水线">
      ${stages
        .map(([label, status]) => `<span class="${profilePipelineStatusClass(status)}">${escapeHtml(label)} · ${escapeHtml(status || "pending")}</span>`)
        .join("")}
    </div>
  `;
}

function refreshProfilePoolFromSet(set) {
  if (!set) {
    return;
  }
  applyCreatorIntelligencePayload({set});
  const selectedIds = new Set(selectedCreatorSampleViewItems().map(sampleViewItemKey));
  currentCloneSetId = set.set_id || currentCloneSetId;
  if (currentCloneSetId) {
    rememberRecentCreatorCloneSetId(currentCloneSetId);
  }
  if (profileContentProfile && set.content_profile) {
    profileContentProfile.value = set.content_profile;
  }
  profileScanPayload = {set};
  runtimeSampleRows = normalizeItems(set.samples);
  syncCreatorProjectSamplesFromViewItems(runtimeSampleRows);
  renderProfileSummary(cloneSummaryFromSet(set) || {});
  renderProfileDecisionBoard({set});
  renderProfileTable();
  setProfileSelection(activeCreatorSampleViewItems().filter((item) => selectedIds.has(sampleViewItemKey(item))));
  updateCreatorCloneSelectionStatus();
  const warnings = normalizeItems(set.warnings);
  profileWarnings.classList.toggle("hidden", !warnings.length);
  profileWarnings.textContent = warnings.join(" ");
}

async function pollProfileQueue(jobId) {
  const response = await fetch(`/api/jobs/${jobId}`, {cache: "no-store"});
  const payload = await readJsonResponse(response);
  const job = payload.job;
  renderJobStatus(job);
  renderProfileQueue(job.result_json || {});
  if (job.status === "success") {
    renderJobStatus(job);
    if (job.result_json?.set) {
      refreshProfilePoolFromSet(job.result_json.set);
    }
    updateCreatorCloneSelectionStatus();
    if (profileAutoDistill?.checked) {
      const selected = selectedCreatorSampleViewItems();
      if (selected.length > CREATOR_CLONE_MAX_DISTILL_SAMPLES) {
        setProfileStageView("distill", {scroll: true});
        profileScanStatus.textContent = "样本富化队列完成，正在继续进行分批大模型蒸馏...";
        await batchDistillSelectedCreatorClone({confirm: false, triggeredByQueue: true});
      } else {
        setProfileStageView("distill", {scroll: true});
        profileScanStatus.textContent = "样本富化队列完成，正在继续进行大模型蒸馏...";
        await distillSelectedCreatorClone({confirmReadiness: false, triggeredByQueue: true});
      }
      return;
    }
    setProfileStageView("distill", {scroll: true});
    profileScanStatus.textContent = "样本富化队列完成。请确认样本仍然勾选，然后点击“大模型蒸馏”或“高级：分批蒸馏”。";
    return;
  }
  if (job.status === "failed") {
    jobMessage.className = "job-message failed";
    jobMessage.textContent = `${job.error_code || "ERROR"}：${job.message || "任务失败"}`;
    updateCreatorCloneSelectionStatus();
    return;
  }
  await new Promise((resolve) => {
    window.setTimeout(resolve, 900);
  });
  return pollProfileQueue(jobId);
}

// Creator Clone: enrichment queue
async function buildSelectedProfileQueue() {
  if (creatorCloneEnrichmentRunning) {
    return;
  }
  const selected = selectedCreatorSampleViewItems();
  if (!selected.length) {
    profileScanStatus.textContent = `请先选择代表样本。视频样本会下载富化，图文/元数据样本会保存为蒸馏参考。`;
    return;
  }
  setProfileStageView("enrich", {scroll: true});
  const buildableCount = selected.filter(isSampleViewItemBuildable).length;
  const referenceOnlyCount = selected.length - buildableCount;
  if (buildableCount > PROFILE_BUILD_MAX_ITEMS) {
    profileScanStatus.textContent = `当前自用版最多一次富化 ${PROFILE_BUILD_MAX_ITEMS} 条可下载视频，避免误批量下载。`;
    return;
  }
  setCreatorCloneEnrichmentLocked(true);
  renderCreatorCloneNextAction();
  try {
    await syncCreatorCloneWorkflowSelection();
    placeJobCard("profile");
    resetJobCard(buildableCount
      ? `创建素材富化队列：视频 ${buildableCount} 条，参考样本 ${referenceOnlyCount} 条。`
      : `保存选样：${referenceOnlyCount} 条仅作为蒸馏参考，不执行视频下载。`);
    revealProfileQueueCard();
    profileQueueSummary.innerHTML = renderProfileQueueSummary({
      completedCount: 0,
      failedCount: 0,
      referenceOnlyCount,
      otherSkippedCount: 0,
      pipelineSummary: {
        selected_count: selected.length,
        downloadable_count: buildableCount,
        reference_only_count: referenceOnlyCount,
        notes: [`已创建本地计划队列 ${selected.length} 条，等待后端逐条回写处理状态。`],
      },
    });
    renderProfileQueue({items: selected.map((item) => ({
      ...queueItemPayload(item),
      status: "pending",
      message: isSampleViewItemBuildable(item) ? "等待下载和素材包生成" : "参考样本等待保留",
      enrichment_status: isSampleViewItemBuildable(item) ? "pending" : "skipped",
      asr_status: isSampleViewItemBuildable(item) ? "pending" : "skipped",
      ocr_status: isSampleViewItemBuildable(item) ? "pending" : "skipped",
      analysis_status: "skipped",
    })), pipeline_summary: {
      selected_count: selected.length,
      downloadable_count: buildableCount,
      reference_only_count: referenceOnlyCount,
      notes: [`已创建本地计划队列 ${selected.length} 条，等待后端逐条回写处理状态。`],
    }});
    profileQueueCard.scrollIntoView({behavior: "smooth", block: "start"});
    const response = await fetch("/api/jobs/profile-build-cases", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        items: selected.map(queueItemPayload),
        selected_sample_ids: selectedCreatorSampleViewItems().map(sampleViewItemKey),
        auto_enrich: true,
        auto_asr: true,
        auto_ocr: true,
        auto_analyze: false,
        quality_preference: qualityPreference?.value || "1080",
        sample_set_id: currentCloneSetId,
      }),
    });
    const payload = await readJsonResponse(response);
    rememberRecentProfileBuildState({
      setId: currentCloneSetId,
      jobId: payload.job_id,
      selectedSampleIds: selectedCreatorSampleViewItems().map(sampleViewItemKey),
    });
    profileScanStatus.textContent = buildableCount
      ? `已创建样本富化队列：${payload.selected_count} 条；可下载视频会生成素材包，图文/元数据样本会作为蒸馏参考。`
      : `已保存 ${payload.selected_count} 条参考样本；这些样本不下载视频，可直接进入大模型蒸馏。`;
    await pollProfileQueue(payload.job_id);
  } catch (error) {
    jobMessage.className = "job-message failed";
    jobMessage.textContent = `${error.error_code || "ERROR"}：${error.message || "队列创建失败"}`;
    profileScanStatus.textContent = jobMessage.textContent;
    updateCreatorCloneSelectionStatus();
  } finally {
    setCreatorCloneEnrichmentLocked(false);
    updateCreatorCloneSelectionStatus();
    renderCreatorCloneNextAction();
  }
}

function topCreatorSampleViewItemsBy(key, count = 3) {
  return sortCreatorSampleViewItems(activeCreatorSampleViewItems(), key).slice(0, count);
}

function lowPerformanceCreatorSampleViewItems(count = 3) {
  return [...activeCreatorSampleViewItems()]
    .sort((left, right) => Number(left.engagement_score || 0) - Number(right.engagement_score || 0))
    .slice(0, count);
}

function needsEnrichmentCreatorSampleViewItems(count = 5) {
  return sortCreatorSampleViewItems(activeCreatorSampleViewItems().filter((item) => isSampleViewItemBuildable(item) && !item.has_frames), "engagement_score").slice(0, count);
}

function profileEvidenceScore(item) {
  return [
    item.has_video,
    item.has_frames,
    item.has_asr,
    item.has_ocr,
    item.has_comments,
  ].filter(Boolean).length;
}

function readyEvidenceCreatorSampleViewItems(count = 5) {
  return [...activeCreatorSampleViewItems()]
    .filter((item) => profileEvidenceScore(item) >= 2)
    .sort((left, right) => {
      const scoreDiff = profileEvidenceScore(right) - profileEvidenceScore(left);
      return scoreDiff || Number(right.engagement_score || 0) - Number(left.engagement_score || 0);
    })
    .slice(0, count);
}

function profileDistillReadiness(items) {
  const selected = normalizeItems(items);
  const counts = selected.reduce(
    (acc, item) => {
      acc.metadataOnly += !item.understanding_level || item.understanding_level === "metadata_only" ? 1 : 0;
      acc.video += item.media_type === "video" ? 1 : 0;
      acc.image += item.media_type === "image" ? 1 : 0;
      acc.unknown += item.media_type === "unknown" ? 1 : 0;
      acc.buildable += isSampleViewItemBuildable(item) ? 1 : 0;
      acc.frames += item.has_frames ? 1 : 0;
      acc.asr += item.has_asr ? 1 : 0;
      acc.ocr += item.has_ocr ? 1 : 0;
      acc.comments += item.has_comments ? 1 : 0;
      acc.score += profileEvidenceScore(item);
      const mediaType = item.media_type || "unknown";
      acc.mediaTypes[mediaType] = (acc.mediaTypes[mediaType] || 0) + 1;
      return acc;
    },
    {metadataOnly: 0, video: 0, image: 0, unknown: 0, buildable: 0, frames: 0, asr: 0, ocr: 0, comments: 0, score: 0, mediaTypes: {}},
  );
  const averageScore = selected.length ? counts.score / selected.length : 0;
  const warnings = [];
  const mediaTypeKeys = Object.keys(counts.mediaTypes).filter((key) => counts.mediaTypes[key] > 0);
  if (mediaTypeKeys.length > 1) {
    warnings.push(`混合格式样本：视频 ${counts.mediaTypes.video || 0}，图文 ${counts.mediaTypes.image || 0}，未知 ${counts.mediaTypes.unknown || 0}`);
  } else if (counts.mediaTypes.image || counts.mediaTypes.unknown) {
    warnings.push(`非视频样本 ${selected.length}/${selected.length}：只能作为封面、标题或元数据参考`);
  }
  if (counts.metadataOnly >= Math.ceil(selected.length / 2)) {
    warnings.push(`仅元数据样本 ${counts.metadataOnly}/${selected.length}`);
  }
  if (counts.frames < Math.ceil(selected.length / 2)) {
    warnings.push(`有关键帧样本 ${counts.frames}/${selected.length}`);
  }
  if (averageScore < 2) {
    warnings.push(`平均证据分 ${averageScore.toFixed(1)}/5`);
  }
  const recommendations = [];
  if (!selected.length) {
    recommendations.push("先从素材池选择代表样本。");
  } else if (warnings.length) {
    recommendations.push("建议先点击主按钮开始富化证据，补齐视频、关键帧、OCR、ASR 后再蒸馏。");
  } else {
    recommendations.push("证据足够，可以直接开始大模型蒸馏。");
  }
  if (counts.image || counts.unknown) {
    recommendations.push("混合图文/未知样本时，蒸馏结论会更多依赖封面、标题、指标和元数据。");
  }
  if (counts.comments === 0) {
    recommendations.push("后续可导入评论，用于判断争议点、需求和互动动机。");
  }
  return {ready: !warnings.length, warnings, averageScore, counts, recommendations};
}

function renderProfileDistillReadiness(items) {
  if (!profileDistillReadinessStatus) {
    return;
  }
  const selected = normalizeItems(items);
  if (!selected.length) {
    profileDistillReadinessStatus.classList.remove("ready", "warning");
    profileDistillReadinessStatus.innerHTML = `
      <div class="distill-readiness-head">
        <strong>蒸馏准备度</strong>
        <p>先选择代表样本。系统会根据样本数量、格式结构、关键帧和证据完整度提示是否适合蒸馏。</p>
      </div>
    `;
    return;
  }
  const readiness = profileDistillReadiness(selected);
  profileDistillReadinessStatus.classList.toggle("ready", readiness.ready);
  profileDistillReadinessStatus.classList.toggle("warning", !readiness.ready);
  const counts = readiness.counts || {};
  const metrics = [
    ["已选样本", selected.length],
    ["可富化视频", counts.buildable],
    ["关键帧", counts.frames],
    ["ASR", counts.asr],
    ["OCR", counts.ocr],
    ["评论", counts.comments],
  ];
  profileDistillReadinessStatus.innerHTML = `
    <div class="distill-readiness-head">
      <strong>${readiness.ready ? "蒸馏准备度：可开始" : "蒸馏准备度：建议先富化"}</strong>
      <p>平均证据分 ${readiness.averageScore.toFixed(1)}/5；视频 ${formatNumber(counts.video)}，图文 ${formatNumber(counts.image)}，未知 ${formatNumber(counts.unknown)}，仅元数据 ${formatNumber(counts.metadataOnly)}。</p>
    </div>
    <div class="distill-readiness-matrix" aria-label="蒸馏证据矩阵">
      ${metrics.map(([label, value]) => `<span><strong>${formatNumber(value || 0)}</strong>${escapeHtml(label)}</span>`).join("")}
    </div>
    ${
      readiness.warnings.length
        ? `<ul class="distill-readiness-warnings">${readiness.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>`
        : ""
    }
    <ul class="distill-readiness-actions">
      ${readiness.recommendations.map((action) => `<li>${escapeHtml(action)}</li>`).join("")}
    </ul>
  `;
}

function confirmProfileDistillReadiness(selected) {
  const readiness = profileDistillReadiness(selected);
  if (readiness.ready) {
    return true;
  }
  return window.confirm(
    `当前选样证据不足：${readiness.warnings.join("；")}。\n建议先点击主按钮开始富化证据，补齐视频、关键帧、OCR、ASR 后再蒸馏。\n仍要继续生成临时蒸馏结果吗？`,
  );
}

function dedupeCreatorSampleViewItems(items, limit = 10) {
  const seen = new Set();
  const deduped = [];
  normalizeItems(items).forEach((item) => {
    const key = sampleViewItemKey(item);
    if (!key || seen.has(key) || deduped.length >= limit) {
      return;
    }
    seen.add(key);
    deduped.push(item);
  });
  return deduped;
}

function recommendedProfileSampleMix() {
  return dedupeCreatorSampleViewItems(
    [
      ...topCreatorSampleViewItemsBy("like_count", 3),
      ...topCreatorSampleViewItemsBy("comment_count", 2),
      ...topCreatorSampleViewItemsBy("share_count", 2),
      ...topCreatorSampleViewItemsBy("collect_count", 2),
      ...topCreatorSampleViewItemsBy("create_time", 2),
      ...lowPerformanceCreatorSampleViewItems(2),
    ],
    10,
  );
}

function profilePresetItems(preset) {
  if (preset === "recommended_mix") {
    return recommendedProfileSampleMix();
  }
  const match = String(preset || "").match(/^(top_likes|top_comments|top_shares|top_collects|latest|low_performance|needs_enrichment|ready_evidence)_(\d+)$/);
  if (match) {
    const [, type, countText] = match;
    const count = Math.max(1, Number(countText || 3));
    if (type === "top_likes") return topCreatorSampleViewItemsBy("like_count", count);
    if (type === "top_comments") return topCreatorSampleViewItemsBy("comment_count", count);
    if (type === "top_shares") return topCreatorSampleViewItemsBy("share_count", count);
    if (type === "top_collects") return topCreatorSampleViewItemsBy("collect_count", count);
    if (type === "latest") return topCreatorSampleViewItemsBy("create_time", count);
    if (type === "low_performance") return lowPerformanceCreatorSampleViewItems(count);
    if (type === "needs_enrichment") return needsEnrichmentCreatorSampleViewItems(count);
    if (type === "ready_evidence") return readyEvidenceCreatorSampleViewItems(count);
  }
  return [];
}

function profilePresetLabel(preset) {
  const match = String(preset || "").match(/^(top_likes|top_comments|top_shares|top_collects|latest|low_performance|needs_enrichment|ready_evidence)_(\d+)$/);
  if (match) {
    const [, type, count] = match;
    const labels = {
      top_likes: `高赞 Top ${count}`,
      top_comments: `高评 Top ${count}`,
      top_shares: `高分享 Top ${count}`,
      top_collects: `高收藏 Top ${count}`,
      latest: `最新 Top ${count}`,
      low_performance: `低表现 ${count} 条`,
      needs_enrichment: `待富化 Top ${count}`,
      ready_evidence: `证据完整 Top ${count}`,
    };
    return labels[type] || "分层样本";
  }
  return {
    recommended_mix: "推荐组合",
  }[preset] || "分层样本";
}

function applyProfilePresetSelection(preset) {
  if (!activeCreatorSampleViewItems().length) {
    profileScanStatus.textContent = "请先扫描或导入账号素材清单。";
    return;
  }
  const items = profilePresetItems(preset);
  setProfileSelection(items);
  profileScanStatus.textContent = `已选择${profilePresetLabel(preset)}：${items.length} 条。可继续手动勾选补充代表样本。`;
}

function creatorCloneSamplePayload(item) {
  return {
    sample_id: sampleViewItemKey(item),
    source_type: item.source_type || "douyin",
    source_url: item.source_url || item.webpage_url || "",
    aweme_id: item.aweme_id || "",
    title: item.title || item.desc || "",
    desc: item.desc || "",
    author: item.author || "",
    cover_url: item.cover_url || "",
    media_type: item.media_type || "unknown",
    like_count: Number(item.like_count || 0),
    comment_count: Number(item.comment_count || 0),
    share_count: Number(item.share_count || 0),
    collect_count: Number(item.collect_count || 0),
    view_count: Number(item.view_count || 0),
    create_time: item.create_time || "",
    case_id: item.case_id || "",
    understanding_level: item.understanding_level || "metadata_only",
    has_video: Boolean(item.has_video),
    has_frames: Boolean(item.has_frames),
    has_asr: Boolean(item.has_asr),
    has_ocr: Boolean(item.has_ocr),
    has_comments: Boolean(item.has_comments),
    enrichment_status: item.enrichment_status || "pending",
    asr_status: item.asr_status || "pending",
    ocr_status: item.ocr_status || "pending",
    analysis_status: item.analysis_status || "not_analyzed",
    tags: item.tags || [],
    notes: item.notes || "",
  };
}

function renderProfileSegments(segments) {
  return `
    <h5>高赞样本</h5>${renderSegmentSampleList(segments.highest_like_samples, "like_count", "赞")}
    <h5>高评论样本</h5>${renderSegmentSampleList(segments.highest_comment_samples, "comment_count", "评")}
    <h5>高分享样本</h5>${renderSegmentSampleList(segments.highest_share_samples, "share_count", "分享")}
    <h5>高收藏样本</h5>${renderSegmentSampleList(segments.highest_collect_samples, "collect_count", "收藏")}
    <h5>弱样本 / 对照样本</h5>${renderSegmentSampleList(segments.weak_or_reference_samples, "engagement_score", "综合")}
  `;
}

function segmentListCount(value) {
  return normalizeItems(value).length;
}

function renderCompactPerformanceSegments(segments = {}) {
  const chips = [
    ["高赞", segments.highest_like_samples],
    ["高评", segments.highest_comment_samples],
    ["高分享", segments.highest_share_samples],
    ["高收藏", segments.highest_collect_samples],
    ["对照", segments.weak_or_reference_samples],
  ].map(([label, rows]) => `<span class="segment-summary-chip">${escapeHtml(label)} ${formatNumber(segmentListCount(rows))}</span>`);
  return `
    <details class="creator-clone-segment-disclosure">
      <summary>
        <span>样本分层摘要</span>
        ${chips.join("")}
      </summary>
      <div class="profile-segment-body">
        ${renderProfileSegments(segments)}
      </div>
    </details>
  `;
}

function renderTopicBuckets(buckets) {
  const rows = normalizeItems(buckets).map((item) => {
    if (!item || typeof item !== "object") {
      return item;
    }
    const name = item.name || item.title || "";
    const parts = [
      item.description,
      item.why_it_works ? `为什么有效：${item.why_it_works}` : "",
      item.evidence ? `证据：${formatReportValue(item.evidence)}` : "",
    ].filter(isMeaningfulReportText);
    return [name, parts.join("；")].filter(isMeaningfulReportText).join("：");
  }).filter(isMeaningfulReportText);
  return renderPublicList(rows, "暂无稳定选题方向。");
}

function renderFormulaCards(formulas) {
  const rows = normalizeItems(formulas).map((item) => {
    if (!item || typeof item !== "object") {
      return item;
    }
    const name = item.name || item.title || item.formula || "";
    const parts = [
      item.when_to_use ? `适用：${item.when_to_use}` : "",
      publicValueHasContent(item.input_material_needed) ? `素材：${formatReportValue(item.input_material_needed)}` : "",
      publicValueHasContent(item.beat_structure || item.beats || item.structure) ? `结构：${formatReportValue(item.beat_structure || item.beats || item.structure)}` : "",
      item.expected_metric_strength ? `强项：${item.expected_metric_strength}` : "",
      publicValueHasContent(item.risks) ? `风险：${formatReportValue(item.risks)}` : "",
    ].filter(isMeaningfulReportText);
    return [name, parts.join("；")].filter(isMeaningfulReportText).join("：");
  }).filter(isMeaningfulReportText);
  return renderPublicList(rows, "本次没有返回独立公式，建议先从高互动样本中人工提炼 2-3 个可复用拍法。");
}

function renderCandidateIdeas(ideas) {
  const rows = normalizeItems(ideas).map((item) => {
    if (!item || typeof item !== "object") {
      return item;
    }
    const title = item.title || item.idea || item.name || "";
    const parts = [
      item.formula_used ? `使用公式：${item.formula_used}` : "",
      item.why_worth_trying || item.reason ? `理由：${item.why_worth_trying || item.reason}` : "",
      item.likely_strength ? `强度：${item.likely_strength}` : "",
      publicValueHasContent(item.production_requirements) ? `制作要求：${formatReportValue(item.production_requirements)}` : "",
    ].filter(isMeaningfulReportText);
    return [title, parts.join("；")].filter(isMeaningfulReportText).join("：");
  }).filter(isMeaningfulReportText);
  return renderPublicList(rows, "本次没有返回独立选题库，可先基于爆款共性手动生成候选选题。");
}

function compactReportList(...values) {
  const rows = [];
  values.forEach((value) => {
    normalizeItems(value).forEach((item) => {
      const text = reportItemPrimaryText(item).trim();
      if (isMeaningfulReportText(text) && !rows.includes(text)) {
        rows.push(text);
      }
    });
  });
  return rows;
}

function isTechnicalReportNote(value) {
  return /(LLM|Reduce|Prompt|批次|本地汇总|大模型暂不可用|大模型未配置|重试|超时|失败|fallback|prompt_only)/i.test(String(value || ""));
}

function trimReportClause(value) {
  return String(value || "").replace(/\s+/g, " ").trim().replace(/[。；;,，、\s]+$/g, "");
}

function truncateReportText(value, limit = 120) {
  const text = trimReportClause(value);
  return text.length > limit ? `${text.slice(0, limit - 1).trim()}…` : text;
}

function compactPublicReportText(value, limit = 240) {
  const chunks = [];
  normalizeItems(value).forEach((item) => {
    const text = reportItemPrimaryText(item).replace(/\s+/g, " ").trim();
    text.split(/[。；;!！?？]\s*/).forEach((part) => {
      const clean = trimReportClause(part);
      if (!isMeaningfulReportText(clean) || isTechnicalReportNote(clean) || chunks.includes(clean)) {
        return;
      }
      chunks.push(truncateReportText(clean, 96));
    });
  });
  const summary = chunks.slice(0, 3).join("；");
  return summary.length > limit ? `${summary.slice(0, limit - 1).trim()}…` : summary;
}

function compactReportHeadline(value, limit = 120) {
  for (const item of normalizeItems(value)) {
    const text = reportItemPrimaryText(item).replace(/\s+/g, " ").trim();
    for (const part of text.split(/[。；;!！?？]\s*/)) {
      const clean = trimReportClause(part);
      if (isMeaningfulReportText(clean) && !isTechnicalReportNote(clean)) {
        return truncateReportText(clean, limit);
      }
    }
  }
  return "";
}

function nonTechnicalReportList(...values) {
  return compactReportList(...values).filter((item) => !isTechnicalReportNote(item));
}

function technicalReportNotes(...values) {
  return compactReportList(...values).filter(isTechnicalReportNote).slice(0, 6);
}

function reportViewEvidenceCountsFromOverview(overview = {}) {
  const counts = overview.understanding_counts || {};
  return {
    selected_count: Number(overview.selected_count || 0),
    sample_count: Number(overview.sample_count || 0),
    understanding_full: Number(counts.full || 0),
    understanding_partial: Number(counts.partial || 0),
    understanding_metadata_only: Number(counts.metadata_only || 0),
  };
}

function creatorReportViewModelFromResult(result = {}, overview = {}, templateLabel = "") {
  if (result.creator_report_view_model && typeof result.creator_report_view_model === "object") {
    const viewModel = {...result.creator_report_view_model};
    viewModel.headline = compactReportHeadline(viewModel.headline || result.summary, 120) || truncateReportText(viewModel.headline || "", 120);
    viewModel.summary = compactPublicReportText(viewModel.summary || result.summary) || truncateReportText(viewModel.summary || result.summary || "", 240);
    viewModel.technical_notes = normalizeItems(viewModel.technical_notes).filter(isMeaningfulReportText).slice(0, 6);
    return viewModel;
  }
  const strategy = creatorStrategyFromResult(result) || {};
  const positioning = result.creator_positioning || {};
  const patterns = result.expression_patterns || {};
  const thinking = result.thinking_patterns || {};
  const spec = result.creator_clone_spec || {};
  const segments = result.performance_segments || {};
  const headline = compactReportHeadline(strategy.positioning || positioning.what_the_creator_sells || positioning.audience_promise || "账号规律已完成蒸馏", 120);
  const fallbackSummary = compactPublicReportText([
    strategy.positioning,
    positioning.what_the_creator_sells,
    positioning.audience_promise,
    result.summary,
  ]);
  const formulas = nonTechnicalReportList(strategy.templates, result.transferable_formulas).slice(0, 5);
  const ideas = nonTechnicalReportList(strategy.idea_bank, result.candidate_ideas, result.topic_buckets).slice(0, 6);
  return {
    headline,
    summary: fallbackSummary || "请先查看下方核心结论、流量来源和可复刻公式。",
    template_label: templateLabel || result.content_profile?.effective_label || "自动识别",
    confidence_label: overview.confidence || "",
    confidence_note: overview.confidence ? `系统置信度：${overview.confidence}` : "",
    evidence_counts: reportViewEvidenceCountsFromOverview(overview),
    sections: {
      core_judgment: {
        fields: [
          {label: "定位", value: headline},
          {label: "观众承诺", value: positioning.audience_promise},
          {label: "隐藏类型", value: positioning.hidden_genre},
          {label: "观众假设", value: positioning.audience_assumption},
        ],
        bullets: nonTechnicalReportList(positioning.audience_promise, positioning.hidden_genre, positioning.audience_assumption, result.summary).slice(0, 5),
      },
      traffic_sources: {
        metric_signals: compactReportList(
          firstSegmentBrief(segments, "highest_like_samples", "高赞"),
          firstSegmentBrief(segments, "highest_comment_samples", "高评"),
          firstSegmentBrief(segments, "highest_share_samples", "高分享"),
          firstSegmentBrief(segments, "highest_collect_samples", "高收藏"),
        ).slice(0, 4),
        hooks: nonTechnicalReportList(strategy.hooks, patterns.opening_hooks, thinking.tension_sources, positioning.audience_promise).slice(0, 6),
      },
      formulas: formulas.length ? formulas : nonTechnicalReportList(strategy.content_strategy, spec.structure_rules, spec.visual_rules, patterns.opening_hooks).slice(0, 5),
      repeatable_patterns: nonTechnicalReportList(result.topic_buckets, patterns.visual_style, patterns.scene_order, patterns.subtitle_voice, spec.expression_rules, spec.visual_rules, spec.structure_rules).slice(0, 6),
      next_ideas: ideas,
      next_actions: nonTechnicalReportList(result.next_actions, result.topic_buckets).slice(0, 5),
      checklist: nonTechnicalReportList(strategy.validation_rules, spec.self_check_rubric).slice(0, 6),
      anti_patterns: nonTechnicalReportList(strategy.anti_patterns, spec.anti_patterns).slice(0, 6),
    },
    technical_notes: technicalReportNotes(overview.warnings, result.next_actions, result.evidence_gaps),
  };
}

function renderDistillationFormulaList(strategy, result) {
  const templates = normalizeItems(strategy.templates);
  const formulas = normalizeItems(result.transferable_formulas);
  if (templates.length || formulas.length) {
    return renderFormulaCards(templates.length ? templates : formulas);
  }
  const fallback = compactReportList(
    strategy.content_strategy,
    result.creator_clone_spec?.structure_rules,
    result.creator_clone_spec?.visual_rules,
    result.expression_patterns?.opening_hooks,
  ).slice(0, 4);
  return renderPublicList(fallback, "本次没有返回独立公式，建议先从内容策略中人工提炼 2-3 个可复用拍法。");
}

function renderDistillationIdeaList(strategy, result) {
  const ideas = normalizeItems(strategy.idea_bank);
  const candidates = normalizeItems(result.candidate_ideas);
  if (ideas.length || candidates.length) {
    return renderCandidateIdeas(ideas.length ? ideas : candidates);
  }
  const buckets = normalizeItems(result.topic_buckets).map((item) => {
    if (!item || typeof item !== "object") {
      return item;
    }
    return item.name || item.title || item.description || formatReportValue(item);
  });
  return renderPublicList(buckets.slice(0, 6), "本次没有返回独立选题库，可先基于爆款共性手动生成候选选题。");
}

function renderDistillationSegmentGrid(segments = {}) {
  return `
    <div class="creator-segment-grid">
      <section>
        <h5>高赞：情绪 / 身份共鸣</h5>
        ${renderSegmentSampleList(segments.highest_like_samples, "like_count", "赞", "暂无高赞分层。")}
      </section>
      <section>
        <h5>高评：讨论 / 参与钩子</h5>
        ${renderSegmentSampleList(segments.highest_comment_samples, "comment_count", "评", "暂无高评分层。")}
      </section>
      <section>
        <h5>高分享：转发理由</h5>
        ${renderSegmentSampleList(segments.highest_share_samples, "share_count", "分享", "暂无高分享分层。")}
      </section>
      <section>
        <h5>高收藏：模板 / 复看价值</h5>
        ${renderSegmentSampleList(segments.highest_collect_samples, "collect_count", "收藏", "暂无高收藏分层。")}
      </section>
    </div>
  `;
}

function reportValueHasAny(...values) {
  return values.some((value) => publicValueHasContent(value));
}

function renderThinkingPatternBlock(patterns = {}) {
  return `
    ${renderPublicFields([
      ["熟悉与新鲜感", patterns.novelty_vs_familiarity],
    ])}
    <h5>观众假设</h5>
    ${renderPublicList(patterns.assumptions, "暂无观众假设。")}
    <h5>张力来源</h5>
    ${renderPublicList(patterns.tension_sources, "暂无张力判断。")}
    <h5>细节选择规则</h5>
    ${renderPublicList(patterns.detail_selection_rules, "暂无细节选择规则。")}
  `;
}

function renderExpressionPatternBlock(patterns = {}, spec = {}) {
  const values = compactReportList(
    patterns.opening_hooks,
    patterns.scene_order,
    patterns.shot_types,
    patterns.subtitle_voice,
    patterns.visual_style,
    patterns.ending_patterns,
    spec.expression_rules,
    spec.visual_rules,
    spec.ending_rules,
  );
  return renderPublicList(values, "暂无表达/视觉规律。");
}

function renderCloneRulesBlock(spec = {}, strategy = {}) {
  return `
    ${renderPublicFields([
      ["Taste", spec.taste],
      ["字幕/文案语气", spec.caption_voice],
    ])}
    <h5>选题规则</h5>
    ${renderPublicList(spec.topic_selection_rules || strategy.content_strategy, "暂无选题规则。")}
    <h5>结构规则</h5>
    ${renderPublicList(spec.structure_rules, "暂无结构规则。")}
    <h5>自检规则</h5>
    ${renderPublicList(spec.self_check_rubric || strategy.validation_rules, "暂无自检规则。")}
  `;
}

function renderCreatorReportHero({viewModel, summary, templateLabel, overview, positioningText}) {
  const evidence = viewModel?.evidence_counts || {};
  const counts = overview?.understanding_counts || {};
  const selectedCount = Number(evidence.selected_count ?? overview?.selected_count ?? 0);
  const sampleCount = Number(evidence.sample_count ?? overview?.sample_count ?? 0);
  const confidence = viewModel?.confidence_label || overview?.confidence || "";
  const evidenceLine = viewModel?.confidence_note
    || `完整 ${formatNumber(counts.full || evidence.understanding_full || 0)} · 部分 ${formatNumber(counts.partial || evidence.understanding_partial || 0)} · 仅元数据 ${formatNumber(counts.metadata_only || evidence.understanding_metadata_only || 0)}`;
  const mediaLine = [evidence.with_video, evidence.with_keyframes, evidence.with_asr, evidence.with_ocr, evidence.with_comments]
    .some((value) => value !== undefined)
    ? `视频 ${formatNumber(evidence.with_video || 0)} · 关键帧 ${formatNumber(evidence.with_keyframes || 0)} · ASR ${formatNumber(evidence.with_asr || 0)} · OCR ${formatNumber(evidence.with_ocr || 0)} · 评论 ${formatNumber(evidence.with_comments || 0)}`
    : "";
  return `
    <article class="creator-report-hero-card">
      <div>
        <span>创作者蒸馏报告</span>
        <h3>${escapeHtml(viewModel?.headline || positioningText || "账号规律已完成蒸馏")}</h3>
        <p>${escapeHtml(viewModel?.summary || summary || "请先查看下方核心结论和可复刻公式。")}</p>
      </div>
      <dl>
        <dt>分析模板</dt>
        <dd>${escapeHtml(viewModel?.template_label || templateLabel || "自动识别")}</dd>
        <dt>样本</dt>
        <dd>${formatNumber(selectedCount)} / ${formatNumber(sampleCount)}</dd>
        <dt>证据完整度</dt>
        <dd>${escapeHtml(evidenceLine)}</dd>
        ${mediaLine ? `<dt>证据覆盖</dt><dd>${escapeHtml(mediaLine)}</dd>` : ""}
        ${confidence ? `<dt>置信度</dt><dd>${escapeHtml(confidence)}</dd>` : ""}
      </dl>
    </article>
  `;
}

function renderCreatorReportTrafficSignals(segments, positioning, patterns, strategy) {
  const metricSignals = compactReportList(
    firstSegmentBrief(segments, "highest_like_samples", "高赞"),
    firstSegmentBrief(segments, "highest_comment_samples", "高评"),
    firstSegmentBrief(segments, "highest_share_samples", "高分享"),
    firstSegmentBrief(segments, "highest_collect_samples", "高收藏"),
  ).slice(0, 4);
  const hookSignals = compactReportList(
    strategy.hooks,
    patterns.opening_hooks,
    positioning.hidden_genre,
    positioning.audience_promise,
  ).slice(0, 8);
  return `
    ${metricSignals.length ? `
      <h5>数据里最强的信号</h5>
      ${renderPublicList(metricSignals)}
    ` : ""}
    <h5>抓停留 / 促互动方式</h5>
    ${renderPublicList(hookSignals, "暂无明确钩子。")}
  `;
}

function renderCreatorReportActionPlan(strategy, result) {
  const nextActions = nonTechnicalReportList(
    result.next_actions,
    result.topic_buckets,
  ).slice(0, 6);
  return `
    <h5>候选选题</h5>
    ${renderDistillationIdeaList(strategy, result)}
    <h5>下一步动作</h5>
    ${renderPublicList(nextActions, "先从最高互动样本中选 3 条，人工复核开头、封面、动作和标题，再生成候选脚本。")}
  `;
}

function renderCreatorReportChecklist(strategy, spec) {
  const validationRules = nonTechnicalReportList(strategy.validation_rules, spec.self_check_rubric).slice(0, 6);
  const antiPatterns = nonTechnicalReportList(strategy.anti_patterns, spec.anti_patterns).slice(0, 6);
  return `
    <h5>发布前自检</h5>
    ${renderPublicList(validationRules, "暂无自检规则。")}
    <h5>不要照搬 / 风险边界</h5>
    ${renderPublicList(antiPatterns, "暂无风险边界。")}
  `;
}

function firstSegmentBrief(segments, key, metricLabel) {
  const item = normalizeItems(segments?.[key])[0];
  if (!item || typeof item !== "object") {
    return "";
  }
  const title = item.title || item.desc || item.source_url || "代表样本";
  const metricValue = item.metric_value ?? item.like_count ?? item.comment_count ?? item.share_count ?? item.collect_count;
  return metricValue !== undefined && metricValue !== null && metricValue !== ""
    ? `${metricLabel}代表：${title}（${formatNumber(metricValue)}）`
    : `${metricLabel}代表：${title}`;
}

function renderCreatorDistillationEvidenceDetails(overview, result, reportViewModel = null) {
  const thinking = result.thinking_patterns || {};
  const patterns = result.expression_patterns || {};
  const spec = result.creator_clone_spec || {};
  const strategy = creatorStrategyFromResult(result) || {};
  const viewModel = reportViewModel || result.creator_report_view_model || null;
  const hasThinking = reportValueHasAny(thinking.assumptions, thinking.tension_sources, thinking.detail_selection_rules, thinking.novelty_vs_familiarity);
  const hasExpression = reportValueHasAny(
    patterns.opening_hooks,
    patterns.scene_order,
    patterns.shot_types,
    patterns.subtitle_voice,
    patterns.visual_style,
    patterns.ending_patterns,
    spec.expression_rules,
    spec.visual_rules,
  );
  return `
    <details class="creator-report-evidence-details">
      <summary>报告依据：样本、证据完整度和后台细节</summary>
      ${renderCreatorCloneEvidenceOverview(overview)}
      ${renderCompactPerformanceSegments(result.performance_segments || {})}
      <div class="creator-report-evidence-inner">
        ${reportValueHasAny(result.topic_buckets) ? `
          <section>
            <h5>选题桶</h5>
            ${renderTopicBuckets(result.topic_buckets)}
          </section>
        ` : ""}
        ${hasThinking ? `
          <section>
            <h5>思维模式</h5>
            ${renderThinkingPatternBlock(thinking)}
          </section>
        ` : ""}
        ${hasExpression ? `
          <section>
            <h5>表达 / 视觉依据</h5>
            ${renderExpressionPatternBlock(patterns, spec)}
          </section>
        ` : ""}
        ${reportValueHasAny(strategy.templates, result.transferable_formulas) ? `
          <section>
            <h5>原始公式字段</h5>
            ${renderDistillationFormulaList(strategy, result)}
          </section>
        ` : ""}
        ${reportValueHasAny(result.evidence_gaps) ? `
          <section>
            <h5>证据缺口</h5>
            ${renderPublicList(result.evidence_gaps)}
          </section>
        ` : ""}
        ${reportValueHasAny(viewModel?.technical_notes) ? `
          <section>
            <h5>运行备注</h5>
            ${renderPublicList(viewModel.technical_notes)}
          </section>
        ` : ""}
      </div>
    </details>
  `;
}

function renderCreatorDistillationReport(result, overview, templateLabel) {
  const viewModel = creatorReportViewModelFromResult(result, overview, templateLabel);
  const strategy = creatorStrategyFromResult(result) || {};
  const positioning = result.creator_positioning || {};
  const patterns = result.expression_patterns || {};
  const thinking = result.thinking_patterns || {};
  const spec = result.creator_clone_spec || {};
  const segments = result.performance_segments || {};
  const sections = viewModel.sections || {};
  const positioningText = viewModel.headline || strategy.positioning || positioning.what_the_creator_sells || result.summary || "待补充";
  const creatorLogic = normalizeItems(sections.core_judgment?.bullets).slice(0, 5);
  const repeatablePatterns = normalizeItems(sections.repeatable_patterns).slice(0, 6);
  const trafficHtml = `
    ${normalizeItems(sections.traffic_sources?.metric_signals).length ? `
      <h5>数据里最强的信号</h5>
      ${renderPublicList(sections.traffic_sources.metric_signals)}
    ` : ""}
    <h5>抓停留 / 促互动方式</h5>
    ${renderPublicList(sections.traffic_sources?.hooks, "暂无明确钩子。")}
  `;
  const actionHtml = `
    <h5>候选选题</h5>
    ${renderPublicList(sections.next_ideas, "本次没有返回独立选题库，可先基于爆款共性手动生成候选选题。")}
    <h5>下一步动作</h5>
    ${renderPublicList(sections.next_actions, "先从最高互动样本中选 3 条，人工复核开头、封面、动作和标题，再生成候选脚本。")}
  `;
  const checklistHtml = `
    <h5>发布前自检</h5>
    ${renderPublicList(sections.checklist, "暂无自检规则。")}
    <h5>不要照搬 / 风险边界</h5>
    ${renderPublicList(sections.anti_patterns, "暂无风险边界。")}
  `;
  return `
    <section class="creator-distillation-report" aria-label="创作者蒸馏核心报告">
      ${renderCreatorReportHero({
        viewModel,
        summary: viewModel.summary || result.summary,
        templateLabel,
        overview,
        positioningText,
      })}
      <div class="public-report-grid creator-distillation-grid creator-decision-grid">
        ${renderPublicCard("1. 核心判断：这个账号为什么能跑通", `
          ${renderPublicFields([
            ["定位", positioningText],
            ["观众承诺", positioning.audience_promise],
            ["隐藏类型", positioning.hidden_genre],
            ["观众假设", positioning.audience_assumption],
          ])}
          <h5>一句话创作逻辑</h5>
          ${renderPublicList(creatorLogic, "暂无核心逻辑。")}
        `, "featured wide")}
        ${renderPublicCard("2. 流量来源：用户为什么会停留、点赞、评论或转发", trafficHtml, "featured")}
        ${renderPublicCard("3. 可复刻创作公式：下一条照这个结构拍", `
          ${renderPublicList(sections.formulas, "本次没有返回独立公式，建议先从高互动样本中人工提炼 2-3 个可复用拍法。")}
          <h5>共性创作要素</h5>
          ${renderPublicList(repeatablePatterns, "暂无稳定共性。")}
        `, "featured")}
        ${renderPublicCard("4. 下一批可以怎么拍：选题与执行动作", actionHtml, "featured")}
        ${renderPublicCard("5. 发布前自检：保留有效结构，避开无效模仿", checklistHtml)}
      </div>
      ${renderCreatorDistillationEvidenceDetails(overview, result, viewModel)}
    </section>
  `;
}

function renderCreatorCloneEvidenceOverview(overview) {
  const counts = overview.understanding_counts || {};
  const warnings = normalizeItems(overview.warnings);
  return `
    <section class="creator-clone-evidence-strip" aria-label="创作者蒸馏证据完整度">
      <article>
        <span>选中样本</span>
        <strong>${formatNumber(overview.selected_count || 0)} / ${formatNumber(overview.sample_count || 0)}</strong>
      </article>
      <article>
        <span>完整证据</span>
        <strong>${formatNumber(counts.full || 0)}</strong>
      </article>
      <article>
        <span>部分证据</span>
        <strong>${formatNumber(counts.partial || 0)}</strong>
      </article>
      <article>
        <span>仅元数据</span>
        <strong>${formatNumber(counts.metadata_only || 0)}</strong>
      </article>
      <article class="wide">
        <span>可信度提示</span>
        <strong>${escapeHtml(overview.confidence || "unknown")}</strong>
        ${warnings.length ? `<p>${escapeHtml(warnings.join("；"))}</p>` : "<p>没有额外警告。</p>"}
      </article>
    </section>
  `;
}

function firstCloneValue(value, fallback = "待补充") {
  const values = normalizeItems(value);
  if (values.length) {
    return formatReportValue(values[0]) || fallback;
  }
  if (value && typeof value === "object") {
    return formatReportValue(value) || fallback;
  }
  return String(value || fallback);
}

function renderCreatorCloneActionSummary(result) {
  const strategy = creatorStrategyFromResult(result) || {};
  const positioning = result.creator_positioning || {};
  const formulas = normalizeItems(result.transferable_formulas);
  const ideas = normalizeItems(result.candidate_ideas);
  const templateValue = firstCloneValue(
    normalizeItems(strategy.templates).map((item) => item?.name || item?.title || item?.template || item),
    "",
  );
  const ideaValue = firstCloneValue(
    normalizeItems(strategy.idea_bank).map((item) => item?.title || item?.idea || item),
    firstCloneValue(ideas.map((item) => item?.title || item), ""),
  );
  const summaryCards = [
    ["核心定位", strategy.positioning || positioning.what_the_creator_sells || result.summary || "待补充"],
    ["内容策略", firstCloneValue(strategy.content_strategy || formulas.map((item) => item?.name || item), "待补充")],
    ["开头钩子", firstCloneValue(strategy.hooks || result.expression_patterns?.opening_hooks, "")],
    ["可复用模板", templateValue],
    ["优先选题", ideaValue],
  ].filter(([, value]) => publicValueHasContent(value));
  return `
    <section class="creator-clone-action-summary" aria-label="创作者蒸馏可执行摘要">
      <div class="section-heading-row compact-row">
        <div>
          <div class="entry-label">Action Summary</div>
          <h3>可执行摘要</h3>
        </div>
        <span class="status-badge muted-badge">用于选题 / 脚本 / 自检</span>
      </div>
      <div class="creator-clone-action-grid">
        ${summaryCards
          .map(([label, value]) => `
            <article>
              <span>${escapeHtml(label)}</span>
              <strong>${escapeHtml(value)}</strong>
            </article>
          `)
          .join("")}
      </div>
    </section>
  `;
}

function renderCreatorStrategyOutput(strategy = {}) {
  if (!strategy || typeof strategy !== "object") {
    return "";
  }
  const hasStrategy = [
    strategy.positioning,
    ...normalizeItems(strategy.content_strategy),
    ...normalizeItems(strategy.hooks),
    ...normalizeItems(strategy.templates),
    ...normalizeItems(strategy.anti_patterns),
    ...normalizeItems(strategy.idea_bank),
    ...normalizeItems(strategy.validation_rules),
  ].some((item) => item !== undefined && item !== null && item !== "");
  if (!hasStrategy) {
    return "";
  }
  const cards = [
    publicValueHasContent(strategy.positioning)
      ? renderPublicCard("策略定位", renderPublicFields([["Positioning", strategy.positioning]]), "featured")
      : "",
    publicValueHasContent(strategy.content_strategy)
      ? renderPublicCard("内容策略", renderPublicList(strategy.content_strategy), "featured")
      : "",
    publicValueHasContent(strategy.hooks)
      ? renderPublicCard("开头钩子", renderPublicList(strategy.hooks))
      : "",
    publicValueHasContent(strategy.templates)
      ? renderPublicCard("可复用模板", renderFormulaCards(strategy.templates), "featured")
      : "",
    publicValueHasContent(strategy.idea_bank)
      ? renderPublicCard("选题库", renderCandidateIdeas(strategy.idea_bank), "featured")
      : "",
  ].filter(Boolean).join("");
  if (!cards) {
    return "";
  }
  return `
    <div class="public-report-grid creator-strategy-grid" aria-label="Creator Intelligence Strategy Output">
      ${cards}
    </div>
  `;
}

function creatorCloneOverviewFromSet(set) {
  const samples = normalizeItems(set?.samples);
  const selectedIds = new Set(normalizeItems(set?.selected_sample_ids));
  const selected = selectedIds.size
    ? samples.filter((sample) => selectedIds.has(sample.sample_id) || selectedIds.has(sample.aweme_id) || selectedIds.has(sample.case_id))
    : samples.filter((sample) => sample.selected);
  const scopedSamples = selected.length ? selected : samples;
  const counts = scopedSamples.reduce(
    (acc, sample) => {
      const level = sample.understanding_level || "metadata_only";
      acc[level] = (acc[level] || 0) + 1;
      return acc;
    },
    {full: 0, partial: 0, metadata_only: 0},
  );
  const selectedCount = selected.length || Number(set?.selected_count || 0);
  const confidence = counts.full >= Math.max(1, Math.floor(scopedSamples.length / 2))
    ? "medium_high"
    : counts.full + counts.partial >= Math.max(1, Math.floor(scopedSamples.length / 2))
      ? "medium"
      : "low_metadata_only";
  return {
    sample_count: Number(set?.sample_count || samples.length || 0),
    selected_count: selectedCount,
    understanding_counts: counts,
    confidence,
    warnings: normalizeItems(set?.warnings),
  };
}

// Creator Clone: export
function renderCreatorCloneResult(result, set, prompt, exports = {}, options = {}) {
  currentCreatorRuntimeReport = result || null;
  currentDistillPrompt = prompt || currentDistillPrompt || "";
  setProfileStageView("export");
  creatorCloneResultCard.classList.remove("hidden");
  if (creatorCloneExportActions) {
    creatorCloneExportActions.open = true;
  }
  if (options.scroll !== false) {
    creatorCloneResultCard.scrollIntoView({behavior: "smooth", block: "start"});
  }
  const overview = result?.sample_overview || creatorCloneOverviewFromSet(set);
  creatorCloneConfidence.textContent = overview.confidence || (result ? "distilled" : "prompt only");
  if (downloadCreatorCloneJson && exports.creator_clone_result_json && set?.set_id) {
    downloadCreatorCloneJson.href = `/api/creator-clone/sets/${encodeURIComponent(set.set_id)}/files/creator_clone_result.json`;
  }
  if (downloadCreatorCloneMd && exports.creator_clone_md && set?.set_id) {
    downloadCreatorCloneMd.href = `/api/creator-clone/sets/${encodeURIComponent(set.set_id)}/files/creator_clone.md`;
  }
  if (!result) {
    creatorCloneResult.innerHTML = `
      <section class="public-analysis-hero">
        <span>LLM 未配置</span>
        <strong>已生成蒸馏 Prompt，可复制到外部大模型手动分析。</strong>
      </section>
      ${renderCreatorCloneEvidenceOverview(overview)}
      <pre class="prompt-preview">${escapeHtml(currentDistillPrompt.slice(0, 3000))}</pre>
    `;
    renderCreatorCloneNextAction();
    return;
  }
  const contentProfile = result.content_profile || overview.content_profile || {};
  const templateLabel = contentProfile.effective_label || contentProfile.requested_label || "自动判断";
  creatorCloneResult.innerHTML = `
    <section class="public-analysis-hero">
      <span>${escapeHtml(`样本 ${overview.selected_count || 0}/${overview.sample_count || 0} · ${overview.confidence || "unknown"} · ${templateLabel}`)}</span>
      <strong>${escapeHtml(result.summary || "创作者蒸馏完成。")}</strong>
    </section>
    ${renderCreatorDistillationReport(result, overview, templateLabel)}
  `;
  renderCreatorCloneNextAction();
}

function applyCreatorCloneDistillPayload(payload) {
  applyCreatorIntelligencePayload(payload);
  const batch = payload.batch_distill || {};
  const recoveryHint = payload.recovery === "prompt_only"
    ? (payload.error_code === "LLM_NOT_CONFIGURED"
      ? "大模型未配置，已生成蒸馏 Prompt，可复制后手动分析。"
      : `${payload.error_code || "LLM_FAILED"}：${payload.message || "大模型蒸馏失败"} 已保留素材池证据和蒸馏 Prompt，可稍后重试或手动分析。`)
    : batch.batch_count
      ? `分批蒸馏完成：${formatNumber(batch.batch_count)} 个批次，已生成总汇总。`
      : "创作者蒸馏完成。";
  profileScanStatus.textContent = recoveryHint;
  currentCloneSetId = payload.set?.set_id || currentCloneSetId;
  renderCreatorCloneResult(payload.result || null, payload.set, payload.prompt || "", payload.exports || {});
}

async function pollCreatorCloneDistillJob(jobId) {
  const response = await fetch(`/api/jobs/${jobId}`, {cache: "no-store"});
  const payload = await readJsonResponse(response);
  const job = payload.job;
  renderJobStatus(job);
  if (job.status === "success") {
    renderJobStatus(job);
    applyCreatorCloneDistillPayload(job.result_json || {});
    return;
  }
  if (job.status === "failed") {
    jobMessage.className = "job-message failed";
    jobMessage.textContent = `${job.error_code || "ERROR"}：${job.message || "蒸馏失败"}`;
    profileScanStatus.textContent = jobMessage.textContent;
    updateCreatorCloneSelectionStatus();
    return;
  }
  await new Promise((resolve) => {
    window.setTimeout(resolve, 900);
  });
  return pollCreatorCloneDistillJob(jobId);
}

// Creator Clone: distillation
async function distillSelectedCreatorClone(options = {}) {
  const shouldConfirmReadiness = options.confirmReadiness !== false;
  const selected = selectedCreatorSampleViewItems();
  if (!selected.length) {
    profileScanStatus.textContent = "请先选择要蒸馏的样本。";
    return;
  }
  if (selected.length > CREATOR_CLONE_MAX_DISTILL_SAMPLES) {
    profileScanStatus.textContent = `当前 MVP 最多选择 ${CREATOR_CLONE_MAX_DISTILL_SAMPLES} 条进行蒸馏，避免上下文过长。`;
    return;
  }
  if (shouldConfirmReadiness && !confirmProfileDistillReadiness(selected)) {
    profileScanStatus.textContent = "已取消蒸馏。建议先点击主按钮开始富化证据，补齐视频、关键帧、OCR、ASR 后再继续。";
    return;
  }
  setProfileStageView("distill", {scroll: true});
  if (options.triggeredByQueue) {
    profileScanStatus.textContent = selected.length < 2
      ? "样本富化完成；样本过少，正在生成临时蒸馏结果..."
      : "样本富化完成，正在调用大模型蒸馏创作者规则...";
  } else {
    profileScanStatus.textContent = selected.length < 2
      ? "样本过少，结果仅供参考。正在生成蒸馏 Prompt..."
      : "正在调用大模型蒸馏创作者规则...";
  }
  setCreatorCloneDistillButtonsLocked(true);
  renderCreatorCloneNextAction();
  try {
    const selectedIds = selected.map(sampleViewItemKey);
    await syncCreatorCloneWorkflowSelection();
    await markCreatorCloneDistillationStarted();
    placeJobCard("profile");
    resetJobCard("正在创建创作者蒸馏任务...");
    scrollProfileTaskPanel();
    const response = await fetch("/api/jobs/creator-clone-distill", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        sample_set_id: currentCloneSetId,
        samples: currentCloneSetId ? [] : activeCreatorSampleViewItems().map(creatorCloneSamplePayload),
        selected_sample_ids: selectedIds,
        distill_mode: "quick",
        include_case_reports: true,
        max_samples: CREATOR_CLONE_MAX_DISTILL_SAMPLES,
        title: "创作者蒸馏素材池",
        source_platform: "douyin",
        content_profile: profileContentProfile?.value || "auto",
      }),
    });
    const payload = await readJsonResponse(response);
    profileScanStatus.textContent = `已创建创作者蒸馏任务：${payload.selected_count || selected.length} 条样本。`;
    await pollCreatorCloneDistillJob(payload.job_id);
  } catch (error) {
    profileScanStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "蒸馏失败"}`;
    jobMessage.className = "job-message failed";
    jobMessage.textContent = profileScanStatus.textContent;
  } finally {
    setCreatorCloneDistillButtonsLocked(false);
    updateCreatorCloneSelectionStatus();
    renderCreatorCloneNextAction();
  }
}

async function batchDistillSelectedCreatorClone(options = {}) {
  const selected = selectedCreatorSampleViewItems();
  if (!selected.length) {
    profileScanStatus.textContent = "请先选择要分批蒸馏的样本。";
    return;
  }
  if (selected.length > PROFILE_BUILD_MAX_ITEMS) {
    profileScanStatus.textContent = `当前分批蒸馏最多支持 ${PROFILE_BUILD_MAX_ITEMS} 条样本。`;
    return;
  }
  const shouldContinue = options.confirm === false
    ? true
    : window.confirm(
      `将把 ${selected.length} 条样本按每 ${CREATOR_CLONE_MAX_DISTILL_SAMPLES} 条一批进行蒸馏，最后再汇总为账号级报告。这个过程可能会多次调用大模型并耗时较久。确认开始？`,
    );
  if (!shouldContinue) {
    profileScanStatus.textContent = "已取消分批蒸馏。";
    return;
  }
  const selectedIds = selected.map(sampleViewItemKey);
  setProfileStageView("distill", {scroll: true});
  setCreatorCloneDistillButtonsLocked(true);
  renderCreatorCloneNextAction();
  try {
    await syncCreatorCloneWorkflowSelection();
    await markCreatorCloneDistillationStarted();
    placeJobCard("profile");
    resetJobCard(options.triggeredByQueue ? "富化完成，正在创建分批蒸馏任务..." : "正在创建分批蒸馏任务...");
    scrollProfileTaskPanel();
    const response = await fetch("/api/jobs/creator-clone-batch-distill", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        sample_set_id: currentCloneSetId,
        samples: currentCloneSetId ? [] : activeCreatorSampleViewItems().map(creatorCloneSamplePayload),
        selected_sample_ids: selectedIds,
        distill_mode: "quick",
        batch_size: CREATOR_CLONE_MAX_DISTILL_SAMPLES,
        max_samples: PROFILE_BUILD_MAX_ITEMS,
        title: "创作者蒸馏素材池",
        source_platform: "douyin",
        content_profile: profileContentProfile?.value || "auto",
      }),
    });
    const payload = await readJsonResponse(response);
    profileScanStatus.textContent = `已创建分批蒸馏任务：${payload.selected_count || selected.length} 条样本，${payload.batch_count || 1} 个批次。`;
    await pollCreatorCloneDistillJob(payload.job_id);
  } catch (error) {
    profileScanStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "分批蒸馏失败"}`;
    jobMessage.className = "job-message failed";
    jobMessage.textContent = profileScanStatus.textContent;
  } finally {
    setCreatorCloneDistillButtonsLocked(false);
    updateCreatorCloneSelectionStatus();
    renderCreatorCloneNextAction();
  }
}

async function loadLlmStatus() {
  try {
    const response = await fetch("/api/settings/llm", {cache: "no-store"});
    const payload = await readJsonResponse(response);
    renderLlmStatus(payload.llm || {});
  } catch (error) {
    llmStatusBadge.textContent = "读取失败";
    llmStatusList.textContent = `${error.error_code || "ERROR"}：${error.message || "无法读取 AI 配置"}`;
    testLlmButton.disabled = true;
  }
}

function renderPreflightStatus(preflight) {
  if (!preflightSummary || !preflightList) {
    return;
  }
  const summary = preflight.summary || {};
  preflightCopySnippets = [];
  preflightSummary.textContent = `就绪 ${summary.ready_count || 0}/${summary.total_count || 0}，缺失 ${summary.missing_count || 0}，关闭 ${summary.disabled_count || 0}。`;
  preflightList.innerHTML = normalizeItems(preflight.checks)
    .map((item) => {
      const status = item.status || "unknown";
      const statusLabel = {ready: "可用", partial: "待打开", missing: "缺失", disabled: "关闭"}[status] || status;
      const snippet = String(item.env_snippet || "");
      const snippetIndex = snippet ? preflightCopySnippets.push(snippet) - 1 : -1;
      return `
        <article class="preflight-item">
          <strong>
            ${escapeHtml(item.label || item.id || "检查项")}
            <span class="preflight-status ${escapeHtml(status)}">${escapeHtml(statusLabel)}</span>
          </strong>
          <p>${escapeHtml(item.message || "")}</p>
          ${normalizeItems(item.contract_summary).length ? `<ul class="preflight-contract-summary">${normalizeItems(item.contract_summary).map((value) => `<li>${escapeHtml(value)}</li>`).join("")}</ul>` : ""}
          ${item.action_hint ? `<p class="preflight-action">${escapeHtml(item.action_hint)}</p>` : ""}
          ${snippet ? `
            <div class="preflight-command-row">
              <pre class="preflight-env-snippet">${escapeHtml(snippet)}</pre>
              <button type="button" class="text-button preflight-copy-button" data-preflight-copy-index="${snippetIndex}">复制命令</button>
            </div>
          ` : ""}
        </article>
      `;
    })
    .join("");
}

async function loadPreflightStatus() {
  if (preflightSummary) {
    preflightSummary.textContent = "正在检查本地工具...";
  }
  const response = await fetch("/api/settings/preflight", {cache: "no-store"});
  const payload = await readJsonResponse(response);
  renderPreflightStatus(payload.preflight || {});
  return payload;
}

function renderDataSourceStatus(status = {}) {
  if (!dataSourceStatusBadge || !dataSourceStatusList) {
    return;
  }
  dataSourceStatusBadge.textContent = status.configured ? "增强已配置" : "主路径可用";
  dataSourceStatusBadge.className = `status-badge ${status.configured ? "success" : "muted-badge"}`;
  const sources = normalizeItems(status.sources);
  dataSourceStatusList.innerHTML = `
    <dl>
      <dt>Cookie API</dt><dd>${status.has_cookie ? "已配置" : "未配置"}</dd>
      <dt>User-Agent</dt><dd>${status.user_agent_configured ? "已配置" : "未配置"}</dd>
      <dt>Referer</dt><dd>${escapeHtml(status.referer || "https://www.douyin.com/")}</dd>
      ${renderDouyinCookieDiagnosticsRows(status.cookie_diagnostics || {})}
      <dt>当前策略</dt><dd>${escapeHtml(status.status_message || "")}</dd>
    </dl>
    <ul class="preflight-contract-summary">
      ${sources.map((source) => `<li><strong>${escapeHtml(source.label || source.id)}</strong>：${escapeHtml(source.message || "")}</li>`).join("")}
    </ul>
  `;
  if (douyinCookieInput) {
    douyinCookieInput.value = "";
    douyinCookieInput.placeholder = status.has_cookie ? `留空保留当前 Cookie（${status.masked_cookie || "已配置"}）` : "粘贴 Douyin Cookie";
  }
  if (douyinUserAgentInput) {
    douyinUserAgentInput.value = status.user_agent || "";
  }
  if (douyinRefererInput) {
    douyinRefererInput.value = status.referer || "https://www.douyin.com/";
  }
  if (douyinClearCookieInput) {
    douyinClearCookieInput.checked = false;
  }
}

function renderDouyinCookieDiagnosticsRows(diagnostics = {}) {
  if (!diagnostics.has_cookie) {
    return "";
  }
  const important = normalizeItems(diagnostics.present_important_keys).join(" / ") || "未检测到";
  const missing = normalizeItems(diagnostics.missing_login_keys).join(" / ") || "无";
  return `
    <dt>Cookie 字段</dt><dd>${formatNumber(diagnostics.pair_count || 0)} 个；登录态字段 ${formatNumber(diagnostics.login_key_count || 0)} 个</dd>
    <dt>关键字段</dt><dd>${escapeHtml(important)}</dd>
    <dt>缺失登录字段</dt><dd>${escapeHtml(missing)}</dd>
  `;
}

function creatorCloneCurrentProfileValue() {
  const quick = creatorCloneUnifiedInputValue();
  if (quick) {
    return firstUrlFromText(quick) || quick;
  }
  if (!profileForm) {
    return "";
  }
  const formData = new FormData(profileForm);
  return String(formData.get("profile_url") || "").trim();
}

function renderDouyinCookieTestResult(test = {}) {
  if (!douyinCookieTestResult) {
    return;
  }
  const diagnostics = test.cookie_diagnostics || {};
  const statusClass = test.status === "ok" ? "success" : ["config_only", "not_configured"].includes(test.status) ? "muted-badge" : "warning";
  const rows = [
    ["自检状态", test.status || ""],
    ["Cookie 结构", diagnostics.has_cookie ? `${formatNumber(diagnostics.pair_count || 0)} 个字段，${formatNumber(diagnostics.login_key_count || 0)} 个登录态字段` : "未配置"],
    ["关键字段", normalizeItems(diagnostics.present_important_keys).join(" / ") || "未检测到"],
    ["API 请求", test.api_checked ? `已请求，HTTP ${test.status_code || "未知"}` : "未请求"],
    ["返回类型", test.api_checked ? `${test.is_json ? "JSON" : "非 JSON"}${test.content_type ? ` · ${test.content_type}` : ""}` : "未检测"],
    ["返回作品", test.api_checked ? `${formatNumber(test.aweme_count || 0)} 条` : "未检测"],
    ["接口消息", test.api_status_msg || ""],
  ].filter(([, value]) => value !== "");
  const nextSteps = normalizeItems(test.safe_next_steps);
  const endpointResults = normalizeItems(test.endpoint_results);
  douyinCookieTestResult.className = `settings-test-result ${statusClass}`;
  douyinCookieTestResult.innerHTML = `
    <strong>${escapeHtml(test.message || "Cookie API 自检完成。")}</strong>
    <dl>
      ${rows.map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd>`).join("")}
    </dl>
    ${endpointResults.length ? `
      <div class="endpoint-test-list">
        <strong>候选接口</strong>
        ${endpointResults.map((item) => `
          <span>${escapeHtml(item.endpoint || "")} · ${escapeHtml(item.status || "")}${item.status_code ? ` · HTTP ${escapeHtml(String(item.status_code))}` : ""}${item.aweme_count ? ` · ${formatNumber(item.aweme_count)} 条` : ""}</span>
        `).join("")}
      </div>
    ` : ""}
    ${nextSteps.length ? `<ul>${nextSteps.map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ul>` : ""}
  `;
}

async function loadDataSourceStatus() {
  if (dataSourceStatusList) {
    dataSourceStatusList.textContent = "正在读取数据源设置...";
  }
  try {
    const response = await fetch("/api/settings/data-sources", {cache: "no-store"});
    const payload = await readJsonResponse(response);
    renderDataSourceStatus(payload.data_sources || {});
  } catch (error) {
    if (dataSourceStatusBadge) {
      dataSourceStatusBadge.textContent = "读取失败";
    }
    if (dataSourceStatusList) {
      dataSourceStatusList.textContent = `${error.error_code || "ERROR"}：${error.message || "无法读取数据源设置"}`;
    }
  }
}

function buildFullPrompt(data) {
  const analysisInput = JSON.stringify(data.analysis_input || {}, null, 2);
  return `${data.prompt || ""}\n\n## 附：analysis_input.json\n\n\`\`\`json\n${analysisInput}\n\`\`\``;
}

function renderWorkflowResult(result) {
  const caseInfo = result.case || {};
  const caseId = result.case_id || caseInfo.case_id || "";
  const rows = [
    ["素材包 ID", caseId || ""],
    ["素材包状态", "已生成"],
    ["AI 自动拆解", result.analysis_status === "success" ? "已生成" : "未配置或未完成，可在 case 详情页重试"],
  ].filter(([, value]) => value);

  caseSummary.innerHTML = `
    <div class="case-status">素材包已生成</div>
    <dl>
      ${rows.map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`).join("")}
    </dl>
  `;
  uploadResult.classList.add("hidden");
  uploadResult.textContent = JSON.stringify(result, null, 2);
}

function getCaseId(result) {
  const caseInfo = result.case || {};
  return result.case_id || caseInfo.case_id || "";
}

async function loadCasePayload(caseId) {
  const response = await fetch(`/api/cases/${caseId}`, {cache: "no-store"});
  const payload = await readJsonResponse(response);
  return payload.case;
}

function renderHomeCase(data) {
  loadedHomeCase = data;
  const metadata = data.metadata || {};
  const analysisInput = data.analysis_input || {};
  const stats = analysisInput.stats || {};
  const report = data.analysis_report || "";
  const analysisResult = data.analysis_result || null;
  const analysisJob = data.analysis_job || {};
  const caseUrl = `/cases/${data.case_id}`;

  homeCaseView.classList.remove("hidden");
  homeContactSheet.src = `${data.artifact_urls.contact_sheet}?v=${Date.now()}`;
  openFullCaseLink.href = caseUrl;
  renderDefinitionList(homeCaseMeta, [
    ["标题", metadata.title],
    ["作者", metadata.author],
    ["点赞", formatNumber(stats.like_count)],
    ["评论", formatNumber(stats.comment_count)],
    ["分享", formatNumber(stats.share_count)],
  ]);

  if (analysisResult) {
    homeAiStatus.textContent = "AI 自动拆解已生成。";
    homeAiReport.innerHTML = renderPublicAnalysisReport(analysisResult);
  } else if (analysisJob.status === "failed") {
    const error = analysisJob.error || {};
    homeAiStatus.textContent = `${error.error_code || "AI_FAILED"}：${error.message || "AI 自动拆解失败，可更换模型后重新解析或打开完整 case 重试。"}`;
    homeAiReport.innerHTML = "";
  } else if (analysisJob.status === "skipped") {
    homeAiStatus.textContent = "视频已准备好，但 AI 自动拆解未配置。配置模型后可重新解析。";
    homeAiReport.innerHTML = "";
  } else if (analysisJob.status === "pending" || analysisJob.status === "running") {
    homeAiStatus.textContent = "视频已准备好，AI 正在拆解。拆解完成后会在这里显示结果。";
    homeAiReport.innerHTML = "";
  } else {
    homeAiStatus.textContent = "视频已准备好。AI 摘要将在拆解完成后显示。";
    homeAiReport.innerHTML = "";
  }
}

async function showAnalysisInline(result, options = {}) {
  const caseId = getCaseId(result);
  if (!caseId) {
    return false;
  }
  if (options.updateMessage !== false) {
    jobMessage.textContent = "素材包已生成，正在加载首页分析视图...";
  }
  const caseData = await loadCasePayload(caseId);
  if (result.analysis_status) {
    caseData.analysis_job = {
      status: result.analysis_status,
      error: result.analysis_error || {},
    };
  }
  if (result.analysis && result.analysis.analysis_result) {
    caseData.analysis_result = result.analysis.analysis_result;
  }
  if (result.analysis && result.analysis.analysis_report) {
    caseData.analysis_report = result.analysis.analysis_report;
  }
  renderHomeCase(caseData);
  if (options.scroll !== false) {
    resultCard.scrollIntoView({behavior: "smooth", block: "start"});
  }
  return true;
}

async function readJsonResponse(response) {
  const payload = await response.json().catch(() => ({
    ok: false,
    error_code: "INVALID_RESPONSE",
    message: "接口返回不是 JSON。",
  }));
  if (!response.ok || payload.ok === false) {
    throw payload;
  }
  return payload;
}

settingsToggle.addEventListener("click", () => {
  settingsModal.classList.remove("hidden");
  loadPreflightStatus().catch(() => {
    if (preflightSummary) {
      preflightSummary.textContent = "本地工具预检失败，请查看后端日志。";
    }
  });
});

settingsClose.addEventListener("click", () => {
  settingsModal.classList.add("hidden");
});

settingsModal.addEventListener("click", (event) => {
  if (event.target === settingsModal) {
    settingsModal.classList.add("hidden");
  }
});

homeRouteButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setHomeRoute(button.dataset.homeRoute);
  });
});

window.addEventListener("hashchange", () => {
  setHomeRoute(routeFromHash(), false);
});

llmSettingsForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  saveLlmSettingsButton.disabled = true;
  llmSaveResult.textContent = "正在保存...";
  try {
    const payload = {
      provider: llmProviderInput?.value || "disabled",
      api_base: llmApiBaseInput?.value || "",
      model: llmModelInput?.value || "",
      timeout_seconds: Number(llmTimeoutInput?.value || 90),
      temperature: Number(llmTemperatureInput?.value || 0.2),
      clear_api_key: Boolean(llmClearKeyInput?.checked),
    };
    const apiKey = String(llmApiKeyInput?.value || "").trim();
    if (apiKey) {
      payload.api_key = apiKey;
    }
    const response = await fetch("/api/settings/llm", {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    const result = await readJsonResponse(response);
    renderLlmStatus(result.llm || {});
    llmSaveResult.textContent = "已保存到本机运行时配置。";
    await loadPreflightStatus().catch(() => {});
  } catch (error) {
    llmSaveResult.textContent = `${error.error_code || "ERROR"}：${error.message || "保存失败"}`;
  } finally {
    saveLlmSettingsButton.disabled = false;
  }
});

douyinSettingsForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  saveDouyinSettingsButton.disabled = true;
  douyinSaveResult.textContent = "正在保存...";
  try {
    const payload = {
      user_agent: douyinUserAgentInput?.value || "",
      referer: douyinRefererInput?.value || "https://www.douyin.com/",
      clear_cookie: Boolean(douyinClearCookieInput?.checked),
    };
    const cookie = String(douyinCookieInput?.value || "").trim();
    if (cookie) {
      payload.douyin_cookie = cookie;
    }
    const response = await fetch("/api/settings/data-sources/douyin", {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    const result = await readJsonResponse(response);
    renderDataSourceStatus(result.data_sources || {});
    douyinSaveResult.textContent = "已保存到本机运行时配置。";
  } catch (error) {
    douyinSaveResult.textContent = `${error.error_code || "ERROR"}：${error.message || "保存失败"}`;
  } finally {
    saveDouyinSettingsButton.disabled = false;
  }
});

testDouyinCookieButton?.addEventListener("click", async () => {
  testDouyinCookieButton.disabled = true;
  if (douyinCookieTestResult) {
    douyinCookieTestResult.textContent = "正在自检 Cookie 结构和 Cookie API...";
  }
  try {
    const profileValue = creatorCloneCurrentProfileValue();
    const payload = {
      profile_url: firstUrlFromText(profileValue) || profileValue,
      count: 5,
    };
    const response = await fetch("/api/settings/data-sources/douyin/test", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    const result = await readJsonResponse(response);
    renderDouyinCookieTestResult(result.test || {});
    await loadDataSourceStatus();
  } catch (error) {
    if (douyinCookieTestResult) {
      douyinCookieTestResult.textContent = `${error.error_code || "ERROR"}：${error.message || "Cookie API 自检失败"}`;
    }
  } finally {
    testDouyinCookieButton.disabled = false;
  }
});

testLlmButton.addEventListener("click", async () => {
  testLlmButton.disabled = true;
  llmTestResult.textContent = "正在测试...";
  try {
    const response = await fetch("/api/settings/llm/test", {method: "POST"});
    const payload = await readJsonResponse(response);
    llmTestResult.textContent = `测试通过：${payload.test?.message || "pong"}`;
  } catch (error) {
    llmTestResult.textContent = `${error.error_code || "ERROR"}：${error.message || "测试失败"}`;
  } finally {
    await loadLlmStatus();
  }
});

refreshPreflightButton?.addEventListener("click", async () => {
  refreshPreflightButton.disabled = true;
  try {
    await loadPreflightStatus();
  } catch (error) {
    preflightSummary.textContent = `${error.error_code || "ERROR"}：${error.message || "本地工具预检失败"}`;
  } finally {
    refreshPreflightButton.disabled = false;
  }
});

preflightList?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-preflight-copy-index]");
  if (!button) {
    return;
  }
  const index = Number(button.dataset.preflightCopyIndex);
  const snippet = Number.isInteger(index) ? preflightCopySnippets[index] : "";
  const originalText = button.textContent;
  try {
    const copied = await copyTextToClipboard(snippet);
    button.textContent = copied ? "已复制" : "复制失败";
  } catch (error) {
    button.textContent = "复制失败";
  } finally {
    window.setTimeout(() => {
      button.textContent = originalText;
    }, 1600);
  }
});

// Single Work
async function runSingleValue(value) {
  singleButton.disabled = true;
  singleButton.textContent = "解析中...";
  selectedCandidate = null;
  currentLocalVideoId = "";
  homeCaseView.classList.add("hidden");
  resultCard.classList.add("hidden");
  setStatus(parseStatus, "解析中");
  setStatus(downloadStatus, "未开始");
  setStatus(packageStatus, "未生成");
  setStatus(analysisStatus, "未运行");
  try {
    const importResponse = await fetch("/api/videos/import-single", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({value}),
    });
    const imported = await readJsonResponse(importResponse);
    currentAwemeId = imported.video.aweme_id;
    singleResult.classList.remove("hidden");
    singleResult.textContent = `已导入作品：${currentAwemeId}，正在解析可用清晰度...`;
    await resolveQualities([currentAwemeId]);
    if (selectedCandidate) {
      await downloadCandidate(selectedCandidate);
    }
  } catch (error) {
    singleResult.classList.remove("hidden");
    singleResult.textContent = `${error.error_code || "ERROR"}：${error.message || "导入失败"}`;
    setStatus(parseStatus, "失败");
    singleButton.disabled = false;
    singleButton.textContent = "解析";
  } finally {
    if (!selectedCandidate) {
      singleButton.disabled = false;
      singleButton.textContent = "解析";
    }
  }
}

singleForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const value = new FormData(singleForm).get("value");
  await runSingleValue(value);
});

profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await scanProfile(event.submitter?.dataset.profileSource || "public");
});

profileHandoffFile?.addEventListener("change", async () => {
  await readHandoffManifestFile(profileHandoffFile.files?.[0]);
});

profileImportModeButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setActiveImportMode(button.dataset.profileImportMode || "browser");
  });
});

creatorCloneFlowSteps.forEach((button) => {
  button.addEventListener("click", () => {
    const targetStage = normalizeProfileStage(button.dataset.profileStageNav || "import");
    if (!canNavigateProfileStage(targetStage)) {
      profileScanStatus.textContent = creatorCloneEnrichmentRunning
        ? "证据富化正在运行，完成后会自动进入大模型蒸馏；当前先保持队列视图。"
        : "大模型蒸馏正在运行，完成后会自动进入报告页；当前先保持任务视图。";
      renderCreatorCloneNextAction();
      return;
    }
    setProfileStageView(targetStage, {scroll: true});
    renderCreatorCloneNextAction();
  });
});

profileQuickInput?.addEventListener("input", () => {
  profileQuickInputRestoredValue = "";
  renderCreatorCloneNextAction();
});

creatorCloneNextButton?.addEventListener("click", async () => {
  if (creatorCloneNextActionRunning) {
    return;
  }
  creatorCloneNextActionRunning = true;
  renderWizardPrimaryAction();
  try {
    await runCreatorCloneNextAction();
  } finally {
    creatorCloneNextActionRunning = false;
    renderCreatorCloneNextAction();
  }
});

profileBrowserHelperButton.addEventListener("click", async () => {
  await scanProfileWithLocalChrome();
});

profileSort.addEventListener("change", () => {
  if (profileScanPayload) {
    renderProfileTable();
    updateCreatorCloneSelectionStatus();
  }
});

profileEvidenceFilter?.addEventListener("change", () => {
  if (profileScanPayload) {
    renderProfileTable();
    updateCreatorCloneSelectionStatus();
  }
});

profileMediaFilter?.addEventListener("change", () => {
  if (profileScanPayload) {
    renderProfileTable();
    updateCreatorCloneSelectionStatus();
  }
});

profileResultsBody.addEventListener("change", (event) => {
  if (event.target.matches("[data-profile-select]")) {
    if (event.target.checked) {
      profileSelectedKeys.add(event.target.value);
    } else {
      profileSelectedKeys.delete(event.target.value);
    }
    invalidateCreatorRuntimeReportForSelectionChange();
    updateCreatorCloneSelectionStatus();
    scheduleCreatorCloneSelectionSync();
  }
});

profileResultsBody.addEventListener("click", (event) => {
  const button = event.target.closest("[data-profile-select-action]");
  if (!button) {
    return;
  }
  const key = button.dataset.profileSelectAction || "";
  if (!key) {
    return;
  }
  profileSelectedKeys.add(key);
  invalidateCreatorRuntimeReportForSelectionChange();
  document.querySelectorAll("[data-profile-select]").forEach((input) => {
    if (input.value === key) {
      input.checked = true;
    }
  });
  updateCreatorCloneSelectionStatus();
  scheduleCreatorCloneSelectionSync();
  profileScanStatus.textContent = "已选入本轮样本。";
});

profileSelectAllButton.addEventListener("click", () => {
  const items = visibleCreatorSampleViewItems();
  setProfileSelection(items);
  profileScanStatus.textContent = `已全选当前列表：${items.length} 条。蒸馏最多支持 ${CREATOR_CLONE_MAX_DISTILL_SAMPLES} 条。`;
});

profileClearSelectionButton.addEventListener("click", () => {
  setProfileSelection([]);
  if (profilePresetKind) {
    profilePresetKind.value = "";
  }
  profileScanStatus.textContent = "已取消选择。";
});

function applyProfilePresetSelectValue() {
  const preset = profilePresetKind?.value || "";
  if (!preset) {
    return;
  }
  applyProfilePresetSelection(preset);
}

profilePresetKind?.addEventListener("change", applyProfilePresetSelectValue);

profileDecisionBoard?.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target : event.target?.parentElement;
  const stageButton = target?.closest("[data-profile-stage-go]");
  if (stageButton) {
    setProfileStageView(stageButton.dataset.profileStageGo || "select", {scroll: true});
  }
});

profileContinueChromeButton?.addEventListener("click", async () => {
  await scanProfileWithLocalChrome({continueScan: true});
});

profileSelectedBuildButton.addEventListener("click", async () => {
  await buildSelectedProfileQueue();
});

creatorCloneDistillButton.addEventListener("click", async () => {
  await distillSelectedCreatorClone();
});

creatorCloneBatchDistillButton?.addEventListener("click", async () => {
  await batchDistillSelectedCreatorClone();
});

copyCreatorCloneSpecButton.addEventListener("click", async () => {
  const strategy = creatorStrategyFromResult(currentCreatorRuntimeReport || {}) || null;
  const payload = strategy || currentCreatorRuntimeReport?.creator_clone_spec || null;
  if (!payload) {
    return;
  }
  await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
  copyCreatorCloneSpecButton.textContent = "已复制";
  window.setTimeout(() => {
    copyCreatorCloneSpecButton.textContent = "复制 Creator Clone Spec";
  }, 1600);
});

copyDistillPromptButton.addEventListener("click", async () => {
  if (!currentDistillPrompt) {
    return;
  }
  await navigator.clipboard.writeText(currentDistillPrompt);
  copyDistillPromptButton.textContent = "已复制";
  window.setTimeout(() => {
    copyDistillPromptButton.textContent = "复制蒸馏 Prompt";
  }, 1600);
});

async function resolveQualities(awemeIds) {
  const response = await fetch("/api/videos/qualities", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({aweme_ids: awemeIds}),
  });
  const payload = await readJsonResponse(response);
  const candidates = payload.results[currentAwemeId] || [];
  if (!candidates.length) {
    singleResult.textContent = "没有解析到可用清晰度候选。";
    setStatus(parseStatus, "未解析到候选");
    return;
  }
  selectedCandidate = chooseCandidate(candidates);
  const sizeMb = selectedCandidate.size_bytes
    ? (selectedCandidate.size_bytes / 1024 / 1024).toFixed(2)
    : "未知";
  const bitrate = selectedCandidate.bitrate
    ? `${Math.round(selectedCandidate.bitrate / 1000)} kbps`
    : "未知码率";
  singleResult.textContent = `已按设置选择：${selectedCandidate.quality_label || "网页候选"} · ${sizeMb} MB · ${bitrate}`;
  setStatus(parseStatus, "已解析");
}

function chooseCandidate(candidates) {
  const preference = qualityPreference?.value || "1080";
  if (preference === "1080") {
    return candidates.find((candidate) => String(candidate.quality_label || "").includes("1080")) || candidates[0];
  }
  if (preference === "720") {
    return candidates.find((candidate) => String(candidate.quality_label || "").includes("720")) || candidates[0];
  }
  return candidates[0];
}

async function downloadCandidate(candidate) {
  let inlineCaseShown = false;
  setHomeRoute("single");
  placeJobCard("single");
  resetJobCard("创建下载和素材包任务...");
  setStatus(downloadStatus, "等待任务");
  setStatus(packageStatus, "等待生成");
  setStatus(analysisStatus, "等待自动拆解");
  caseSummary.innerHTML = "";
  resultCard.classList.add("hidden");
  buildCaseButton.hidden = true;
  try {
    const response = await fetch("/api/jobs/download-build-analyze-case", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({aweme_id: currentAwemeId, candidate_id: candidate.candidate_id}),
    });
    const payload = await readJsonResponse(response);
    const renderIntermediateCase = async (job, {scroll = false} = {}) => {
      const result = job.result_json || {};
      const caseId = getCaseId(result);
      if (!caseId || inlineCaseShown) {
        return;
      }
      currentLocalVideoId = result.local_video_id || currentLocalVideoId;
      resultCard.classList.remove("hidden");
      buildCaseButton.hidden = true;
      renderWorkflowResult(result);
      setStatus(downloadStatus, "完成");
      setStatus(packageStatus, "已生成");
      setStatus(analysisStatus, job.status === "success" ? "完成" : "AI 自动拆解中，本地拆解已可查看");
      try {
        await showAnalysisInline(result, {scroll, updateMessage: false});
        inlineCaseShown = true;
      } catch (error) {
        homeAiStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "本地拆解视图加载失败，任务仍在继续"}`;
      }
    };
    return pollJob(payload.job_id, async (job) => {
      if (job.status === "success" && job.result_json.local_video_id) {
        currentLocalVideoId = job.result_json.local_video_id;
        resultCard.classList.remove("hidden");
        buildCaseButton.hidden = true;
        renderWorkflowResult(job.result_json);
        setStatus(downloadStatus, "完成");
        setStatus(packageStatus, "已生成");
        setStatus(
          analysisStatus,
          {
            success: "已生成",
            failed: "失败，可更换模型后重试",
            skipped: "未配置",
            pending: "未完成",
          }[job.result_json.analysis_status] || "未完成",
        );
        if (await showAnalysisInline(job.result_json, {scroll: !inlineCaseShown, updateMessage: false})) {
          jobMessage.textContent = `success · 100% · ${job.message || "任务完成"}`;
          return;
        }
      }
    }, async (job) => {
      await renderIntermediateCase(job, {scroll: true});
    });
  } catch (error) {
    jobMessage.className = "job-message failed";
    jobMessage.textContent = `${error.error_code || "ERROR"}：${error.message || "任务创建失败"}`;
    setStatus(downloadStatus, "失败");
    singleButton.disabled = false;
    singleButton.textContent = "解析";
  }
}

buildCaseButton.addEventListener("click", async () => {
  if (!currentLocalVideoId) {
    return;
  }
  buildCaseButton.disabled = true;
  placeJobCard("single");
  resetJobCard("创建任务...");
  try {
    const response = await fetch("/api/jobs/build-case", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({local_video_id: currentLocalVideoId}),
    });
    const payload = await readJsonResponse(response);
    pollJob(payload.job_id);
  } catch (error) {
    jobMessage.className = "job-message failed";
    jobMessage.textContent = `${error.error_code || "ERROR"}：${error.message || "任务创建失败"}`;
    buildCaseButton.disabled = false;
  }
});

async function pollJob(jobId, onSuccess, onProgress) {
  try {
    const response = await fetch(`/api/jobs/${jobId}`, {cache: "no-store"});
    const payload = await readJsonResponse(response);
    const job = payload.job;
    renderJobStatus(job);
    if (job.status === "success") {
      renderJobStatus(job);
      if (onSuccess) {
        await onSuccess(job);
      } else if (jobResult) {
        showJson(jobResult, job.result_json);
      }
      buildCaseButton.disabled = false;
      singleButton.disabled = false;
      singleButton.textContent = "解析";
      return;
    }
    if (job.status === "failed") {
      jobMessage.className = "job-message failed";
      jobMessage.textContent = `${job.error_code || "ERROR"}：${job.message || "任务失败"}`;
      if (jobResult) {
        showJson(jobResult, job);
      }
      setStatus(downloadStatus, "失败");
      buildCaseButton.disabled = false;
      singleButton.disabled = false;
      singleButton.textContent = "解析";
      return;
    }
    if (onProgress) {
      await onProgress(job);
    }
    await new Promise((resolve) => {
      window.setTimeout(resolve, 700);
    });
    return pollJob(jobId, onSuccess, onProgress);
  } catch (error) {
    jobMessage.className = "job-message failed";
    jobMessage.textContent = `${error.error_code || "ERROR"}：${error.message || "查询任务失败"}`;
    buildCaseButton.disabled = false;
    singleButton.disabled = false;
    singleButton.textContent = "解析";
  }
}

copyHomePromptButton.addEventListener("click", async () => {
  if (!loadedHomeCase) {
    return;
  }
  await navigator.clipboard.writeText(buildFullPrompt(loadedHomeCase));
  copyHomePromptButton.textContent = "已复制";
  window.setTimeout(() => {
    copyHomePromptButton.textContent = "复制 Prompt";
  }, 1600);
});

downloadHomeAnalysisInputButton.addEventListener("click", () => {
  const url = loadedHomeCase?.artifact_urls?.analysis_input;
  if (url) {
    window.open(url, "_blank", "noopener,noreferrer");
  }
});

loadLlmStatus();
loadDataSourceStatus();
loadPreflightStatus().catch(() => {});
renderCreatorCloneNextAction();
setHomeRoute(routeFromHash(), false);
