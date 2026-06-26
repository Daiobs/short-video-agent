const settingsToggle = document.getElementById("settings-toggle");
const settingsDrawer = document.getElementById("settings-drawer");
const settingsClose = document.getElementById("settings-close");
const singleForm = document.getElementById("single-form");
const singleButton = document.getElementById("single-button");
const downloadSelectedButton = document.getElementById("download-selected-button");
const singleResult = document.getElementById("single-result");
const qualityPreference = document.getElementById("quality-preference");
const parseStatus = document.getElementById("parse-status");
const downloadStatus = document.getElementById("download-status");
const packageStatus = document.getElementById("package-status");
const analysisStatus = document.getElementById("analysis-status");
const llmStatusBadge = document.getElementById("llm-status-badge");
const llmStatusList = document.getElementById("llm-status-list");
const llmConfigHint = document.getElementById("llm-config-hint");
const testLlmButton = document.getElementById("test-llm-button");
const llmTestResult = document.getElementById("llm-test-result");
const resultCard = document.getElementById("result-card");
const recentEmptyState = document.getElementById("recent-empty-state");
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
const jobResult = document.getElementById("job-result");
const homeRouteButtons = Array.from(document.querySelectorAll("[data-home-route]"));
const homePanels = Array.from(document.querySelectorAll("[data-home-panel]"));

let currentLocalVideoId = "";
let currentAwemeId = "";
let selectedCandidate = null;
let loadedHomeCase = null;

function setStatus(element, value) {
  if (element) {
    element.textContent = value;
  }
}

function setHomeRoute(route, updateHash = true) {
  const activeRoute = ["single", "profile", "cases", "settings"].includes(route) ? route : "single";
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
}

