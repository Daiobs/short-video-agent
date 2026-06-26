const refreshCalibrationButton = document.getElementById("refresh-calibration-button");
const copyCalibrationReportButton = document.getElementById("copy-calibration-report-button");
const downloadCalibrationReportButton = document.getElementById("download-calibration-report-button");
const calibrationReportStatus = document.getElementById("calibration-report-status");
const calibrationFilterForm = document.getElementById("calibration-filter-form");
const calibrationStatusFilter = document.getElementById("calibration-status-filter");
const calibrationDiagnosisStatusFilter = document.getElementById("calibration-diagnosis-status-filter");
const calibrationVerdictFilter = document.getElementById("calibration-verdict-filter");
const calibrationCategoryFilter = document.getElementById("calibration-category-filter");
const calibrationSearchFilter = document.getElementById("calibration-search-filter");
const calibrationUpdatedAt = document.getElementById("calibration-updated-at");
const calibrationSummary = document.getElementById("calibration-summary");
const calibrationInsights = document.getElementById("calibration-insights");
const calibrationRecommendations = document.getElementById("calibration-recommendations");
const calibrationRecords = document.getElementById("calibration-records");

const calibrationStatusLabels = {
  needs_ai_analysis: "等待 AI 拆解",
  awaiting_review: "等待人工验收",
  needs_rerun: "需要重跑",
  accepted: "验收通过",
  calibrating: "校准中",
};

const diagnosisStatusLabels = {
  needs_ai_analysis: "等待 AI 拆解",
  needs_rerun: "需要带反馈重跑",
  enrichment_mismatch: "富化证据未对齐",
  needs_context: "证据不完整",
  accepted: "可沉淀",
  reviewable: "可人工复核",
  needs_review: "需要补齐",
};

const verdictLabels = {
  pending: "待验收",
  pass: "通过",
  needs_fix: "需要修正",
  reject: "不通过",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("zh-CN");
}

function formatDate(value) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {hour12: false});
}

function formatMap(value, labels = {}) {
  const entries = Object.entries(value || {});
  if (!entries.length) {
    return "暂无";
  }
  return entries
    .map(([key, count]) => `${labels[key] || key} ${count}`)
    .join(" / ");
}

function formatEvidenceCompletion(summary) {
  const evidence = summary?.evidence_completion || {};
  const withEvidence = Number(evidence.with_required_evidence || 0);
  if (!withEvidence) {
    return "暂无重跑证据样本";
  }
  return `样本 ${withEvidence} · 已齐 ${formatNumber(evidence.complete_records || 0)} · 仍缺 ${formatNumber(evidence.missing_records || 0)} · 证据项 ${formatNumber(evidence.ready_items || 0)}/${formatNumber(evidence.total_items || 0)}`;
}

async function readJsonResponse(response) {
  const payload = await response.json();
  if (!response.ok || payload.ok === false) {
    throw payload;
  }
  return payload;
}

function currentQuery() {
  const params = new URLSearchParams();
  if (calibrationStatusFilter.value) {
    params.set("status", calibrationStatusFilter.value);
  }
  if (calibrationDiagnosisStatusFilter.value) {
    params.set("diagnosis_status", calibrationDiagnosisStatusFilter.value);
  }
  if (calibrationVerdictFilter.value) {
    params.set("verdict", calibrationVerdictFilter.value);
  }
  if (calibrationCategoryFilter.value.trim()) {
    params.set("category", calibrationCategoryFilter.value.trim());
  }
  if (calibrationSearchFilter.value.trim()) {
    params.set("search", calibrationSearchFilter.value.trim());
  }
  return params;
}

async function loadCalibrationReport() {
  const query = currentQuery();
  const response = await fetch(`/api/cases/quality-calibration/report?${query.toString()}`, {cache: "no-store"});
  return readJsonResponse(response);
}

function showReportStatus(message) {
  calibrationReportStatus.classList.remove("hidden");
  calibrationReportStatus.textContent = message;
}

