const page = document.querySelector(".case-page");
const caseId = page.dataset.caseId;
const contactSheetImage = document.getElementById("contact-sheet-image");
const caseMeta = document.getElementById("case-meta");
const analysisCategorySelect = document.getElementById("analysis-category-select");
const updateCategoryButton = document.getElementById("update-category-button");
const categoryDescription = document.getElementById("category-description");
const categoryStatus = document.getElementById("category-status");
const keyframeStrip = document.getElementById("keyframe-strip");
const promptText = document.getElementById("prompt-text");
const analysisBriefText = document.getElementById("analysis-brief-text");
const analysisJson = document.getElementById("analysis-json");
const copyPromptButton = document.getElementById("copy-prompt-button");
const downloadAnalysisInputButton = document.getElementById("download-analysis-input-button");
const downloadRerunPlanButton = document.getElementById("download-rerun-plan-button");
const downloadRerunPlanMarkdownButton = document.getElementById("download-rerun-plan-markdown-button");
const copyBriefButton = document.getElementById("copy-brief-button");
const runAutoAnalysisButton = document.getElementById("run-auto-analysis-button");
const copyAiReportButton = document.getElementById("copy-ai-report-button");
const artifactOverview = document.getElementById("artifact-overview");
const caseLlmStatus = document.getElementById("case-llm-status");
const autoAnalysisStatus = document.getElementById("auto-analysis-status");
const autoAnalysisSummary = document.getElementById("auto-analysis-summary");
const autoAnalysisCards = document.getElementById("auto-analysis-cards");
const autoAnalysisReport = document.getElementById("auto-analysis-report");
const caseDiagnosisSummary = document.getElementById("case-diagnosis-summary");
const readinessSummary = document.getElementById("readiness-summary");
const qualityCalibrationSummary = document.getElementById("quality-calibration-summary");
const saveQualityCalibrationRecordButton = document.getElementById("save-quality-calibration-record-button");
const qualityCalibrationRecordStatus = document.getElementById("quality-calibration-record-status");
const worksheetSummary = document.getElementById("worksheet-summary");
const worksheetReview = document.getElementById("worksheet-review");
const worksheetSections = document.getElementById("worksheet-sections");
const saveWorksheetButton = document.getElementById("save-worksheet-button");
const worksheetStatus = document.getElementById("worksheet-status");
const qualityAcceptanceSummary = document.getElementById("quality-acceptance-summary");
const rerunStrategyPanel = document.getElementById("rerun-strategy-panel");
const qualityAcceptanceVerdict = document.getElementById("quality-acceptance-verdict");
const qualityAcceptanceScore = document.getElementById("quality-acceptance-score");
const qualityAcceptanceReviewer = document.getElementById("quality-acceptance-reviewer");
const qualityAcceptanceSummaryInput = document.getElementById("quality-acceptance-summary-input");
const qualityAcceptanceChecks = document.getElementById("quality-acceptance-checks");
const qualityAcceptanceNotes = document.getElementById("quality-acceptance-notes");
const qualityAcceptanceNextActions = document.getElementById("quality-acceptance-next-actions");
const saveQualityAcceptanceButton = document.getElementById("save-quality-acceptance-button");
const saveQualityAcceptanceAndRerunButton = document.getElementById("save-quality-acceptance-and-rerun-button");
const qualityAcceptanceStatus = document.getElementById("quality-acceptance-status");
const runEnrichmentButton = document.getElementById("run-enrichment-button");
const metricSnapshotButton = document.getElementById("metric-snapshot-button");
const asrPlaceholderButton = document.getElementById("asr-placeholder-button");
const ocrPlaceholderButton = document.getElementById("ocr-placeholder-button");
const enrichmentStatus = document.getElementById("enrichment-status");
const enrichmentSummary = document.getElementById("enrichment-summary");
const commentsImportText = document.getElementById("comments-import-text");
const importCommentsButton = document.getElementById("import-comments-button");
const commentsStatus = document.getElementById("comments-status");
const metricStatus = document.getElementById("metric-status");
const primaryWorkflowSummary = document.getElementById("primary-workflow-summary");
const primaryCaseMeta = document.getElementById("primary-case-meta");
const primaryArtifactStatus = document.getElementById("primary-artifact-status");
const primaryAiStatus = document.getElementById("primary-ai-status");
const caseTabButtons = Array.from(document.querySelectorAll("[data-case-tab]"));
const caseTabPanels = Array.from(document.querySelectorAll("[data-case-tab-panel]"));

let loadedCase = null;

function wait(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
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

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
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

function setCaseTab(tab) {
  const activeTab = ["overview", "ai", "package", "review", "enrichment", "calibration"].includes(tab)
    ? tab
    : "overview";
  caseTabPanels.forEach((panel) => {
    panel.classList.toggle("hidden", panel.dataset.caseTabPanel !== activeTab);
  });
  caseTabButtons.forEach((button) => {
    const active = button.dataset.caseTab === activeTab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "page" : "false");
  });
}

function syncPrimaryRunButtons(disabled) {
  document.querySelectorAll('[data-primary-action="run_ai"]').forEach((button) => {
    button.disabled = disabled;
  });
}