function routeFromHash() {
  return window.location.hash.replace("#", "") || "single";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
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
    ["AI 自动拆解", result.analysis_status === "success" ? "已生成" : "未运行，可在 case 详情页启动"],
  ].filter(([, value]) => value);

  caseSummary.innerHTML = `
    <div class="case-status">素材包已生成</div>
    <dl>
      ${rows.map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`).join("")}
    </dl>
  `;
  recentEmptyState.classList.add("hidden");
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
  const video = analysisInput.video || {};
  const ffprobe = data.ffprobe || {};
  const report = data.analysis_report || "";
  const caseUrl = `/cases/${data.case_id}`;

  homeCaseView.classList.remove("hidden");
  homeContactSheet.src = `${data.artifact_urls.contact_sheet}?v=${Date.now()}`;
  openFullCaseLink.href = caseUrl;
  renderDefinitionList(homeCaseMeta, [
    ["作品 ID", metadata.aweme_id || analysisInput.aweme_id],
    ["标题", metadata.title],
    ["作者", metadata.author],
    ["点赞", formatNumber(stats.like_count)],
    ["评论", formatNumber(stats.comment_count)],
    ["分享", formatNumber(stats.share_count)],
    ["互动分", formatNumber(stats.engagement_score)],
    ["时长", formatSeconds(video.duration || ffprobe.duration)],
    ["分辨率", `${video.width || ffprobe.width || 0}x${video.height || ffprobe.height || 0}`],
    ["文件大小", formatBytes(video.file_size || ffprobe.file_size)],
  ]);

  if (data.analysis_result) {
    homeAiStatus.textContent = "AI 自动拆解已生成。可以在完整分析页继续修改类型、工作表或重新分析。";
    homeAiReport.textContent = report || JSON.stringify(data.analysis_result, null, 2);
  } else {
    homeAiStatus.textContent = "素材包已生成，但 AI 自动拆解未运行。可以打开完整分析页手动启动，或复制 Prompt 手动分析。";
    homeAiReport.textContent = "";
  }
}

async function showAnalysisInline(result) {
  const caseId = getCaseId(result);
  if (!caseId) {
    return false;
  }
  jobMessage.textContent = "素材包已生成，正在加载首页分析视图...";
  const caseData = await loadCasePayload(caseId);
  renderHomeCase(caseData);
  resultCard.scrollIntoView({behavior: "smooth", block: "start"});
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
  setHomeRoute("settings");
});

settingsClose.addEventListener("click", () => {
  setHomeRoute("single");
});

homeRouteButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setHomeRoute(button.dataset.homeRoute);
  });
});

window.addEventListener("hashchange", () => {
  setHomeRoute(routeFromHash(), false);
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

singleForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  singleButton.disabled = true;
  singleButton.textContent = "处理中...";
  downloadSelectedButton.disabled = true;
  selectedCandidate = null;
  currentLocalVideoId = "";
  homeCaseView.classList.add("hidden");
  resultCard.classList.add("hidden");
  setStatus(parseStatus, "解析中");
  setStatus(downloadStatus, "未开始");
  setStatus(packageStatus, "未生成");
  setStatus(analysisStatus, "未运行");
  try {
    const value = new FormData(singleForm).get("value");
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
  } catch (error) {
    singleResult.classList.remove("hidden");
    singleResult.textContent = `${error.error_code || "ERROR"}：${error.message || "导入失败"}`;
    setStatus(parseStatus, "失败");
    singleButton.disabled = false;
    singleButton.textContent = "解析作品";
  } finally {
    singleButton.disabled = false;
    singleButton.textContent = "解析作品";
  }
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
  downloadSelectedButton.disabled = false;
}

function chooseCandidate(candidates) {
  const preference = qualityPreference.value;
  if (preference === "1080") {
    return candidates.find((candidate) => String(candidate.quality_label || "").includes("1080")) || candidates[0];
  }
  if (preference === "720") {
    return candidates.find((candidate) => String(candidate.quality_label || "").includes("720")) || candidates[0];
  }
  return candidates[0];
}

async function downloadCandidate(candidate) {
  jobCard.classList.remove("hidden");
  setHomeRoute("single");
  progressBar.style.width = "0%";
  jobMessage.className = "job-message";
  jobMessage.textContent = "创建下载和素材包任务...";
  setStatus(downloadStatus, "等待任务");
  setStatus(packageStatus, "等待生成");
  setStatus(analysisStatus, "未运行");
  jobResult.textContent = "";
  caseSummary.innerHTML = "";
  resultCard.classList.add("hidden");
  buildCaseButton.hidden = true;
  downloadSelectedButton.disabled = true;
  try {
    const response = await fetch("/api/jobs/download-and-build-case", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({aweme_id: currentAwemeId, candidate_id: candidate.candidate_id}),
    });
    const payload = await readJsonResponse(response);
    pollJob(payload.job_id, async (job) => {
      if (job.status === "success" && job.result_json.local_video_id) {
        currentLocalVideoId = job.result_json.local_video_id;
        resultCard.classList.remove("hidden");
        buildCaseButton.hidden = true;
        renderWorkflowResult(job.result_json);
        setStatus(downloadStatus, "完成");
        setStatus(packageStatus, "已生成");
        setStatus(analysisStatus, "未运行，可到 case 页启动");
        if (await showAnalysisInline(job.result_json)) {
          setHomeRoute("cases");
          return;
        }
      }
    });
  } catch (error) {
    jobMessage.className = "job-message failed";
    jobMessage.textContent = `${error.error_code || "ERROR"}：${error.message || "任务创建失败"}`;
    setStatus(downloadStatus, "失败");
    singleButton.disabled = false;
    singleButton.textContent = "解析作品";
    downloadSelectedButton.disabled = !selectedCandidate;
  }
}

downloadSelectedButton.addEventListener("click", async () => {
  if (!selectedCandidate) {
    return;
  }
  await downloadCandidate(selectedCandidate);
});

buildCaseButton.addEventListener("click", async () => {
  if (!currentLocalVideoId) {
    return;
  }
  buildCaseButton.disabled = true;
  jobCard.classList.remove("hidden");
  progressBar.style.width = "0%";
  jobMessage.className = "job-message";
  jobMessage.textContent = "创建任务...";
  jobResult.textContent = "";
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

async function pollJob(jobId, onSuccess) {
  try {
    const response = await fetch(`/api/jobs/${jobId}`, {cache: "no-store"});
    const payload = await readJsonResponse(response);
    const job = payload.job;
    progressBar.style.width = `${job.progress || 0}%`;
    jobMessage.textContent = `${job.status} · ${job.progress}% · ${job.message || ""}`;
    if (job.status === "success") {
      jobMessage.className = "job-message success";
      if (onSuccess) {
        await onSuccess(job);
      } else {
        showJson(jobResult, job.result_json);
      }
      buildCaseButton.disabled = false;
      singleButton.disabled = false;
      singleButton.textContent = "解析作品";
      downloadSelectedButton.disabled = !selectedCandidate;
      return;
    }
    if (job.status === "failed") {
      jobMessage.className = "job-message failed";
      jobMessage.textContent = `${job.error_code || "ERROR"}：${job.message || "任务失败"}`;
      showJson(jobResult, job);
      setStatus(downloadStatus, "失败");
      buildCaseButton.disabled = false;
      singleButton.disabled = false;
      singleButton.textContent = "解析作品";
      downloadSelectedButton.disabled = !selectedCandidate;
      return;
    }
    window.setTimeout(() => pollJob(jobId, onSuccess), 700);
  } catch (error) {
    jobMessage.className = "job-message failed";
    jobMessage.textContent = `${error.error_code || "ERROR"}：${error.message || "查询任务失败"}`;
    buildCaseButton.disabled = false;
    singleButton.disabled = false;
    singleButton.textContent = "解析作品";
    downloadSelectedButton.disabled = !selectedCandidate;
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
setHomeRoute(routeFromHash(), false);
