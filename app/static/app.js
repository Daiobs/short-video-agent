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
const testLlmButton = document.getElementById("test-llm-button");
const llmTestResult = document.getElementById("llm-test-result");
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
const jobResult = document.getElementById("job-result");
const homeRouteButtons = Array.from(document.querySelectorAll("[data-home-route]"));
const homePanels = Array.from(document.querySelectorAll("[data-home-panel]"));
const profileForm = document.getElementById("profile-form");
const profileSort = document.getElementById("profile-sort");
const profileScanButton = document.getElementById("profile-scan-button");
const profileSelectedImportButton = document.getElementById("profile-selected-import-button");
const profileSelectedBuildButton = document.getElementById("profile-selected-build-button");
const profileScanStatus = document.getElementById("profile-scan-status");
const profileResultsCard = document.getElementById("profile-results-card");
const profileProviderBadge = document.getElementById("profile-provider-badge");
const profileWarnings = document.getElementById("profile-warnings");
const profileSummary = document.getElementById("profile-summary");
const profileResultsBody = document.getElementById("profile-results-body");

let currentLocalVideoId = "";
let currentAwemeId = "";
let selectedCandidate = null;
let loadedHomeCase = null;
let profileItems = [];
let profileScanPayload = null;

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

function normalizeItems(value) {
  if (!value) {
    return [];
  }
  if (Array.isArray(value)) {
    return value.filter((item) => item !== undefined && item !== null && item !== "");
  }
  return [value];
}

function formatReportValue(value) {
  if (Array.isArray(value)) {
    return value.map(formatReportValue).join(" / ");
  }
  if (value && typeof value === "object") {
    return Object.entries(value)
      .map(([key, item]) => `${key}: ${formatReportValue(item)}`)
      .join("；");
  }
  return String(value ?? "");
}

function renderPublicList(items, emptyText = "暂无明确结论。") {
  const values = normalizeItems(items).map(formatReportValue).filter(Boolean);
  if (!values.length) {
    return `<p class="muted compact-copy">${escapeHtml(emptyText)}</p>`;
  }
  return `<ul class="public-report-list">${values.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
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
}

function sortProfileItems(items, sortBy) {
  const key = ["like_count", "comment_count", "share_count", "engagement_score", "create_time"].includes(sortBy)
    ? sortBy
    : "like_count";
  return [...items].sort((left, right) => {
    const leftValue = left[key] || 0;
    const rightValue = right[key] || 0;
    return rightValue > leftValue ? 1 : rightValue < leftValue ? -1 : 0;
  });
}

function selectedProfileItems() {
  const ids = Array.from(document.querySelectorAll("[data-profile-select]:checked")).map((input) => input.value);
  return profileItems.filter((item) => ids.includes(item.aweme_id));
}

function renderProfileSummary(summary) {
  if (!summary || !profileSummary) {
    return;
  }
  const topItems = normalizeItems(summary.top_items).slice(0, 3);
  profileSummary.innerHTML = `
    <article><span>扫描作品</span><strong>${formatNumber(summary.scanned_count)}</strong></article>
    <article><span>最高综合分</span><strong>${formatNumber(summary.max_engagement_score)}</strong></article>
    <article><span>平均点赞</span><strong>${formatNumber(summary.avg_like_count)}</strong></article>
    <article><span>平均评论</span><strong>${formatNumber(summary.avg_comment_count)}</strong></article>
    <article><span>平均分享</span><strong>${formatNumber(summary.avg_share_count)}</strong></article>
    <article class="wide"><span>高频关键词</span><strong>${escapeHtml(normalizeItems(summary.content_keywords).slice(0, 8).join(" / ") || "暂无")}</strong></article>
    <article class="wide"><span>综合分 Top 3</span><strong>${escapeHtml(topItems.map((item) => item.title || item.aweme_id).join(" / ") || "暂无")}</strong></article>
  `;
}

function renderProfileResults(payload) {
  profileScanPayload = payload;
  profileItems = normalizeItems(payload.items);
  profileResultsCard.classList.remove("hidden");
  profileProviderBadge.textContent = payload.provider || "profile";
  const warnings = normalizeItems(payload.warnings);
  profileWarnings.classList.toggle("hidden", !warnings.length);
  profileWarnings.textContent = warnings.join(" ");
  renderProfileSummary(payload.summary || {});
  renderProfileTable();
}

function renderProfileTable() {
  const sorted = sortProfileItems(profileItems, profileSort.value);
  if (!sorted.length) {
    profileResultsBody.innerHTML = '<tr><td colspan="9" class="muted">没有扫描到作品。可以改用多作品链接粘贴。</td></tr>';
    return;
  }
  profileResultsBody.innerHTML = sorted
    .map((item) => {
      const image = item.cover_url
        ? `<img src="${escapeHtml(item.cover_url)}" alt="" class="profile-cover">`
        : '<div class="profile-cover placeholder">无封面</div>';
      const typeLabel = {video: "视频", image: "图文/照片", unknown: "未知"}[item.media_type] || "未知";
      const buildDisabled = item.can_build_case === false ? " disabled" : "";
      const buildTitle = item.can_build_case === false ? ' title="图文/照片作品暂不能走视频素材包流程，请先用单作品解析确认支持情况。"' : "";
      return `
        <tr>
          <td><input type="checkbox" data-profile-select value="${escapeHtml(item.aweme_id)}"></td>
          <td>${image}</td>
          <td>
            <strong>${escapeHtml(item.title || item.desc || item.aweme_id)}</strong>
            <p>${escapeHtml(item.desc || item.webpage_url || "")}</p>
            <span class="profile-media-type ${escapeHtml(item.media_type || "unknown")}">${escapeHtml(typeLabel)}</span>
          </td>
          <td>${formatNumber(item.like_count)}</td>
          <td>${formatNumber(item.comment_count)}</td>
          <td>${formatNumber(item.share_count)}</td>
          <td>${formatNumber(item.engagement_score)}</td>
          <td>${escapeHtml(item.create_time || "未知")}</td>
          <td>
            <button type="button" data-profile-import="${escapeHtml(item.aweme_id)}">进入解析</button>
            <button type="button" data-profile-build="${escapeHtml(item.aweme_id)}"${buildDisabled}${buildTitle}>生成素材包</button>
          </td>
        </tr>
      `;
    })
    .join("");
}

async function scanProfile() {
  profileScanButton.disabled = true;
  profileScanStatus.textContent = "正在扫描...";
  profileResultsCard.classList.add("hidden");
  try {
    const formData = new FormData(profileForm);
    const profileValue = String(formData.get("profile_url") || "").trim();
    const isUrl = /^https?:\/\//i.test(profileValue);
    const payload = {
      profile_url: isUrl ? profileValue : "",
      sec_user_id: isUrl ? "" : profileValue,
      manual_links: String(formData.get("manual_links") || ""),
      count: Number(formData.get("count") || 20),
      max_pages: 1,
      sort_by: String(formData.get("sort_by") || "like_count"),
    };
    const response = await fetch("/api/profile/scan", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    const result = await readJsonResponse(response);
    profileScanStatus.textContent = `扫描完成：${result.items.length} 条作品。`;
    renderProfileResults(result);
  } catch (error) {
    profileScanStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "扫描失败，请改用多作品链接粘贴或单作品解析。"}`;
  } finally {
    profileScanButton.disabled = false;
  }
}