function renderPrimaryWorkflow(data) {
  const workflow = data.primary_workflow || {};
  const configured = Boolean(workflow.llm_configured);
  const analysisStatus = workflow.analysis_status || "unknown";
  primaryWorkflowSummary.innerHTML = `
    <div class="primary-workflow-hero ${escapeHtml(analysisStatus)}">
      <strong>${escapeHtml(workflow.next_action_label || "查看素材包")}</strong>
      <p>${escapeHtml(
        workflow.artifact_ready
          ? "素材包已生成。你可以复制 prompt 手动分析，也可以在配置大模型后启动 AI 自动拆解。"
          : "素材包文件不完整，建议重新生成素材包。",
      )}</p>
    </div>
  `;
  const missing = normalizeItems(workflow.missing_artifacts);
  primaryArtifactStatus.textContent = workflow.artifact_ready
    ? "素材包已生成：video.mp4、metadata.json、ffprobe.json、contact_sheet.jpg、keyframes、prompt.md 和 analysis_input.json 可用。"
    : `素材包缺少：${missing.join("、") || "未知文件"}`;
  if (!workflow.artifact_ready) {
    primaryAiStatus.textContent = "请先重新生成素材包。";
  } else if (analysisStatus === "completed") {
    primaryAiStatus.textContent = "AI 自动拆解已完成，可查看 analysis_report.md。";
  } else if (!configured) {
    primaryAiStatus.textContent = "AI 未配置。你仍然可以复制 prompt.md 和下载 analysis_input.json，手动交给外部大模型分析。";
  } else {
    primaryAiStatus.textContent = "AI 已配置，但当前 case 还未分析。可以点击“开始 AI 自动拆解”。";
  }
  runAutoAnalysisButton.textContent = analysisStatus === "completed" ? "重新 AI 自动拆解" : "开始 AI 自动拆解";
  syncPrimaryRunButtons(!configured || !workflow.artifact_ready);
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

function renderMiniList(items) {
  const values = normalizeItems(items);
  if (!values.length) {
    return '<p class="muted compact-copy">暂无。</p>';
  }
  return `<ul class="mini-list">${values.map((item) => `<li>${escapeHtml(formatReportValue(item))}</li>`).join("")}</ul>`;
}

function renderRecommendationList(recommendations) {
  const values = normalizeItems(recommendations).map((item) => {
    if (item && typeof item === "object") {
      return item;
    }
    return {label: item};
  });
  if (!values.length) {
    return '<p class="muted compact-copy">暂无明确规则建议。</p>';
  }
  return `
    <ul class="quality-recommendation-list">
      ${values
        .map((item) => {
          const sourceIds = normalizeItems(item.source_issue_ids)
            .map((source) => String(source || "").trim())
            .filter(Boolean);
          return `
            <li class="quality-recommendation-item">
              <div class="quality-recommendation-title">
                <span class="status-pill">${escapeHtml(`P${item.priority ?? 0}`)}</span>
                <strong>${escapeHtml(item.label || item.id || "规则建议")}</strong>
              </div>
              ${item.reason ? `<p>${escapeHtml(item.reason)}</p>` : ""}
              ${item.action ? `<p class="recommendation-action">${escapeHtml(item.action)}</p>` : ""}
              ${
                sourceIds.length
                  ? `<p class="muted compact-copy">触发项：${escapeHtml(sourceIds.join(" / "))}</p>`
                  : ""
              }
              ${renderReadinessActionButton({
                label: item.action_label,
                target: item.action_target,
                mode: item.action_mode,
              })}
            </li>
          `;
        })
        .join("")}
    </ul>
  `;
}

function renderFieldRows(rows) {
  const filtered = rows.filter(([, value]) => value !== undefined && value !== null && value !== "");
  if (!filtered.length) {
    return '<p class="muted compact-copy">暂无。</p>';
  }
  return `
    <dl class="report-dl">
      ${filtered.map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(formatReportValue(value))}</dd>`).join("")}
    </dl>
  `;
}

function renderReportCard(title, body, tone = "") {
  return `
    <article class="analysis-report-card ${escapeHtml(tone)}">
      <h3>${escapeHtml(title)}</h3>
      ${body}
    </article>
  `;
}

function renderQualityChecks(checks) {
  const values = Array.isArray(checks) ? checks : [];
  if (!values.length) {
    return '<p class="muted compact-copy">暂无。</p>';
  }
  return `
    <div class="quality-check-list">
      ${values
        .map((check) => `
          <div class="quality-check ${check.passed ? "passed" : "failed"}">
            <div>
              <strong>${escapeHtml(check.label || "")}</strong>
              <p>${escapeHtml(check.message || "")}</p>
              ${check.passed ? "" : `<p class="muted compact-copy">建议：${escapeHtml(check.action || "")}</p>`}
            </div>
            <span>${escapeHtml(check.passed ? "通过" : "待补")}</span>
          </div>
        `)
        .join("")}
    </div>
  `;
}

function qualityGapCategory(gap) {
  const id = gap && gap.id ? gap.id : "";
  const categories = {
    summary: ["结论", "claim"],
    hook: ["钩子", "hook"],
    visual: ["画面", "visual"],
    copy_speech_text: ["文案/声音", "copy"],
    audience: ["评论", "comment"],
    evidence: ["证据", "evidence"],
    claim_traceability: ["结论证据", "trace"],
    visual_input: ["视觉输入", "visual"],
    evidence_gaps: ["证据缺口", "evidence"],
    evidence_confidence: ["置信度", "confidence"],
    model_confidence: ["模型置信度", "confidence"],
    engagement_data: ["互动数据", "evidence"],
    time_bounds: ["时间边界", "time"],
    structure_depth: ["结构", "structure"],
    content_ratio_balance: ["内容占比", "structure"],
    adaptation_boundary: ["改编边界", "boundary"],
    replication: ["复刻", "replication"],
    copyable_traceability: ["复刻来源", "trace"],
    shot_table_traceability: ["分镜来源", "trace"],
    publishing: ["发布", "publish"],
    enrichment_usage: ["富化证据", "evidence"],
    rerun_compliance: ["重跑合规", "trace"],
  };
  return categories[id] || ["待处理", "default"];
}

function renderQualityGapDetails(details) {
  const values = normalizeItems(details).filter((item) => item && typeof item === "object");
  if (!values.length) {
    return "";
  }
  return `
    <ul class="quality-gap-detail-list">
      ${values
        .map((item) => {
          const meta = [];
          if (item.location) {
            meta.push(item.location);
          }
          if (item.time !== undefined && item.limit !== undefined) {
            meta.push(`${item.time}s / 上限 ${item.limit}s`);
          }
          if (item.total !== undefined && item.limit !== undefined) {
            meta.push(`${item.total}% / 目标 ${item.limit}%`);
          }
          return `
            <li>
              <strong>${escapeHtml(item.label || item.id || "细节")}</strong>
              ${meta.length ? `<span>${escapeHtml(meta.join(" · "))}</span>` : ""}
              ${item.message ? `<p>${escapeHtml(item.message)}</p>` : ""}
            </li>
          `;
        })
        .join("")}
    </ul>
  `;
}

function renderQualityGapPanel(gaps) {
  const values = Array.isArray(gaps) ? gaps : [];
  if (!values.length) {
    return `
      <div class="quality-gap-panel complete">
        <strong>质量闸门已通过</strong>
        <p>当前报告没有阻塞项，结论、证据、复刻点和分镜表可以进入人工筛选。</p>
      </div>
    `;
  }
  return `
    <div class="quality-gap-panel">
      <div class="quality-gap-heading">
        <strong>优先质量缺口</strong>
        <span>${escapeHtml(values.length)} 项</span>
      </div>
      <div class="quality-gap-list">
        ${values
          .map((gap) => {
            const [label, tone] = qualityGapCategory(gap);
            return `
              <article class="quality-gap-item ${escapeHtml(tone)}">
                <div class="quality-gap-label">${escapeHtml(label)}</div>
                <div>
                  <strong>${escapeHtml(gap.label || gap.id || "待处理")}</strong>
                  <p>${escapeHtml(gap.message || "")}</p>
                  ${renderQualityGapDetails(gap.details)}
                  <p class="quality-gap-action">${escapeHtml(gap.action || "")}</p>
                </div>
              </article>
            `;
          })
          .join("")}
      </div>
    </div>
  `;
}

function renderEvidencePill(label, items, strong = false) {
  const count = normalizeItems(items).length;
  return `<span class="evidence-pill ${strong && count ? "active" : ""}">${escapeHtml(label)} ${escapeHtml(count)}</span>`;
}

const coverageVerdictLabels = {
  used: "已使用",
  checked_empty: "已检测为空",
  available_not_used: "可用未使用",
  evidence_without_insight: "有证据无洞察",
  insight_without_evidence: "有洞察无证据",
  empty_result: "结果为空",
  provider_missing: "未配置",
  missing: "缺失",
};

const diagnosisSourceLabels = {
  enrichment: "富化证据",
  ai_quality: "AI 自检",
  readiness: "准备度",
  human_acceptance: "人工验收",
  complete: "诊断",
};

function renderEnrichmentCoverage(coverage) {
  const items = (coverage && coverage.items) || {};
  const rows = [
    ["asr", "ASR"],
    ["ocr", "OCR"],
    ["comments", "评论"],
  ];
  if (!rows.some(([key]) => items[key])) {
    return '<p class="muted compact-copy">暂无富化证据核对。</p>';
  }
  return `
    <div class="enrichment-coverage-list">
      ${rows
        .map(([key, fallbackLabel]) => {
          const item = items[key] || {};
          const verdict = item.verdict || "missing";
          return `
            <article class="enrichment-coverage-item ${escapeHtml(verdict)}">
              <div>
                <strong>${escapeHtml(item.label || fallbackLabel)}</strong>
                <p>${escapeHtml(item.message || "")}</p>
                ${item.action ? `<p class="quality-gap-action">${escapeHtml(item.action)}</p>` : ""}
              </div>
              <dl>
                <dt>状态</dt><dd>${escapeHtml(coverageVerdictLabels[verdict] || verdict)}</dd>
                <dt>证据</dt><dd>${escapeHtml(item.evidence_count ?? 0)}</dd>
                <dt>洞察</dt><dd>${item.insight_ready ? "有" : "无"}</dd>
              </dl>
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderRerunCompliance(compliance) {
  const data = compliance || {};
  const checks = normalizeItems(data.checks || []);
  const failedChecks = checks.filter((check) => check && check.passed === false);
  if (!data.active) {
    return `
      ${renderFieldRows([
        ["状态", data.status || "not_required"],
        ["结论", data.summary || "当前没有启用带反馈重跑策略。"],
      ])}
      <p class="muted compact-copy">没有人工反馈重跑约束时，不需要合规检查。</p>
    `;
  }
  return `
    ${renderFieldRows([
      ["状态", data.status || ""],
      ["合规分", `${data.score ?? 0} / 100`],
      ["阻塞项", `${data.blocking_count ?? failedChecks.length} 项`],
      ["结论", data.summary || ""],
    ])}
    <h4>未通过约束</h4>
    ${failedChecks.length ? renderQualityChecks(failedChecks) : '<p class="muted compact-copy">暂无未通过约束。</p>'}
    <h4>全部约束</h4>
    ${renderQualityChecks(checks)}
  `;
}

function renderAutoAnalysisOverview(result, readiness) {
  const hook = result.hook_analysis || {};
  const replication = result.replication || {};
  const evidence = result.evidence_summary || {};
  const enrichmentCoverage = result.enrichment_coverage || {};
  const quality = result.quality_review || {};
  const rerunCompliance = result.rerun_compliance || {};
  const qualityGaps = normalizeItems(quality.gaps);
  const evidenceGaps = normalizeItems(evidence.evidence_gaps);
  const criticalGaps = normalizeItems(readiness.critical_gaps);
  const criticalGapSummaries = criticalGaps.map((gap) => `${gap.label || ""}：${gap.action || gap.message || ""}`);
  const nextActions = normalizeItems(quality.next_actions).length
    ? quality.next_actions
    : readiness.next_actions || result.next_actions || [];

  return `
    <div class="analysis-trust-panel ${escapeHtml(quality.level || "unknown")}">
      <div class="analysis-trust-score">
        <span>${escapeHtml(quality.score ?? 0)}</span>
        <small>/ ${escapeHtml(quality.max_score ?? 100)}</small>
      </div>
      <div>
        <strong>${escapeHtml(quality.label || "拆解质量待确认")}</strong>
        <p>${escapeHtml(quality.summary || "尚未生成质量自检。")}</p>
      </div>
    </div>
    <div class="analysis-trust-grid">
      <div class="analysis-trust-card">
        <strong>结论速览</strong>
        ${renderFieldRows([
          ["一句话总结", result.summary || ""],
          ["内容类型", result.content_category_label || result.content_category || ""],
          ["置信度", result.confidence ?? ""],
          ["停留理由", hook.why_stop_scrolling || ""],
          ["复刻角度", replication.remake_angle || ""],
        ])}
      </div>
      <div class="analysis-trust-card">
        <strong>证据覆盖</strong>
        <div class="evidence-pill-row">
          ${renderEvidencePill("视觉", evidence.visual_evidence, true)}
          ${renderEvidencePill("ASR", evidence.asr_evidence, true)}
          ${renderEvidencePill("OCR", evidence.ocr_evidence, true)}
          ${renderEvidencePill("评论", evidence.comment_evidence, true)}
          ${renderEvidencePill("推断", evidence.inferred_points)}
          ${renderEvidencePill("缺口", evidenceGaps, true)}
        </div>
        ${renderFieldRows([
          ["视觉输入", evidence.visual_input_mode || ""],
          ["富化阻塞", `${(enrichmentCoverage.summary || {}).blocking_count || 0} 项`],
          ["重跑合规", rerunCompliance.active ? `${rerunCompliance.score ?? 0} / 100` : "未启用"],
          ["质量缺口", qualityGaps.length ? `${qualityGaps.length} 项` : "无"],
          ["准备度关键缺口", criticalGaps.length ? `${criticalGaps.length} 项` : "无"],
        ])}
        <h4>富化证据使用</h4>
        ${renderEnrichmentCoverage(enrichmentCoverage)}
      </div>
      <div class="analysis-trust-card action-card">
        <strong>关键缺口与下一步</strong>
        ${renderQualityGapPanel(qualityGaps)}
        <h4>准备度关键缺口</h4>
        ${renderMiniList(criticalGapSummaries.length ? criticalGapSummaries : ["无关键缺口"])}
        <h4>建议动作</h4>
        ${renderMiniList(nextActions)}
      </div>
    </div>
  `;
}

function errorAdvice(code) {
  const advice = {
    LLM_NOT_CONFIGURED: "请在 .env 中配置 LLM_PROVIDER、LLM_API_BASE、LLM_API_KEY 和 LLM_MODEL，然后重启服务。",
    LLM_REQUEST_FAILED: "请检查 API Base、API Key、网络、账户余额和模型名是否正确。",
    LLM_RESPONSE_INVALID: "模型没有返回合法 JSON。可以降低 LLM_TEMPERATURE，或换支持图片输入且 JSON 更稳定的模型。",
    AUTO_ANALYSIS_FAILED: "请确认 contact_sheet.jpg 和 keyframes/ 已生成，再重新分析。",
    ENRICHMENT_FAILED: "请确认 metadata.json、ffprobe.json 和 analysis_input.json 都已生成。",
    COMMENTS_IMPORT_FAILED: "请检查评论文本是否为空，或每行 JSON 是否包含 text 字段。",
    ASR_PROVIDER_NOT_CONFIGURED: "请安装 requirements-asr.txt，并在 .env 中设置 ASR_PROVIDER=faster_whisper。",
    ASR_FAILED: "请检查视频是否有音轨、ffmpeg 是否可用，以及 ASR 模型配置是否正确。",
    OCR_PROVIDER_NOT_CONFIGURED: "请安装 requirements-ocr.txt，并在 .env 中设置 OCR_PROVIDER=rapidocr。",
    OCR_FAILED: "请检查 keyframes/ 是否存在，以及 OCR provider 配置是否正确。",
  };
  return advice[code] || "";
}

function renderLlmStatus(llm) {
  const configured = Boolean(llm.configured);
  caseLlmStatus.innerHTML = `
    <strong>${configured ? "AI 自动拆解已启用" : "素材包已生成，但 AI 自动拆解未启用"}</strong>
    <div class="compact-dl">
      <dl>
        <dt>Provider</dt><dd>${escapeHtml(llm.provider || "disabled")}</dd>
        <dt>API Base</dt><dd>${escapeHtml(llm.api_base || "")}</dd>
        <dt>Model</dt><dd>${escapeHtml(llm.model || "未配置")}</dd>
        <dt>API Key</dt><dd>${llm.has_api_key ? `已配置 ${escapeHtml(llm.masked_api_key || "")}` : "未配置"}</dd>
        <dt>图片帧数</dt><dd>${escapeHtml(llm.llm_max_keyframes ?? "")}</dd>
      </dl>
    </div>
    <p class="muted compact-copy">${escapeHtml(llm.status_message || "")}</p>
  `;
  runAutoAnalysisButton.disabled = !configured;
  saveQualityAcceptanceAndRerunButton.disabled = !configured;
}

function renderArtifactOverview(data) {
  const descriptions = data.artifact_descriptions || {};
  const paths = data.paths || {};
  const keyframes = data.artifact_urls?.keyframes || [];
  const items = [
    ["video.mp4", paths.video],
    ["metadata.json", paths.metadata],
    ["qualities.json", paths.qualities],
    ["ffprobe.json", paths.ffprobe],
    ["contact_sheet.jpg", paths.contact_sheet],
    ["keyframes/", `${paths.keyframes_dir || ""}（${keyframes.length} 张）`],
    ["analysis_input.json", paths.analysis_input],
    ["prompt.md", paths.prompt],
    ["worksheet.json", paths.worksheet],
    ["quality_acceptance.json", paths.quality_acceptance],
    ["quality_calibration_record.json", paths.quality_calibration_record],
    ["rerun_plan.json", paths.rerun_plan],
    ["rerun_plan.md", paths.rerun_plan_markdown],
    ["analysis_brief.md", paths.analysis_brief],
    ["analysis_result.json", data.analysis_result ? paths.analysis_result : "尚未生成"],
    ["analysis_report.md", data.analysis_report ? paths.analysis_report : "尚未生成"],
  ];
  artifactOverview.innerHTML = items
    .map(([name, path]) => `
      <div class="artifact-item">
        <strong>${escapeHtml(name)}</strong>
        <p>${escapeHtml(descriptions[name] || "")}</p>
        <p class="muted compact-copy">${escapeHtml(path || "")}</p>
      </div>
    `)
    .join("");
}

function findProfile(categoryId) {
  return (loadedCase.analysis_profiles || []).find((profile) => profile.category_id === categoryId);
}

function renderCategoryControls(analysisInput) {
  const currentCategory = analysisInput.content_category || "generic";
  analysisCategorySelect.innerHTML = (loadedCase.analysis_profiles || [])
    .map((profile) => {
      const selected = profile.category_id === currentCategory ? " selected" : "";
      return `<option value="${escapeHtml(profile.category_id)}"${selected}>${escapeHtml(profile.label)}</option>`;
    })
    .join("");
  const context = analysisInput.analysis_context || {};
  const profile = findProfile(currentCategory);
  categoryDescription.textContent = context.description || (profile ? profile.description : "");
}

function buildAnalysisHints(metadata, ffprobe, analysisInput) {
  const stats = analysisInput.stats || {};
  const video = analysisInput.video || {};
  const assets = analysisInput.assets || {};
  const duration = Number(video.duration || ffprobe.duration || 0);
  const width = Number(video.width || ffprobe.width || 0);
  const height = Number(video.height || ffprobe.height || 0);
  const frameCount = (assets.keyframes || []).length;
  const missingStats = !Number(stats.like_count) && !Number(stats.comment_count) && !Number(stats.share_count);
  const warnings = [];

  if (missingStats) {
    warnings.push("互动数据为空：当前只能分析内容结构，不能判断真实爆款强度。");
  }
  if (!metadata.aweme_id && !analysisInput.aweme_id) {
    warnings.push("作品 ID 缺失：建议重新生成素材包，便于后续和原作品对照。");
  }
  if (duration && duration < 8) {
    warnings.push("视频很短：重点看 0-3 秒是否直接给出人物、情绪或反差。");
  }
  if (width && height && height > width) {
    warnings.push("竖屏视频：适合拆解封面第一眼、人物居中、近景表情和手机端占屏效果。");
  }

  return {
    frameCount,
    warnings,
    rows: [
      ["素材类型", metadata.source_url ? "抖音单作品导入后下载" : "本地视频"],
      ["分析类型", analysisInput.content_category_label || analysisInput.analysis_context?.label || "通用短视频"],
      ["内容判断", missingStats ? "内容结构分析样本" : "可结合互动数据判断爆款强度"],
      ["前 3 秒样本", `${Math.min(frameCount, 4)} 张关键帧可观察`],
      ["视频长度", formatSeconds(duration)],
      ["画面规格", width && height ? `${width}x${height}` : "未知"],
      ["文件大小", formatBytes(video.file_size || ffprobe.file_size)],
      ["下一步", "点击上方按钮复制完整 Prompt，并把 contact_sheet.jpg 一起交给 LLM。"],
      ["注意", warnings.join(" ")],
    ],
  };
}

function renderKeyframes(loadedCase, analysisInput) {
  const keyframeUrls = loadedCase.artifact_urls.keyframes || [];
  const frames = analysisInput.assets && analysisInput.assets.keyframes ? analysisInput.assets.keyframes : [];
  const frameByFilename = new Map(
    frames.map((frame) => {
      const parts = String(frame.path || "").split("/");
      return [parts[parts.length - 1], frame];
    }),
  );

  if (!keyframeUrls.length) {
    keyframeStrip.textContent = "没有可展示的关键帧。";
    return;
  }

  keyframeStrip.innerHTML = keyframeUrls
    .map((item) => {
      const frame = frameByFilename.get(item.filename) || {};
      const timestamp = Number(frame.timestamp || 0);
      return `
        <a class="keyframe-card" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">
          <img src="${escapeHtml(item.url)}" alt="${escapeHtml(item.filename)}">
          <span>${timestamp.toFixed(2)}s</span>
        </a>
      `;
    })
    .join("");
}

function renderWorksheetReview(review) {
  const payload = review || {};
  worksheetReview.innerHTML = `
    <div class="analysis-trust-panel ${escapeHtml(payload.level || "empty")}">
      <div class="analysis-trust-score">
        <span>${escapeHtml(payload.score ?? 0)}</span>
        <small>/ ${escapeHtml(payload.max_score ?? 100)}</small>
      </div>
      <div>
        <strong>${escapeHtml(payload.label || "待开始人工拆解")}</strong>
        <p>${escapeHtml(payload.summary || "先补齐前 3 秒钩子、内容结构和复刻方案。")}</p>
      </div>
    </div>
    <div class="worksheet-review-grid">
      ${renderQualityChecks(payload.checks || [])}
      <div class="analysis-trust-card">
        <strong>下一步建议</strong>
        ${renderMiniList(payload.next_actions)}
      </div>
    </div>
  `;
}

function renderWorksheet(worksheet, review) {
  renderWorksheetReview(review || worksheet.review || {});
  worksheetSummary.value = worksheet.summary || "";
  const sections = worksheet.sections || {};
  worksheetSections.innerHTML = Object.entries(sections)
    .map(([sectionId, section]) => {
      const fields = section.fields || {};
      const fieldHtml = Object.entries(fields)
        .map(([fieldId, field]) => `
          <label>${escapeHtml(field.label || fieldId)}
            ${field.hint ? `<span class="field-hint">${escapeHtml(field.hint)}</span>` : ""}
            <textarea
              rows="4"
              data-section-id="${escapeHtml(sectionId)}"
              data-field-id="${escapeHtml(fieldId)}"
              placeholder="${escapeHtml(field.hint || "填写你的观察和判断...")}"
            >${escapeHtml(field.value || "")}</textarea>
          </label>
        `)
        .join("");
      return `
        <div class="worksheet-section">
          <h3>${escapeHtml(section.title || sectionId)}</h3>
          <div class="worksheet-fields">${fieldHtml}</div>
        </div>
      `;
    })
    .join("");
}

const qualityAcceptanceCheckLabels = {
  summary_matches_video: "总结是否符合视频",
  evidence_is_sufficient: "证据是否足够",
  copyable_points_are_useful: "可复刻点是否有用",
  shot_table_is_actionable: "分镜表是否可执行",
  publish_package_is_usable: "发布包是否可用",
};

const qualityAcceptanceVerdictLabels = {
  pending: "待验收",
  pass: "通过，可作为样例",
  needs_fix: "需要修正",
  reject: "不通过",
};

function renderQualityAcceptance(acceptance) {
  const payload = acceptance || {};
  const snapshot = payload.quality_snapshot || {};
  qualityAcceptanceSummary.innerHTML = `
    <div class="acceptance-overview ${escapeHtml(payload.verdict || "pending")}">
      <div>
        <strong>${escapeHtml(qualityAcceptanceVerdictLabels[payload.verdict] || "待验收")}</strong>
        <p>${escapeHtml(payload.summary || "尚未记录人工验收。")}</p>
      </div>
      <dl>
        <dt>AI 分数</dt><dd>${escapeHtml(snapshot.score ?? 0)}</dd>
        <dt>AI 等级</dt><dd>${escapeHtml(snapshot.label || snapshot.level || "")}</dd>
        <dt>AI 缺口</dt><dd>${escapeHtml((snapshot.gap_ids || []).join(" / ") || "无")}</dd>
      </dl>
    </div>
  `;
  qualityAcceptanceVerdict.value = payload.verdict || "pending";
  qualityAcceptanceScore.value = payload.score || "";
  qualityAcceptanceReviewer.value = payload.reviewer || "";
  qualityAcceptanceSummaryInput.value = payload.summary || "";
  qualityAcceptanceNotes.value = payload.notes || "";
  qualityAcceptanceNextActions.value = payload.next_actions || "";
  const checks = payload.checks || {};
  qualityAcceptanceChecks.innerHTML = Object.entries(qualityAcceptanceCheckLabels)
    .map(([key, label]) => `
      <label>${escapeHtml(label)}
        <select data-acceptance-check="${escapeHtml(key)}">
          <option value="">未判断</option>
          <option value="pass"${checks[key] === "pass" ? " selected" : ""}>通过</option>
          <option value="needs_fix"${checks[key] === "needs_fix" ? " selected" : ""}>需修正</option>
          <option value="reject"${checks[key] === "reject" ? " selected" : ""}>不通过</option>
        </select>
      </label>
    `)
    .join("");
}

function currentRerunStrategy(data) {
  const direct = data.manual_review_context && data.manual_review_context.rerun_strategy;
  const analyzed = data.analysis_result
    && data.analysis_result.manual_review_context
    && data.analysis_result.manual_review_context.rerun_strategy;
  return direct || analyzed || {};
}

function renderRerunEvidenceMeta(item) {
  const rows = [];
  if (item.char_count !== undefined && item.char_count !== null && item.char_count !== "") {
    rows.push(["文本字数", item.char_count]);
  }
  if (item.segment_count !== undefined && item.segment_count !== null && item.segment_count !== "") {
    rows.push(["ASR 分段", item.segment_count]);
  }
  if (item.count !== undefined && item.count !== null && item.count !== "") {
    rows.push(["评论数量", item.count]);
  }
  if (Array.isArray(item.sources) && item.sources.length) {
    rows.push(["OCR 来源", item.sources.join(" / ")]);
  }
  if (!rows.length && !item.excerpt) {
    return "";
  }
  return `
    <div class="rerun-evidence-meta">
      ${
        rows.length
          ? `<dl>${rows.map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(formatReportValue(value))}</dd>`).join("")}</dl>`
          : ""
      }
      ${item.excerpt ? `<p class="rerun-evidence-excerpt">${escapeHtml(item.excerpt)}</p>` : ""}
    </div>
  `;
}

function renderRerunEvidenceSummary(strategy) {
  const summary = strategy.evidence_summary || {};
  const total = Number(summary.total || 0);
  if (!total) {
    return '<p class="muted compact-copy">暂无必须核对的证据。</p>';
  }
  const ready = Number(summary.ready || 0);
  const missing = Number(summary.missing || 0);
  return `
    <div class="rerun-evidence-summary ${missing ? "has-missing" : "complete"}">
      <div><strong>${escapeHtml(ready)}</strong><span>已就绪</span></div>
      <div><strong>${escapeHtml(missing)}</strong><span>仍缺失</span></div>
      <div><strong>${escapeHtml(total)}</strong><span>总证据</span></div>
    </div>
  `;
}

function renderStrategyCards(items, emptyText) {
  const values = normalizeItems(items);
  if (!values.length) {
    return `<p class="muted compact-copy">${escapeHtml(emptyText || "暂无。")}</p>`;
  }
  return values
    .map((item) => {
      if (!item || typeof item !== "object") {
        return `<article class="rerun-strategy-item"><p>${escapeHtml(formatReportValue(item))}</p></article>`;
      }
      return `
        <article class="rerun-strategy-item ${escapeHtml(item.status || "")}">
          <div class="rerun-strategy-item-title">
            <strong>${escapeHtml(item.label || item.id || "待处理项")}</strong>
            ${item.status ? `<span class="status-pill ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span>` : ""}
          </div>
          <p>${escapeHtml(item.instruction || item.message || item.action || item.output || "")}</p>
          ${renderRerunEvidenceMeta(item)}
          ${item.source ? `<small>${escapeHtml(item.source)}</small>` : ""}
          ${renderReadinessActionButton({
            label: item.action_label || "",
            target: item.target || item.action_target || "",
            mode: item.mode || "focus",
          }, "primary-action")}
        </article>
      `;
    })
    .join("");
}

function missingRerunEvidence(strategy) {
  const missingStatuses = new Set(["missing", "provider_missing", "pending", "disabled", "not_configured"]);
  return normalizeItems(strategy.required_evidence)
    .filter((item) => item && typeof item === "object" && missingStatuses.has(String(item.status || "")));
}

function renderRerunEvidenceWarning(strategy) {
  const missing = missingRerunEvidence(strategy);
  if (!missing.length) {
    return "";
  }
  return `
    <div class="rerun-evidence-warning">
      <strong>先补证据会更准</strong>
      <p>当前策略仍缺 ${escapeHtml(missing.map((item) => item.label || item.id || "证据").join(" / "))}。你可以继续重跑，但补齐后再跑通常更稳定。</p>
    </div>
  `;
}

function confirmMissingEvidenceBeforeRerun(data) {
  const strategy = currentRerunStrategy(data || {});
  const missing = missingRerunEvidence(strategy);
  if (!missing.length) {
    return true;
  }
  const labels = missing.map((item) => item.label || item.id || "证据").join(" / ");
  return window.confirm(
    `重跑策略提示：当前仍缺 ${labels}。\n\n先补齐这些证据会让拆解更准。选择“确定”继续重跑；选择“取消”先补证据。`,
  );
}

function renderRerunStrategy(data) {
  const strategy = currentRerunStrategy(data || {});
  if (!strategy.active) {
    rerunStrategyPanel.innerHTML = `
      <div class="rerun-strategy-empty">
        <strong>尚未生成带反馈重跑策略</strong>
        <p>保存人工质量验收后，系统会把需修正项、禁止重复的问题、必须核对的证据和输出要求整理到这里。</p>
      </div>
    `;
    return;
  }
  rerunStrategyPanel.innerHTML = `
    <div class="rerun-strategy-hero ${escapeHtml(strategy.priority || "normal")}">
      <div>
        <span class="status-pill ${escapeHtml(strategy.priority || "normal")}">${escapeHtml(strategy.priority || "normal")}</span>
        <strong>${escapeHtml(strategy.summary || "本次重跑会按人工反馈修正。")}</strong>
      </div>
      <p>点击“保存并重新拆解”时，这些策略会进入下一次 AI prompt，避免盲目重跑。</p>
    </div>
    ${renderRerunEvidenceWarning(strategy)}
    ${renderRerunEvidenceSummary(strategy)}
    <div class="rerun-strategy-grid">
      <section>
        <h3>修正目标</h3>
        ${renderStrategyCards(strategy.fix_targets, "暂无明确修正目标。")}
      </section>
      <section>
        <h3>必须核对证据</h3>
        ${renderStrategyCards(strategy.required_evidence, "暂无额外证据要求。")}
      </section>
      <section>
        <h3>禁止重复</h3>
        ${renderMiniList(strategy.do_not_repeat)}
      </section>
      <section>
        <h3>输出要求</h3>
        ${renderMiniList(strategy.output_requirements)}
      </section>
    </div>
  `;
}

function collectQualityAcceptance() {
  const source = loadedCase.quality_acceptance || {};
  const checks = {};
  qualityAcceptanceChecks.querySelectorAll("[data-acceptance-check]").forEach((select) => {
    checks[select.dataset.acceptanceCheck] = select.value;
  });
  return {
    ...source,
    verdict: qualityAcceptanceVerdict.value,
    score: qualityAcceptanceScore.value,
    reviewer: qualityAcceptanceReviewer.value,
    summary: qualityAcceptanceSummaryInput.value,
    checks,
    notes: qualityAcceptanceNotes.value,
    next_actions: qualityAcceptanceNextActions.value,
  };
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

function renderPublicAnalysisHero(result) {
  const category = result.content_category_label || result.content_category || "短视频";
  const confidence = result.confidence ? `置信度 ${result.confidence}` : "";
  return `
    <section class="public-analysis-hero">
      <span>${escapeHtml(category)}${confidence ? ` · ${escapeHtml(confidence)}` : ""}</span>
      <strong>${escapeHtml(result.summary || "AI 已完成拆解，但没有返回摘要。")}</strong>
    </section>
  `;
}

function renderPublicAnalysisCards(result) {
  const hook = result.hook_analysis || {};
  const visual = result.visual_analysis || {};
  const replication = result.replication || {};
  const publish = result.publish_package || {};
  return `
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

function renderAutoAnalysis(data) {
  const result = data.analysis_result || null;
  const report = data.analysis_report || "";
  if (!result) {
    const configured = Boolean(data.llm_settings && data.llm_settings.configured);
    autoAnalysisStatus.textContent = configured
      ? "尚未生成 AI 自动拆解。可以点击“开始 AI 自动拆解”。"
      : "尚未生成 AI 自动拆解；你仍然可以复制 prompt.md 或下载 analysis_input.json 手动分析。";
    autoAnalysisSummary.innerHTML = "";
    autoAnalysisCards.innerHTML = "";
    autoAnalysisReport.textContent = "";
    copyAiReportButton.disabled = true;
    runAutoAnalysisButton.textContent = "开始 AI 自动拆解";
    return;
  }
  autoAnalysisStatus.textContent = "AI 自动拆解已生成。";
  copyAiReportButton.disabled = false;
  runAutoAnalysisButton.textContent = "重新 AI 自动拆解";
  autoAnalysisSummary.innerHTML = renderPublicAnalysisHero(result);
  autoAnalysisCards.innerHTML = renderPublicAnalysisCards(result);
  autoAnalysisReport.textContent = report || JSON.stringify(result, null, 2);
}

function renderAutoAnalysisCards(result) {
  const hook = result.hook_analysis || {};
  const visual = result.visual_analysis || {};
  const copywriting = result.copywriting_analysis || {};
  const speech = result.speech_analysis || {};
  const screenText = result.screen_text_analysis || {};
  const comments = result.comment_insights || {};
  const replication = result.replication || {};
  const publish = result.publish_package || {};
  const enrichmentUsage = result.enrichment_usage || {};
  const enrichmentCoverage = result.enrichment_coverage || {};
  const rerunCompliance = result.rerun_compliance || {};
  const evidence = result.evidence_summary || {};
  const quality = result.quality_review || {};
  const shotTable = normalizeItems(replication.shot_table);
  const timeline = normalizeItems(result.timeline);

  autoAnalysisCards.innerHTML = [
    renderReportCard(
      "拆解质量自检",
      `
        ${renderFieldRows([
          ["质量分", `${quality.score ?? 0} / ${quality.max_score ?? 100}`],
          ["等级", quality.label],
          ["结论", quality.summary],
        ])}
        <h4>优先缺口</h4>
        ${renderQualityGapPanel(quality.gaps)}
        <h4>模块检查</h4>
        ${renderQualityChecks(quality.checks)}
        <h4>建议动作</h4>
        ${renderMiniList(quality.next_actions)}
      `,
      "quality-card",
    ),
    renderReportCard(
      "重跑合规",
      renderRerunCompliance(rerunCompliance),
      rerunCompliance.active && rerunCompliance.status !== "passed" ? "quality-card" : "",
    ),
    renderReportCard(
      "证据与推断边界",
      `
        ${renderFieldRows([
          ["视觉输入", evidence.visual_input_mode],
        ])}
        <h4>视觉证据</h4>
        ${renderMiniList(evidence.visual_evidence)}
        <h4>ASR 证据</h4>
        ${renderMiniList(evidence.asr_evidence)}
        <h4>OCR 证据</h4>
        ${renderMiniList(evidence.ocr_evidence)}
        <h4>评论证据</h4>
        ${renderMiniList(evidence.comment_evidence)}
        <h4>富化证据使用</h4>
        ${renderEnrichmentCoverage(enrichmentCoverage)}
        <h4>推断点</h4>
        ${renderMiniList(evidence.inferred_points)}
        <h4>证据缺口</h4>
        ${renderMiniList(evidence.evidence_gaps)}
      `,
      "evidence-card",
    ),
    renderReportCard(
      "前 3 秒钩子",
      `
        ${renderFieldRows([
          ["第一眼", hook.first_impression],
          ["停留理由", hook.why_stop_scrolling],
          ["优化", hook.optimization],
        ])}
        <h4>逐秒观察</h4>
        ${renderMiniList(hook.first_3_seconds)}
      `,
      "primary-card",
    ),
    renderReportCard(
      "视觉节奏",
      renderFieldRows([
        ["场景", visual.scene],
        ["主体", visual.subject],
        ["构图", visual.composition],
        ["光色", visual.lighting_color],
        ["运动节奏", visual.movement_rhythm],
        ["风格词", visual.style_keywords],
      ]),
    ),
    renderReportCard(
      "文案与字幕",
      `
        ${renderFieldRows([
          ["标题点击理由", copywriting.title_click_reason],
          ["字幕/文字作用", copywriting.subtitle_or_text_role],
          ["评论触发", copywriting.comment_trigger],
        ])}
        <h4>可复用模式</h4>
        ${renderMiniList(copywriting.reusable_patterns)}
      `,
    ),
    renderReportCard(
      "语音/口播",
      `
        ${renderFieldRows([
          ["是否有口播", speech.has_speech === true ? "是" : speech.has_speech === false ? "否" : ""],
          ["开头一句", speech.opening_line],
          ["口播钩子", speech.spoken_hook],
          ["脚本结构", speech.script_structure],
        ])}
        <h4>金句</h4>
        ${renderMiniList(speech.quotable_lines)}
      `,
    ),
    renderReportCard(
      "画面文字/OCR",
      `
        ${renderFieldRows([
          ["封面文字作用", screenText.cover_text_role],
          ["字幕文字作用", screenText.subtitle_text_role],
        ])}
        <h4>文字模式</h4>
        ${renderMiniList(screenText.screen_text_patterns)}
        <h4>文字和画面冲突</h4>
        ${renderMiniList(screenText.text_visual_conflicts)}
      `,
    ),
    renderReportCard(
      "评论反馈",
      `
        ${renderFieldRows([
          ["互动设计", comments.replicable_interaction_design],
        ])}
        <h4>用户需求</h4>
        ${renderMiniList(comments.audience_needs)}
        <h4>评论触发点</h4>
        ${renderMiniList(comments.comment_triggers)}
        <h4>高频词</h4>
        ${renderMiniList(comments.high_frequency_words)}
      `,
    ),
    renderReportCard(
      "复刻方案",
      `
        ${renderFieldRows([
          ["复刻角度", replication.remake_angle],
          ["3 秒开头", replication.opening_3s],
        ])}
        <h4>可借鉴点</h4>
        ${renderMiniList(replication.copyable_points)}
        <h4>不要照搬</h4>
        ${renderMiniList(replication.avoid_copying)}
        <h4>分镜表</h4>
        ${renderShotTable(shotTable)}
      `,
      "primary-card",
    ),
    renderReportCard(
      "发布包",
      `
        ${renderFieldRows([
          ["发布文案", publish.caption],
          ["置顶评论", publish.pinned_comment],
        ])}
        <h4>标题</h4>
        ${renderMiniList(publish.titles)}
        <h4>标签</h4>
        ${renderMiniList(publish.hashtags)}
      `,
    ),
    renderReportCard(
      "时间线 / 情绪路径",
      `
        <h4>情绪路径</h4>
        ${renderMiniList(result.emotion_path)}
        <h4>时间线</h4>
        ${renderMiniList(timeline)}
        <h4>内容占比</h4>
        ${renderMiniList(result.content_ratio)}
      `,
    ),
    renderReportCard(
      "风险与下一步",
      `
        ${renderFieldRows([
          ["ASR 使用", enrichmentUsage.asr_used === true ? "是" : enrichmentUsage.asr_used === false ? "否" : ""],
          ["OCR 使用", enrichmentUsage.ocr_used === true ? "是" : enrichmentUsage.ocr_used === false ? "否" : ""],
          ["评论使用", enrichmentUsage.comments_used === true ? "是" : enrichmentUsage.comments_used === false ? "否" : ""],
        ])}
        <h4>富化说明</h4>
        ${renderMiniList(enrichmentUsage.notes)}
        <h4>风险</h4>
        ${renderMiniList(result.risks)}
        <h4>下一步</h4>
        ${renderMiniList(result.next_actions)}
      `,
    ),
  ].join("");
}

function renderShotTable(rows) {
  if (!rows.length) {
    return '<p class="muted compact-copy">暂无。</p>';
  }
  return `
    <div class="shot-table-wrap">
      <table class="shot-table">
        <thead>
          <tr>
            <th>时间</th>
            <th>画面</th>
            <th>动作</th>
            <th>字幕</th>
            <th>节奏</th>
            <th>目的</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map((row) => `
              <tr>
                <td>${escapeHtml(row.time || "")}</td>
                <td>${escapeHtml(row.visual || "")}</td>
                <td>${escapeHtml(row.action || "")}</td>
                <td>${escapeHtml(row.subtitle || "")}</td>
                <td>${escapeHtml(row.music_rhythm || "")}</td>
                <td>${escapeHtml(row.purpose || "")}</td>
              </tr>
            `)
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderStatusPills(statuses) {
  const entries = Object.entries(statuses || {});
  if (!entries.length) {
    return '<span class="status-pill muted-pill">pending</span>';
  }
  return entries
    .map(([name, status]) => `<span class="status-pill ${escapeHtml(status)}">${escapeHtml(name)}：${escapeHtml(status)}</span>`)
    .join("");
}

function renderReadinessActionButton(action, className = "") {
  if (!action || !action.target || !action.label) {
    return "";
  }
  const mode = action.mode === "click" ? "click" : "focus";
  return `
    <button type="button" class="readiness-action-button ${escapeHtml(className)}" data-action-target="${escapeHtml(action.target)}" data-action-mode="${escapeHtml(mode)}">
      ${escapeHtml(action.label)}
    </button>
  `;
}

function renderCriticalGaps(gaps) {
  const values = Array.isArray(gaps) ? gaps : [];
  if (!values.length) {
    return `
      <div class="readiness-critical-gaps complete">
        <div>
          <strong>关键证据已齐</strong>
          <p>基础素材、分析镜头和核心拆解输入没有阻塞项，可以进入更细的内容判断。</p>
        </div>
      </div>
    `;
  }
  return `
    <div class="readiness-critical-gaps">
      <div class="readiness-critical-heading">
        <strong>关键缺口</strong>
        <span>${escapeHtml(values.length)} 项影响完整度</span>
      </div>
      <div class="readiness-critical-list">
        ${values
          .map((gap) => `
            <div class="readiness-critical-item">
              <div>
                <strong>${escapeHtml(gap.label || "")}</strong>
                <p>${escapeHtml(gap.action || gap.message || "")}</p>
              </div>
              ${renderReadinessActionButton({label: gap.action_label, target: gap.action_target}, "primary-action")}
            </div>
          `)
          .join("")}
      </div>
    </div>
  `;
}

function activateReadinessTarget(targetSelector, actionMode = "focus") {
  if (!targetSelector) {
    return;
  }
  if (targetSelector.startsWith("/")) {
    window.location.href = targetSelector;
    return;
  }
  const target = document.querySelector(targetSelector);
  if (!target) {
    return;
  }
  target.scrollIntoView({behavior: "smooth", block: "center"});
  window.setTimeout(() => {
    if (typeof target.focus === "function" && !target.disabled) {
      target.focus({preventScroll: true});
    }
    if (actionMode === "click" && typeof target.click === "function" && !target.disabled) {
      target.click();
    }
    target.classList.add("target-pulse");
    window.setTimeout(() => {
      target.classList.remove("target-pulse");
    }, 1600);
  }, 350);
}

function renderDiagnosisActions(actions) {
  const values = normalizeItems(actions);
  if (!values.length) {
    return '<p class="muted compact-copy">暂无动作建议，可以继续人工复核或保存校准样本。</p>';
  }
  const [featured, ...secondary] = values;
  return `
    <div class="case-diagnosis-featured-action">
      <span>推荐动作</span>
      <strong>${escapeHtml(featured.label || "下一步")}</strong>
      <p>${escapeHtml(featured.description || "")}</p>
      ${renderReadinessActionButton(featured, "primary-action")}
    </div>
    ${
      secondary.length
        ? `
          <div class="case-diagnosis-secondary-actions">
            <strong>其他动作</strong>
            <div class="readiness-action-row">
              ${secondary.map((action) => renderReadinessActionButton(action)).join("")}
            </div>
            ${renderMiniList(secondary.map((action) => action.description || action.label || ""))}
          </div>
        `
        : ""
    }
  `;
}

function renderCaseDiagnosis(data) {
  const diagnosis = data.case_diagnosis || {};
  const score = diagnosis.score || {};
  const blockers = normalizeItems(diagnosis.blockers);
  const primaryActions = normalizeItems(diagnosis.primary_actions);
  const blockerRows = blockers.length
    ? blockers
    : [{source: "complete", label: "暂无阻塞项", message: "当前没有发现会阻止继续拆解的关键问题。", target: ""}];
  caseDiagnosisSummary.innerHTML = `
    <div class="case-diagnosis-hero ${escapeHtml(diagnosis.status || "pending")}">
      <div>
        <span class="status-pill ${escapeHtml(diagnosis.status || "pending")}">${escapeHtml(diagnosis.label || "待诊断")}</span>
        <strong>${escapeHtml(diagnosis.summary || "正在等待素材包诊断。")}</strong>
      </div>
      <div class="case-diagnosis-score-grid">
        <div><span>${escapeHtml(score.quality ?? 0)}</span><small>AI 质量</small></div>
        <div><span>${escapeHtml(score.readiness ?? 0)}</span><small>准备度</small></div>
        <div><span>${escapeHtml(score.enrichment_blocking ?? 0)}</span><small>富化阻塞</small></div>
        <div><span>${escapeHtml(score.human_blocking ?? 0)}</span><small>人工阻塞</small></div>
      </div>
    </div>
    <div class="case-diagnosis-grid">
      <article class="case-diagnosis-panel">
        <strong>关键阻塞</strong>
        <div class="case-diagnosis-blocker-list">
          ${blockerRows
            .map((item) => `
              <div class="case-diagnosis-blocker ${escapeHtml(item.source || "unknown")}">
                <div>
                  <span>${escapeHtml(diagnosisSourceLabels[item.source] || item.source || "诊断")}</span>
                  <strong>${escapeHtml(item.label || "")}</strong>
                  <p>${escapeHtml(item.message || "")}</p>
                </div>
                ${renderReadinessActionButton({label: "定位", target: item.target || ""})}
              </div>
            `)
            .join("")}
        </div>
      </article>
      <article class="case-diagnosis-panel action-card">
        <strong>下一步动作</strong>
        ${renderDiagnosisActions(primaryActions)}
      </article>
    </div>
  `;
}

function renderReadiness(data) {
  const readiness = data.analysis_readiness || {};
  const checks = readiness.checks || [];
  const nextActions = readiness.next_actions || [];
  const nextActionItems = readiness.next_action_items || [];
  const criticalGaps = readiness.critical_gaps || [];
  const level = readiness.level || "low";
  readinessSummary.innerHTML = `
    <div class="readiness-hero ${escapeHtml(level)}">
      <div>
        <div class="readiness-score">${escapeHtml(readiness.score ?? 0)}<span>/ ${escapeHtml(readiness.max_score ?? 100)}</span></div>
        <strong>${escapeHtml(readiness.label || "待检查")}</strong>
      </div>
      <p>${escapeHtml(readiness.summary || "")}</p>
    </div>
    ${renderCriticalGaps(criticalGaps)}
    <div class="readiness-check-grid">
      ${checks
        .map((check) => `
          <div class="readiness-check ${check.ready ? "ready" : "missing"}">
            <div class="readiness-check-title">
              <strong>${escapeHtml(check.label || "")}</strong>
              <span class="status-pill ${escapeHtml(check.status || "pending")}">${escapeHtml(check.ready ? "已就绪" : check.status || "待补齐")}</span>
            </div>
            <p>${escapeHtml(check.message || "")}</p>
            ${check.ready ? "" : `<p class="muted compact-copy">建议：${escapeHtml(check.action || "")}</p>`}
            ${check.ready ? "" : renderReadinessActionButton({label: check.action_label, target: check.action_target})}
          </div>
        `)
        .join("")}
    </div>
    <div class="readiness-next-actions">
      <strong>下一步建议</strong>
      ${renderMiniList(nextActions)}
      <div class="readiness-action-row">
        ${nextActionItems.map((action) => renderReadinessActionButton(action, "primary-action")).join("")}
      </div>
    </div>
  `;
}

function renderQualityCalibration(data) {
  const calibration = data.quality_calibration || {};
  const aiQuality = calibration.ai_quality || {};
  const humanAcceptance = calibration.human_acceptance || {};
  const readiness = calibration.readiness || {};
  const worksheet = calibration.worksheet || {};
  const actions = calibration.next_actions || [];
  const recommendations = calibration.recommendations || [];
  const aiGaps = normalizeItems(aiQuality.gaps).map((gap) => {
    if (gap && typeof gap === "object") {
      return `${gap.label || gap.id || "质量缺口"}：${gap.action || gap.message || ""}`;
    }
    return gap;
  });
  const blockers = normalizeItems(humanAcceptance.blockers).map((blocker) => {
    if (blocker && typeof blocker === "object") {
      return `${blocker.label || blocker.id || "人工阻塞项"}：${blocker.message || blocker.status || ""}`;
    }
    return blocker;
  });
  const readinessGaps = normalizeItems(readiness.critical_gaps).map((gap) => {
    if (gap && typeof gap === "object") {
      return `${gap.label || gap.id || "准备度缺口"}：${gap.action || gap.message || ""}`;
    }
    return gap;
  });
  qualityCalibrationSummary.innerHTML = `
    <div class="quality-calibration-hero ${escapeHtml(calibration.status || "pending")}">
      <div>
        <span class="status-pill ${escapeHtml(calibration.status || "pending")}">${escapeHtml(calibration.label || "待校准")}</span>
        <strong>${escapeHtml(calibration.summary || "暂无校准结论。")}</strong>
      </div>
      <div class="quality-calibration-score">
        <span>${escapeHtml(aiQuality.score ?? 0)}</span>
        <small>AI / ${escapeHtml(aiQuality.max_score ?? 100)}</small>
      </div>
    </div>
    <div class="quality-calibration-grid">
      <article class="quality-calibration-cardlet">
        <strong>AI 自检</strong>
        ${renderFieldRows([
          ["报告状态", aiQuality.has_report ? "已生成" : "未生成"],
          ["质量等级", aiQuality.label || aiQuality.level || ""],
          ["质量总结", aiQuality.summary || ""],
          ["AI 缺口", aiQuality.gap_count ? `${aiQuality.gap_count} 项` : "无"],
        ])}
        ${renderMiniList(aiGaps)}
      </article>
      <article class="quality-calibration-cardlet">
        <strong>人工验收</strong>
        ${renderFieldRows([
          ["验收结论", humanAcceptance.verdict_label || humanAcceptance.verdict || "待验收"],
          ["人工评分", humanAcceptance.score || ""],
          ["验收意见", humanAcceptance.summary || ""],
          ["阻塞项", humanAcceptance.blocker_count ? `${humanAcceptance.blocker_count} 项` : "无"],
        ])}
        ${renderMiniList(blockers)}
      </article>
      <article class="quality-calibration-cardlet action-card">
        <strong>校准动作</strong>
        ${renderFieldRows([
          ["准备度", `${readiness.score ?? 0} / ${readiness.label || ""}`],
          ["人工工作表", `${worksheet.score ?? 0} / ${worksheet.label || worksheet.level || ""}`],
          ["关键准备缺口", readiness.critical_gap_count ? `${readiness.critical_gap_count} 项` : "无"],
        ])}
        ${readinessGaps.length ? renderMiniList(readinessGaps) : ""}
        ${renderMiniList(actions.map((action) => action.description || action.label || ""))}
        <h4>规则建议</h4>
        ${renderRecommendationList(recommendations)}
        <div class="readiness-action-row">
          ${actions.map((action) => renderReadinessActionButton(action, "primary-action")).join("")}
        </div>
      </article>
    </div>
  `;
}

caseDiagnosisSummary.addEventListener("click", (event) => {
  const button = event.target.closest("[data-action-target]");
  if (!button || !caseDiagnosisSummary.contains(button)) {
    return;
  }
  activateReadinessTarget(button.dataset.actionTarget || "", button.dataset.actionMode || "focus");
});

readinessSummary.addEventListener("click", (event) => {
  const button = event.target.closest("[data-action-target]");
  if (!button || !readinessSummary.contains(button)) {
    return;
  }
  activateReadinessTarget(button.dataset.actionTarget || "", button.dataset.actionMode || "focus");
});

qualityCalibrationSummary.addEventListener("click", (event) => {
  const button = event.target.closest("[data-action-target]");
  if (!button || !qualityCalibrationSummary.contains(button)) {
    return;
  }
  activateReadinessTarget(button.dataset.actionTarget || "", button.dataset.actionMode || "focus");
});

rerunStrategyPanel.addEventListener("click", (event) => {
  const button = event.target.closest("[data-action-target]");
  if (!button || !rerunStrategyPanel.contains(button)) {
    return;
  }
  activateReadinessTarget(button.dataset.actionTarget || "", button.dataset.actionMode || "focus");
});

function renderEnrichment(data) {
  const enrichment = data.enrichment || {};
  const manifest = enrichment.manifest || {};
  const statuses = manifest.statuses || {};
  const commentSummary = enrichment.comment_summary || {};
  const caseIndex = enrichment.case_index || {};
  const asrStatus = enrichment.asr_status || {};
  const asrTranscript = enrichment.asr_transcript || {};
  const ocrStatus = enrichment.ocr_status || {};
  const ocrFrame = enrichment.ocr_frame || {};
  const ocrSubtitle = enrichment.ocr_subtitle || {};
  const paths = enrichment.paths || {};
  const commentsPath = paths.comments || {};
  const metricsPath = paths.metrics || {};
  const indexesPath = paths.indexes || {};

  enrichmentStatus.innerHTML = `
    <div class="status-pill-row">${renderStatusPills(statuses)}</div>
    <p class="muted compact-copy">富化目录：${escapeHtml(paths.base || "尚未生成")}</p>
  `;

  enrichmentSummary.innerHTML = `
    <div class="enrichment-grid">
      <div class="artifact-item">
        <strong>评论摘要</strong>
        <p>评论数：${formatNumber(commentSummary.total_comments || 0)}</p>
        <p>高频词：${escapeHtml((commentSummary.high_frequency_words || []).slice(0, 10).join("、") || "暂无")}</p>
        <p class="muted compact-copy">${escapeHtml(commentsPath.summary || "")}</p>
      </div>
      <div class="artifact-item">
        <strong>指标快照</strong>
        <p>来源：${escapeHtml(manifest.source_url || data.metadata?.source_url || "")}</p>
        <p class="muted compact-copy">${escapeHtml(metricsPath.snapshots || "")}</p>
      </div>
      <div class="artifact-item">
        <strong>结构化索引</strong>
        <p>标题：${escapeHtml(caseIndex.title || data.metadata?.title || "")}</p>
        <p class="muted compact-copy">${escapeHtml(indexesPath.case_index || "")}</p>
      </div>
      <div class="artifact-item">
        <strong>ASR / OCR</strong>
        <p>ASR：${escapeHtml(asrStatus.status || statuses.asr || "pending")}</p>
        <p>OCR：${escapeHtml(ocrStatus.status || statuses.ocr || "pending")}</p>
        <p>转写：${escapeHtml((asrTranscript.full_text || "").slice(0, 80) || "暂无")}</p>
        <p>画面文字：${escapeHtml((ocrFrame.full_text || "").slice(0, 80) || "暂无")}</p>
        <p>字幕文字：${escapeHtml((ocrSubtitle.full_text || "").slice(0, 80) || "暂无")}</p>
        <p class="muted compact-copy">${escapeHtml(asrStatus.message || ocrStatus.message || "后续接入 provider 后可重跑。")}</p>
      </div>
    </div>
  `;
}

function collectWorksheet() {
  const source = loadedCase.worksheet || {};
  const worksheet = JSON.parse(JSON.stringify(source));
  worksheet.summary = worksheetSummary.value;
  worksheet.sections = worksheet.sections || {};
  worksheetSections.querySelectorAll("textarea[data-section-id][data-field-id]").forEach((textarea) => {
    const sectionId = textarea.dataset.sectionId;
    const fieldId = textarea.dataset.fieldId;
    worksheet.sections[sectionId] = worksheet.sections[sectionId] || {fields: {}};
    worksheet.sections[sectionId].fields = worksheet.sections[sectionId].fields || {};
    worksheet.sections[sectionId].fields[fieldId] = worksheet.sections[sectionId].fields[fieldId] || {};
    worksheet.sections[sectionId].fields[fieldId].value = textarea.value;
  });
  return worksheet;
}

function buildFullPrompt(data) {
  const analysisInput = JSON.stringify(data.analysis_input || {}, null, 2);
  return `${data.prompt || ""}\n\n## 附：analysis_input.json\n\n\`\`\`json\n${analysisInput}\n\`\`\``;
}

function renderCase(data) {
  loadedCase = data;
  const metadata = loadedCase.metadata || {};
  const ffprobe = loadedCase.ffprobe || {};
  const analysisInput = loadedCase.analysis_input || {};
  const stats = analysisInput.stats || {};
  const video = analysisInput.video || {};
  const analysisHints = buildAnalysisHints(metadata, ffprobe, analysisInput);

  contactSheetImage.src = `${loadedCase.artifact_urls.contact_sheet}?v=${Date.now()}`;
  renderDefinitionList(caseMeta, [
    ["素材包 ID", loadedCase.case_id],
    ["作品 ID", metadata.aweme_id || analysisInput.aweme_id],
    ["标题", metadata.title],
    ["作者", metadata.author],
    ["来源", metadata.source_url],
    ["点赞", formatNumber(stats.like_count)],
    ["评论", formatNumber(stats.comment_count)],
    ["分享", formatNumber(stats.share_count)],
    ["互动分", formatNumber(stats.engagement_score)],
    ["时长", formatSeconds(video.duration || ffprobe.duration)],
    ["分辨率", `${video.width || ffprobe.width || 0}x${video.height || ffprobe.height || 0}`],
    ["帧率", video.fps || ffprobe.fps || ""],
    ["文件大小", formatBytes(video.file_size || ffprobe.file_size)],
    ["素材目录", loadedCase.paths.keyframes_dir],
  ]);
  renderDefinitionList(primaryCaseMeta, [
    ["素材包 ID", loadedCase.case_id],
    ["作品 ID", metadata.aweme_id || analysisInput.aweme_id],
    ["标题", metadata.title],
    ["作者", metadata.author],
    ["来源", metadata.source_url],
    ["时长", formatSeconds(video.duration || ffprobe.duration)],
    ["分辨率", `${video.width || ffprobe.width || 0}x${video.height || ffprobe.height || 0}`],
    ["文件大小", formatBytes(video.file_size || ffprobe.file_size)],
  ]);
  renderPrimaryWorkflow(loadedCase);

  renderCategoryControls(analysisInput);
  renderCaseDiagnosis(loadedCase);
  renderReadiness(loadedCase);
  renderQualityCalibration(loadedCase);
  renderArtifactOverview(loadedCase);
  renderLlmStatus(loadedCase.llm_settings || {});
  renderKeyframes(loadedCase, analysisInput);
  renderEnrichment(loadedCase);
  renderAutoAnalysis(loadedCase);
  renderQualityAcceptance(loadedCase.quality_acceptance || {});
  renderRerunStrategy(loadedCase);
  renderWorksheet(loadedCase.worksheet || {}, loadedCase.worksheet_review || {});

  promptText.textContent = loadedCase.prompt || "";
  analysisBriefText.textContent = loadedCase.analysis_brief || "";
  analysisJson.textContent = JSON.stringify(analysisInput, null, 2);
}

async function loadCase() {
  caseMeta.textContent = "正在读取素材包...";
  const response = await fetch(`/api/cases/${caseId}`, {cache: "no-store"});
  const payload = await response.json();
  if (!response.ok || payload.ok === false) {
    const message = payload.message || "素材包读取失败";
    caseMeta.textContent = `${payload.error_code || "ERROR"}：${message}`;
    return;
  }

  renderCase(payload.case);
}

copyPromptButton.addEventListener("click", async () => {
  if (!loadedCase) {
    return;
  }
  const text = buildFullPrompt(loadedCase);
  await navigator.clipboard.writeText(text);
  copyPromptButton.textContent = "已复制";
  window.setTimeout(() => {
    copyPromptButton.textContent = "复制 Prompt";
  }, 1600);
});

downloadAnalysisInputButton.addEventListener("click", () => {
  if (!loadedCase) {
    return;
  }
  const url = loadedCase.artifact_urls?.analysis_input;
  if (url) {
    window.open(url, "_blank", "noopener,noreferrer");
  }
});

downloadRerunPlanButton.addEventListener("click", () => {
  if (!loadedCase) {
    return;
  }
  const url = loadedCase.artifact_urls?.rerun_plan;
  if (url) {
    window.open(url, "_blank", "noopener,noreferrer");
  }
});

downloadRerunPlanMarkdownButton.addEventListener("click", () => {
  if (!loadedCase) {
    return;
  }
  const url = loadedCase.artifact_urls?.rerun_plan_markdown;
  if (url) {
    window.open(url, "_blank", "noopener,noreferrer");
  }
});

copyBriefButton.addEventListener("click", async () => {
  if (!loadedCase) {
    return;
  }
  await navigator.clipboard.writeText(loadedCase.analysis_brief || "");
  copyBriefButton.textContent = "已复制";
  window.setTimeout(() => {
    copyBriefButton.textContent = "复制分析工作表";
  }, 1600);
});

copyAiReportButton.addEventListener("click", async () => {
  if (!loadedCase || !loadedCase.analysis_report) {
    return;
  }
  await navigator.clipboard.writeText(loadedCase.analysis_report);
  copyAiReportButton.textContent = "已复制";
  window.setTimeout(() => {
    copyAiReportButton.textContent = "复制 AI 报告";
  }, 1600);
});

async function pollAnalysisJob(jobId) {
  const response = await fetch(`/api/jobs/${jobId}`, {cache: "no-store"});
  const payload = await response.json();
  if (!response.ok || payload.ok === false) {
    throw payload;
  }
  const job = payload.job;
  autoAnalysisStatus.textContent = `${job.status} · ${job.progress}% · ${job.message || ""}`;
  primaryAiStatus.textContent = `AI 分析中：${job.progress || 0}% · ${job.message || ""}`;
  if (job.status === "success") {
    await loadCase();
    runAutoAnalysisButton.disabled = false;
    saveQualityAcceptanceAndRerunButton.disabled = false;
    return job;
  }
  if (job.status === "failed") {
    const code = job.error_code || "ERROR";
    const advice = errorAdvice(code);
    autoAnalysisStatus.textContent = `${code}：${job.message || "自动拆解失败"}${advice ? ` ${advice}` : ""}`;
    primaryAiStatus.textContent = `${code}：AI 自动拆解失败。${advice || "请检查模型配置后重试。"}`;
    runAutoAnalysisButton.disabled = false;
    saveQualityAcceptanceAndRerunButton.disabled = false;
    return job;
  }
  await wait(900);
  return pollAnalysisJob(jobId);
}

async function startAutoAnalysisJob() {
  const response = await fetch("/api/jobs/analyze-case", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({case_id: loadedCase.case_id}),
  });
  const payload = await response.json();
  if (!response.ok || payload.ok === false) {
    throw payload;
  }
  return pollAnalysisJob(payload.job_id);
}

function restoreAnalysisActionButtons() {
  const configured = Boolean(loadedCase && loadedCase.llm_settings && loadedCase.llm_settings.configured);
  runAutoAnalysisButton.disabled = !configured;
  saveQualityAcceptanceAndRerunButton.disabled = !configured;
  syncPrimaryRunButtons(!configured);
}

runAutoAnalysisButton.addEventListener("click", async () => {
  if (!loadedCase) {
    return;
  }
  setCaseTab("ai");
  runAutoAnalysisButton.disabled = true;
  saveQualityAcceptanceAndRerunButton.disabled = true;
  syncPrimaryRunButtons(true);
  autoAnalysisStatus.textContent = "正在创建 AI 自动拆解任务...";
  primaryAiStatus.textContent = "AI 分析中：正在创建任务...";
  try {
    await startAutoAnalysisJob();
  } catch (error) {
    const code = error.error_code || "ERROR";
    const advice = errorAdvice(code);
    autoAnalysisStatus.textContent = `${code}：${error.message || "任务创建失败"}${advice ? ` ${advice}` : ""}`;
    restoreAnalysisActionButtons();
  }
});

document.querySelectorAll("[data-primary-action]").forEach((button) => {
  button.addEventListener("click", () => {
    const action = button.dataset.primaryAction;
    if (action === "copy_prompt") {
      setCaseTab("package");
      copyPromptButton.click();
    } else if (action === "download_input") {
      setCaseTab("package");
      downloadAnalysisInputButton.click();
    } else if (action === "run_ai") {
      setCaseTab("ai");
      runAutoAnalysisButton.click();
    }
  });
});

caseTabButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setCaseTab(button.dataset.caseTab);
  });
});