function renderSummary(payload) {
  const summary = payload.summary || {};
  const filtered = payload.filtered_summary || {};
  calibrationUpdatedAt.textContent = payload.updated_at
    ? `索引更新时间：${formatDate(payload.updated_at)}`
    : "还没有保存过校准样本。";
  calibrationSummary.innerHTML = `
    <article class="calibration-summary-item">
      <strong>${escapeHtml(formatNumber(summary.total || 0))}</strong>
      <span>全部样本</span>
    </article>
    <article class="calibration-summary-item">
      <strong>${escapeHtml(formatNumber(filtered.total || 0))}</strong>
      <span>当前筛选</span>
    </article>
    <article class="calibration-summary-item wide">
      <strong>校准状态</strong>
      <span>${escapeHtml(formatMap(summary.by_status, calibrationStatusLabels))}</span>
    </article>
    <article class="calibration-summary-item wide">
      <strong>诊断状态</strong>
      <span>${escapeHtml(formatMap(summary.by_diagnosis_status, diagnosisStatusLabels))}</span>
    </article>
    <article class="calibration-summary-item wide">
      <strong>人工结论</strong>
      <span>${escapeHtml(formatMap(summary.by_verdict, verdictLabels))}</span>
    </article>
    <article class="calibration-summary-item wide">
      <strong>证据完成度</strong>
      <span>${escapeHtml(formatEvidenceCompletion(summary))}</span>
    </article>
    <article class="calibration-summary-item wide">
      <strong>筛选证据</strong>
      <span>${escapeHtml(formatEvidenceCompletion(filtered))}</span>
    </article>
  `;
}

function renderIssueList(items) {
  const values = Array.isArray(items) ? items : [];
  if (!values.length) {
    return '<p class="muted compact-copy">暂无。</p>';
  }
  return `
    <ul class="issue-list">
      ${values
        .map((item) => `
          <li>
            <strong>${escapeHtml(item.label || item.id || "")}</strong>
            <span>${escapeHtml(formatNumber(item.count || 0))} 次</span>
            ${
              Array.isArray(item.examples) && item.examples.length
                ? `<p>${escapeHtml(item.examples.join(" / "))}</p>`
                : ""
            }
          </li>
        `)
        .join("")}
    </ul>
  `;
}

function renderInsights(payload) {
  const insights = payload.filtered_insights || payload.insights || {};
  calibrationInsights.innerHTML = `
    <article class="calibration-insight-card">
      <strong>AI 自检缺口</strong>
      ${renderIssueList(insights.top_ai_gaps || [])}
    </article>
    <article class="calibration-insight-card">
      <strong>人工阻塞项</strong>
      ${renderIssueList(insights.top_human_blockers || [])}
    </article>
    <article class="calibration-insight-card">
      <strong>诊断阻塞</strong>
      ${renderIssueList(insights.top_diagnosis_blockers || [])}
    </article>
    <article class="calibration-insight-card">
      <strong>准备度缺口</strong>
      ${renderIssueList(insights.top_readiness_gaps || [])}
    </article>
    <article class="calibration-insight-card">
      <strong>重跑仍缺证据</strong>
      ${renderIssueList(insights.top_rerun_evidence_gaps || [])}
    </article>
    <article class="calibration-insight-card">
      <strong>重跑合规失败</strong>
      ${renderIssueList(insights.top_rerun_compliance_failures || [])}
    </article>
    <article class="calibration-insight-card">
      <strong>下一步动作</strong>
      ${renderIssueList(insights.top_next_actions || [])}
    </article>
    <article class="calibration-insight-card">
      <strong>诊断推荐动作</strong>
      ${renderIssueList(insights.top_diagnosis_actions || [])}
    </article>
  `;
}

function renderRecommendations(payload) {
  const recommendations = payload.filtered_recommendations || payload.recommendations || [];
  if (!recommendations.length) {
    calibrationRecommendations.innerHTML = '<p class="muted compact-copy">暂无明确规则改进建议。保存更多人工验收样本后，这里会自动聚合。</p>';
    return;
  }
  calibrationRecommendations.innerHTML = recommendations
    .map((item) => {
      const sourceIds = Array.isArray(item.source_issue_ids)
        ? item.source_issue_ids.map((value) => String(value || "").trim()).filter(Boolean)
        : [];
      const actionTarget = item.action_target || "";
      const actionLabel = item.action_label || "";
      return `
        <article class="calibration-recommendation">
          <div>
            <span class="status-pill">${escapeHtml(`P${item.priority ?? 0}`)}</span>
            <strong>${escapeHtml(item.label || item.id || "")}</strong>
          </div>
          <p>${escapeHtml(item.reason || "")}</p>
          <p class="recommendation-action">${escapeHtml(item.action || "")}</p>
          ${sourceIds.length ? `<p class="muted compact-copy">触发项：${escapeHtml(sourceIds.join(" / "))}</p>` : ""}
          ${actionLabel || actionTarget ? `<p class="muted compact-copy">页面动作：${escapeHtml(actionLabel || "查看")} -> ${escapeHtml(actionTarget || "无")}</p>` : ""}
        </article>
      `;
    })
    .join("");
}