function profileItemByAwemeId(awemeId) {
  return profileItems.find((item) => item.aweme_id === awemeId);
}

function profileItemValue(item) {
  return item?.webpage_url || item?.aweme_id || "";
}

function importProfileItem(item) {
  const value = profileItemValue(item);
  if (!value) {
    return;
  }
  singleForm.querySelector('[name="value"]').value = value;
  setHomeRoute("single");
  singleResult.classList.remove("hidden");
  singleResult.textContent = `已带入作品：${item.aweme_id}。点击“解析”会复用单作品流程。`;
}

async function buildProfileItem(item) {
  const value = profileItemValue(item);
  if (!value) {
    return;
  }
  if (item.can_build_case === false) {
    profileScanStatus.textContent = "图文/照片作品暂不能直接生成视频素材包，请先进入单作品解析确认支持情况。";
    return;
  }
  singleForm.querySelector('[name="value"]').value = value;
  setHomeRoute("single");
  await runSingleValue(value);
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
  await scanProfile();
});

profileSort.addEventListener("change", () => {
  if (profileScanPayload) {
    renderProfileTable();
  }
});

profileResultsBody.addEventListener("click", async (event) => {
  const importButton = event.target.closest("[data-profile-import]");
  const buildButton = event.target.closest("[data-profile-build]");
  if (importButton) {
    importProfileItem(profileItemByAwemeId(importButton.dataset.profileImport));
  } else if (buildButton) {
    await buildProfileItem(profileItemByAwemeId(buildButton.dataset.profileBuild));
  }
});

profileSelectedImportButton.addEventListener("click", () => {
  const selected = selectedProfileItems();
  if (!selected.length) {
    profileScanStatus.textContent = "请先选择 1 条作品。";
    return;
  }
  if (selected.length > 1) {
    profileScanStatus.textContent = "P2.0 不做批量解析，请先选择 1 条作品。";
    return;
  }
  importProfileItem(selected[0]);
});

profileSelectedBuildButton.addEventListener("click", async () => {
  const selected = selectedProfileItems();
  if (!selected.length) {
    profileScanStatus.textContent = "请先选择 1 条作品。";
    return;
  }
  if (selected.length > 1) {
    profileScanStatus.textContent = "P2.0 不自动批量下载或批量 AI 拆解，请先选择 1 条作品。";
    return;
  }
  if (selected[0].can_build_case === false) {
    profileScanStatus.textContent = "选中的图文/照片作品暂不能直接生成视频素材包，请先进入单作品解析确认支持情况。";
    return;
  }
  await buildProfileItem(selected[0]);
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
  let inlineCaseShown = false;
  jobCard.classList.remove("hidden");
  setHomeRoute("single");
  progressBar.style.width = "0%";
  jobMessage.className = "job-message";
  jobMessage.textContent = "创建下载和素材包任务...";
  setStatus(downloadStatus, "等待任务");
  setStatus(packageStatus, "等待生成");
  setStatus(analysisStatus, "等待自动拆解");
  jobResult.textContent = "";
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

async function pollJob(jobId, onSuccess, onProgress) {
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
      singleButton.textContent = "解析";
      return;
    }
    if (job.status === "failed") {
      jobMessage.className = "job-message failed";
      jobMessage.textContent = `${job.error_code || "ERROR"}：${job.message || "任务失败"}`;
      showJson(jobResult, job);
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
setHomeRoute(routeFromHash(), false);