document.querySelectorAll('a[href="#auto-analysis-report"]').forEach((link) => {
  link.addEventListener("click", () => {
    setCaseTab("ai");
  });
});

async function pollEnrichmentJob(jobId) {
  const response = await fetch(`/api/jobs/${jobId}`, {cache: "no-store"});
  const payload = await response.json();
  if (!response.ok || payload.ok === false) {
    throw payload;
  }
  const job = payload.job;
  enrichmentStatus.textContent = `${job.status} · ${job.progress}% · ${job.message || ""}`;
  if (job.status === "success") {
    await loadCase();
    runEnrichmentButton.disabled = false;
    return;
  }
  if (job.status === "failed") {
    const code = job.error_code || "ERROR";
    const advice = errorAdvice(code);
    enrichmentStatus.textContent = `${code}：${job.message || "富化归档失败"}${advice ? ` ${advice}` : ""}`;
    runEnrichmentButton.disabled = false;
    return;
  }
  await wait(700);
  return pollEnrichmentJob(jobId);
}

async function pollAsrJob(jobId) {
  const response = await fetch(`/api/jobs/${jobId}`, {cache: "no-store"});
  const payload = await response.json();
  if (!response.ok || payload.ok === false) {
    throw payload;
  }
  const job = payload.job;
  enrichmentStatus.textContent = `${job.status} · ${job.progress}% · ${job.message || ""}`;
  if (job.status === "success") {
    await loadCase();
    enrichmentStatus.textContent = job.message || "ASR 完成";
    asrPlaceholderButton.disabled = false;
    return;
  }
  if (job.status === "failed") {
    const code = job.error_code || "ERROR";
    const advice = errorAdvice(code);
    await loadCase();
    enrichmentStatus.textContent = `${code}：${job.message || "ASR 失败"}${advice ? ` ${advice}` : ""}`;
    asrPlaceholderButton.disabled = false;
    return;
  }
  await wait(900);
  return pollAsrJob(jobId);
}