function renderActionList(actions) {
  const values = Array.isArray(actions) ? actions : [];
  if (!values.length) {
    return '<p class="muted compact-copy">暂无下一步动作。</p>';
  }
  return `
    <ul class="mini-list">
      ${values
        .map((action) => `<li>${escapeHtml(action.description || action.label || "")}</li>`)
        .join("")}
    </ul>
  `;
}

function renderRerunEvidenceList(items) {
  const values = Array.isArray(items) ? items : [];
  if (!values.length) {
    return '<p class="muted compact-copy">无证据要求</p>';
  }
  return `
    <ul class="calibration-evidence-list">
      ${values
        .map((item) => {
          const meta = [];
          if (item.char_count !== undefined && item.char_count !== null && item.char_count !== "") {
            meta.push(`文本 ${item.char_count} 字`);
          }
          if (item.segment_count !== undefined && item.segment_count !== null && item.segment_count !== "") {
            meta.push(`ASR ${item.segment_count} 段`);
          }
          if (item.count !== undefined && item.count !== null && item.count !== "") {
            meta.push(`评论 ${item.count} 条`);
          }
          if (Array.isArray(item.sources) && item.sources.length) {
            meta.push(`来源 ${item.sources.join(" / ")}`);
          }
          return `
            <li>
              <div>
                <strong>${escapeHtml(item.label || item.id || "证据")}</strong>
                <span class="status-pill ${escapeHtml(item.status || "pending")}">${escapeHtml(item.status || "pending")}</span>
              </div>
              ${meta.length ? `<p>${escapeHtml(meta.join(" · "))}</p>` : ""}
              ${item.excerpt ? `<p class="muted compact-copy">${escapeHtml(item.excerpt)}</p>` : ""}
            </li>
          `;
        })
        .join("")}
    </ul>
  `;
}

function renderRerunEvidenceSummary(strategy) {
  const summary = strategy.evidence_summary || {};
  const total = Number(summary.total || 0);
  if (!total) {
    return '<p class="muted compact-copy">暂无必须核对的证据。</p>';
  }
  return `
    <p class="muted compact-copy">
      证据完成度：已就绪 ${escapeHtml(summary.ready || 0)} / 缺失 ${escapeHtml(summary.missing || 0)} / 总计 ${escapeHtml(total)}
    </p>
  `;
}