async function pollOcrJob(jobId) {
  const response = await fetch(`/api/jobs/${jobId}`, {cache: "no-store"});
  const payload = await response.json();
  if (!response.ok || payload.ok === false) {
    throw payload;
  }
  const job = payload.job;
  enrichmentStatus.textContent = `${job.status} · ${job.progress}% · ${job.message || ""}`;
  if (job.status === "success") {
    await loadCase();
    enrichmentStatus.textContent = job.message || "OCR 完成";
    ocrPlaceholderButton.disabled = false;
    return;
  }
  if (job.status === "failed") {
    const code = job.error_code || "ERROR";
    const advice = errorAdvice(code);
    await loadCase();
    enrichmentStatus.textContent = `${code}：${job.message || "OCR 失败"}${advice ? ` ${advice}` : ""}`;
    ocrPlaceholderButton.disabled = false;
    return;
  }
  await wait(900);
  return pollOcrJob(jobId);
}

runEnrichmentButton.addEventListener("click", async () => {
  if (!loadedCase) {
    return;
  }
  runEnrichmentButton.disabled = true;
  enrichmentStatus.textContent = "正在创建富化归档任务...";
  try {
    const response = await fetch("/api/jobs/enrich-case", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({case_id: loadedCase.case_id}),
    });
    const payload = await response.json();
    if (!response.ok || payload.ok === false) {
      throw payload;
    }
    await pollEnrichmentJob(payload.job_id);
  } catch (error) {
    const code = error.error_code || "ERROR";
    const advice = errorAdvice(code);
    enrichmentStatus.textContent = `${code}：${error.message || "任务创建失败"}${advice ? ` ${advice}` : ""}`;
    runEnrichmentButton.disabled = false;
  }
});

metricSnapshotButton.addEventListener("click", async () => {
  if (!loadedCase) {
    return;
  }
  metricSnapshotButton.disabled = true;
  metricStatus.textContent = "正在记录指标快照...";
  try {
    const response = await fetch(`/api/cases/${caseId}/metrics/snapshot`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({capture_method: "case_page", permission_note: "local personal analysis"}),
    });
    const payload = await response.json();
    if (!response.ok || payload.ok === false) {
      throw payload;
    }
    metricStatus.textContent = "指标快照已写入 snapshots.jsonl。";
    await loadCase();
  } catch (error) {
    metricStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "记录失败"}`;
  } finally {
    metricSnapshotButton.disabled = false;
  }
});

importCommentsButton.addEventListener("click", async () => {
  if (!loadedCase) {
    return;
  }
  importCommentsButton.disabled = true;
  commentsStatus.textContent = "正在导入评论...";
  try {
    const response = await fetch(`/api/cases/${caseId}/comments/import`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        text: commentsImportText.value,
        comments: [],
        source: "manual",
        permission_note: "user provided comments",
      }),
    });
    const payload = await response.json();
    if (!response.ok || payload.ok === false) {
      throw payload;
    }
    commentsImportText.value = "";
    commentsStatus.textContent = `已导入 ${payload.comments.imported_count} 条评论，并刷新评论摘要。`;
    await loadCase();
  } catch (error) {
    const code = error.error_code || "ERROR";
    const advice = errorAdvice(code);
    commentsStatus.textContent = `${code}：${error.message || "导入失败"}${advice ? ` ${advice}` : ""}`;
  } finally {
    importCommentsButton.disabled = false;
  }
});

async function runProviderPlaceholder(kind) {
  const button = kind === "asr" ? asrPlaceholderButton : ocrPlaceholderButton;
  button.disabled = true;
  enrichmentStatus.textContent = `正在检查 ${kind.toUpperCase()} provider 状态...`;
  try {
    if (kind === "asr") {
      enrichmentStatus.textContent = "正在创建 ASR 任务...";
      const response = await fetch("/api/jobs/asr-case", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({case_id: loadedCase.case_id}),
      });
      const payload = await response.json();
      if (!response.ok || payload.ok === false) {
        throw payload;
      }
      await pollAsrJob(payload.job_id);
      return;
    }
    if (kind === "ocr") {
      enrichmentStatus.textContent = "正在创建 OCR 任务...";
      const response = await fetch("/api/jobs/ocr-case", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({case_id: loadedCase.case_id}),
      });
      const payload = await response.json();
      if (!response.ok || payload.ok === false) {
        throw payload;
      }
      await pollOcrJob(payload.job_id);
      return;
    }
    const response = await fetch(`/api/cases/${caseId}/${kind}`, {method: "POST"});
    const payload = await response.json();
    const code = payload.error_code || (kind === "asr" ? "ASR_PROVIDER_NOT_CONFIGURED" : "OCR_PROVIDER_NOT_CONFIGURED");
    const advice = errorAdvice(code);
    await loadCase();
    enrichmentStatus.textContent = `${code}：${payload.message || "provider 未配置"}${advice ? ` ${advice}` : ""}`;
  } catch (error) {
    enrichmentStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "检查失败"}`;
  } finally {
    button.disabled = false;
  }
}