function renderRecords(records) {
  if (!records.length) {
    calibrationRecords.innerHTML = '<p class="muted compact-copy">暂无匹配的校准样本。可以先在 case 页面点击“保存校准样本”。</p>';
    return;
  }
  calibrationRecords.innerHTML = records
    .map((record) => {
      const calibration = record.quality_calibration || {};
      const diagnosis = record.case_diagnosis || {};
      const rerunStrategy = record.rerun_strategy || {};
      const aiQuality = calibration.ai_quality || {};
      const acceptance = record.quality_acceptance || {};
      const stats = record.stats || {};
      const status = calibration.status || "unknown";
      const verdict = acceptance.verdict || "pending";
      return `
        <article class="calibration-record ${escapeHtml(status)}">
          <div class="calibration-record-header">
            <div>
              <div class="record-title-row">
                <span class="status-pill ${escapeHtml(status)}">${escapeHtml(calibrationStatusLabels[status] || status)}</span>
                <span class="status-pill ${escapeHtml(diagnosis.status || "unknown")}">${escapeHtml(diagnosisStatusLabels[diagnosis.status] || diagnosis.status || "未诊断")}</span>
                <span class="status-pill ${escapeHtml(verdict)}">${escapeHtml(verdictLabels[verdict] || verdict)}</span>
              </div>
              <h3>${escapeHtml(record.title || record.case_id || "未命名样本")}</h3>
              <p class="muted compact-copy">${escapeHtml(record.content_category_label || record.content_category || "未分类")} · ${escapeHtml(record.author || "未知作者")} · ${escapeHtml(formatDate(record.recorded_at))}</p>
            </div>
            <div class="quality-calibration-score">
              <span>${escapeHtml(aiQuality.score ?? 0)}</span>
              <small>AI / ${escapeHtml(aiQuality.max_score ?? 100)}</small>
            </div>
          </div>
          <div class="calibration-record-grid">
            <dl class="report-dl">
              <dt>case_id</dt><dd>${escapeHtml(record.case_id || "")}</dd>
              <dt>互动分</dt><dd>${escapeHtml(formatNumber(stats.engagement_score || 0))}</dd>
              <dt>AI 等级</dt><dd>${escapeHtml(aiQuality.label || aiQuality.level || "")}</dd>
              <dt>人工评分</dt><dd>${escapeHtml(acceptance.score || "")}</dd>
            </dl>
            <div>
              <strong>人工验收意见</strong>
              <p>${escapeHtml(acceptance.summary || "暂无。")}</p>
              <p class="muted compact-copy">${escapeHtml(acceptance.notes || "")}</p>
            </div>
            <div>
              <strong>顶部诊断</strong>
              <p>${escapeHtml(diagnosis.summary || "暂无诊断快照。")}</p>
              <p class="muted compact-copy">${escapeHtml((diagnosis.blockers || []).map((item) => item.label || item.source || "").filter(Boolean).join(" / ") || "无阻塞")}</p>
            </div>
            <div>
              <strong>推荐动作</strong>
              ${renderActionList(diagnosis.primary_actions || calibration.next_actions || [])}
            </div>
            <div>
              <strong>重跑策略</strong>
              <p>${escapeHtml(rerunStrategy.summary || "暂无重跑策略。")}</p>
              ${renderRerunEvidenceSummary(rerunStrategy)}
              ${renderRerunEvidenceList(rerunStrategy.required_evidence || [])}
            </div>
          </div>
          <div class="toolbar-actions">
            <a class="button-link" href="/cases/${encodeURIComponent(record.case_id)}" target="_blank" rel="noreferrer">打开 case</a>
          </div>
        </article>
      `;
    })
    .join("");
}

async function loadCalibrationRecords() {
  refreshCalibrationButton.disabled = true;
  calibrationRecords.innerHTML = '<p class="muted compact-copy">正在读取校准样本...</p>';
  try {
    const query = currentQuery();
    const response = await fetch(`/api/cases/quality-calibration/records?${query.toString()}`, {cache: "no-store"});
    const payload = await readJsonResponse(response);
    renderSummary(payload);
    renderInsights(payload);
    renderRecommendations(payload);
    renderRecords(payload.records || []);
  } catch (error) {
    calibrationRecords.innerHTML = `<p class="notice">${escapeHtml(error.error_code || "ERROR")}：${escapeHtml(error.message || "读取校准样本失败")}</p>`;
  } finally {
    refreshCalibrationButton.disabled = false;
  }
}

calibrationFilterForm.addEventListener("submit", (event) => {
  event.preventDefault();
  loadCalibrationRecords();
});

refreshCalibrationButton.addEventListener("click", () => {
  loadCalibrationRecords();
});

copyCalibrationReportButton.addEventListener("click", async () => {
  copyCalibrationReportButton.disabled = true;
  showReportStatus("正在生成对比报告...");
  try {
    const payload = await loadCalibrationReport();
    await navigator.clipboard.writeText(payload.report_markdown || "");
    showReportStatus("已复制当前筛选结果的 Markdown 对比报告。");
  } catch (error) {
    showReportStatus(`${error.error_code || "ERROR"}：${error.message || "生成报告失败"}`);
  } finally {
    copyCalibrationReportButton.disabled = false;
  }
});

downloadCalibrationReportButton.addEventListener("click", async () => {
  downloadCalibrationReportButton.disabled = true;
  showReportStatus("正在生成对比报告...");
  try {
    const payload = await loadCalibrationReport();
    const blob = new Blob([payload.report_markdown || ""], {type: "text/markdown;charset=utf-8"});
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "quality_calibration_report.md";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    showReportStatus("已下载当前筛选结果的 Markdown 对比报告。");
  } catch (error) {
    showReportStatus(`${error.error_code || "ERROR"}：${error.message || "下载报告失败"}`);
  } finally {
    downloadCalibrationReportButton.disabled = false;
  }
});

loadCalibrationRecords();