asrPlaceholderButton.addEventListener("click", () => {
  runProviderPlaceholder("asr");
});

ocrPlaceholderButton.addEventListener("click", () => {
  runProviderPlaceholder("ocr");
});

updateCategoryButton.addEventListener("click", async () => {
  if (!loadedCase) {
    return;
  }
  updateCategoryButton.disabled = true;
  categoryStatus.classList.remove("hidden");
  categoryStatus.textContent = "正在更新分析类型...";
  try {
    const response = await fetch(`/api/cases/${caseId}/analysis-category`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({category_id: analysisCategorySelect.value}),
    });
    const payload = await response.json();
    if (!response.ok || payload.ok === false) {
      throw payload;
    }
    renderCase(payload.case);
    categoryStatus.textContent = "已更新分析类型，Prompt 和 analysis_input.json 已同步。";
  } catch (error) {
    categoryStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "更新失败"}`;
  } finally {
    updateCategoryButton.disabled = false;
  }
});

saveWorksheetButton.addEventListener("click", async () => {
  if (!loadedCase) {
    return;
  }
  saveWorksheetButton.disabled = true;
  worksheetStatus.textContent = "正在保存...";
  try {
    const response = await fetch(`/api/cases/${caseId}/worksheet`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({worksheet: collectWorksheet()}),
    });
    const payload = await response.json();
    if (!response.ok || payload.ok === false) {
      throw payload;
    }
    renderCase(payload.case);
    worksheetStatus.textContent = "已保存，并同步生成 analysis_brief.md。";
  } catch (error) {
    worksheetStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "保存失败"}`;
  } finally {
    saveWorksheetButton.disabled = false;
  }
});

async function saveQualityAcceptance(successMessage) {
  const response = await fetch(`/api/cases/${caseId}/quality-acceptance`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({acceptance: collectQualityAcceptance()}),
  });
  const payload = await response.json();
  if (!response.ok || payload.ok === false) {
    throw payload;
  }
  renderCase(payload.case);
  qualityAcceptanceStatus.textContent = successMessage;
  return payload.case;
}

saveQualityAcceptanceButton.addEventListener("click", async () => {
  if (!loadedCase) {
    return;
  }
  saveQualityAcceptanceButton.disabled = true;
  qualityAcceptanceStatus.textContent = "正在保存...";
  try {
    await saveQualityAcceptance("已保存到 quality_acceptance.json。");
  } catch (error) {
    qualityAcceptanceStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "保存失败"}`;
  } finally {
    saveQualityAcceptanceButton.disabled = false;
  }
});

saveQualityAcceptanceAndRerunButton.addEventListener("click", async () => {
  if (!loadedCase) {
    return;
  }
  saveQualityAcceptanceButton.disabled = true;
  saveQualityAcceptanceAndRerunButton.disabled = true;
  runAutoAnalysisButton.disabled = true;
  qualityAcceptanceStatus.textContent = "正在保存质量验收...";
  try {
    await saveQualityAcceptance("已保存质量验收，正在带入反馈重新 AI 拆解...");
    if (!confirmMissingEvidenceBeforeRerun(loadedCase)) {
      qualityAcceptanceStatus.textContent = "已保存质量验收，已取消重新拆解。可以先补齐策略提示的证据。";
      return;
    }
    runAutoAnalysisButton.disabled = true;
    saveQualityAcceptanceAndRerunButton.disabled = true;
    autoAnalysisStatus.textContent = "正在创建 AI 自动拆解任务，人工验收反馈会进入本次分析上下文...";
    const job = await startAutoAnalysisJob();
    qualityAcceptanceStatus.textContent = job.status === "success"
      ? "已保存质量验收，并完成重新拆解任务。"
      : "已保存质量验收，但重新拆解失败；请查看 AI 自动拆解状态。";
  } catch (error) {
    const code = error.error_code || "ERROR";
    const advice = errorAdvice(code);
    qualityAcceptanceStatus.textContent = `${code}：${error.message || "保存或重新拆解失败"}${advice ? ` ${advice}` : ""}`;
    if (code !== "LLM_NOT_CONFIGURED") {
      autoAnalysisStatus.textContent = `${code}：${error.message || "任务创建失败"}${advice ? ` ${advice}` : ""}`;
    }
  } finally {
    saveQualityAcceptanceButton.disabled = false;
    restoreAnalysisActionButtons();
  }
});

saveQualityCalibrationRecordButton.addEventListener("click", async () => {
  if (!loadedCase) {
    return;
  }
  saveQualityCalibrationRecordButton.disabled = true;
  qualityCalibrationRecordStatus.textContent = "正在保存校准样本...";
  try {
    const response = await fetch(`/api/cases/${caseId}/quality-calibration/record`, {
      method: "POST",
    });
    const payload = await response.json();
    if (!response.ok || payload.ok === false) {
      throw payload;
    }
    renderCase(payload.case);
    qualityCalibrationRecordStatus.textContent = `已保存：${payload.record_path || "quality_calibration_record.json"}`;
  } catch (error) {
    qualityCalibrationRecordStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "保存失败"}`;
  } finally {
    saveQualityCalibrationRecordButton.disabled = false;
  }
});

loadCase();
setCaseTab("overview");
