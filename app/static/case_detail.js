const page = document.querySelector(".case-page");
const caseId = page.dataset.caseId;
const contactSheetImage = document.getElementById("contact-sheet-image");
const caseMeta = document.getElementById("case-meta");
const analysisSummary = document.getElementById("analysis-summary");
const analysisCategorySelect = document.getElementById("analysis-category-select");
const updateCategoryButton = document.getElementById("update-category-button");
const categoryDescription = document.getElementById("category-description");
const categoryStatus = document.getElementById("category-status");
const analysisLensList = document.getElementById("analysis-lens-list");
const keyQuestionsList = document.getElementById("key-questions-list");
const contentRatioList = document.getElementById("content-ratio-list");
const keyframeStrip = document.getElementById("keyframe-strip");
const promptText = document.getElementById("prompt-text");
const analysisBriefText = document.getElementById("analysis-brief-text");
const analysisJson = document.getElementById("analysis-json");
const copyPromptButton = document.getElementById("copy-prompt-button");
const copyBriefButton = document.getElementById("copy-brief-button");
const runAutoAnalysisButton = document.getElementById("run-auto-analysis-button");
const copyAiReportButton = document.getElementById("copy-ai-report-button");
const autoAnalysisStatus = document.getElementById("auto-analysis-status");
const autoAnalysisSummary = document.getElementById("auto-analysis-summary");
const autoAnalysisReport = document.getElementById("auto-analysis-report");
const worksheetSummary = document.getElementById("worksheet-summary");
const worksheetSections = document.getElementById("worksheet-sections");
const saveWorksheetButton = document.getElementById("save-worksheet-button");
const worksheetStatus = document.getElementById("worksheet-status");

let loadedCase = null;

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

function renderBullets(element, items) {
  const values = Array.isArray(items) ? items : [];
  if (!values.length) {
    element.innerHTML = "<li>暂无。</li>";
    return;
  }
  element.innerHTML = values.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
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

function renderAnalysisFramework(analysisInput) {
  const context = analysisInput.analysis_context || {};
  renderBullets(analysisLensList, context.analysis_lens || analysisInput.analysis_lens || []);
  renderBullets(keyQuestionsList, context.key_questions || analysisInput.key_questions || []);
  renderBullets(contentRatioList, context.content_ratio || analysisInput.content_ratio || []);
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

function renderWorksheet(worksheet) {
  worksheetSummary.value = worksheet.summary || "";
  const sections = worksheet.sections || {};
  worksheetSections.innerHTML = Object.entries(sections)
    .map(([sectionId, section]) => {
      const fields = section.fields || {};
      const fieldHtml = Object.entries(fields)
        .map(([fieldId, field]) => `
          <label>${escapeHtml(field.label || fieldId)}
            <textarea
              rows="4"
              data-section-id="${escapeHtml(sectionId)}"
              data-field-id="${escapeHtml(fieldId)}"
              placeholder="填写你的观察和判断..."
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

function renderAutoAnalysis(data) {
  const result = data.analysis_result || null;
  const report = data.analysis_report || "";
  if (!result) {
    autoAnalysisStatus.textContent = "尚未生成 AI 自动拆解。请配置大模型 API 后点击“开始 AI 自动拆解”。";
    autoAnalysisSummary.innerHTML = "";
    autoAnalysisReport.textContent = "";
    copyAiReportButton.disabled = true;
    runAutoAnalysisButton.textContent = "开始 AI 自动拆解";
    return;
  }
  autoAnalysisStatus.textContent = "AI 自动拆解已生成。";
  copyAiReportButton.disabled = false;
  runAutoAnalysisButton.textContent = "重新 AI 自动拆解";
  renderDefinitionList(autoAnalysisSummary, [
    ["一句话总结", result.summary || ""],
    ["内容类型", result.content_category_label || result.content_category || ""],
    ["置信度", result.confidence ?? ""],
    ["互动数据", result.engagement_data_quality || ""],
    ["停留理由", result.hook_analysis?.why_stop_scrolling || ""],
    ["复刻角度", result.replication?.remake_angle || ""],
  ]);
  autoAnalysisReport.textContent = report || JSON.stringify(result, null, 2);
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

  renderCategoryControls(analysisInput);
  renderDefinitionList(analysisSummary, analysisHints.rows);
  renderAnalysisFramework(analysisInput);
  renderKeyframes(loadedCase, analysisInput);
  renderAutoAnalysis(loadedCase);
  renderWorksheet(loadedCase.worksheet || {});

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
    copyPromptButton.textContent = "复制调试 Prompt";
  }, 1600);
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
  if (job.status === "success") {
    await loadCase();
    runAutoAnalysisButton.disabled = false;
    return;
  }
  if (job.status === "failed") {
    autoAnalysisStatus.textContent = `${job.error_code || "ERROR"}：${job.message || "自动拆解失败"}`;
    runAutoAnalysisButton.disabled = false;
    return;
  }
  window.setTimeout(() => {
    pollAnalysisJob(jobId).catch((error) => {
      autoAnalysisStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "查询任务失败"}`;
      runAutoAnalysisButton.disabled = false;
    });
  }, 900);
}

runAutoAnalysisButton.addEventListener("click", async () => {
  if (!loadedCase) {
    return;
  }
  runAutoAnalysisButton.disabled = true;
  autoAnalysisStatus.textContent = "正在创建 AI 自动拆解任务...";
  try {
    const response = await fetch("/api/jobs/analyze-case", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({case_id: loadedCase.case_id}),
    });
    const payload = await response.json();
    if (!response.ok || payload.ok === false) {
      throw payload;
    }
    await pollAnalysisJob(payload.job_id);
  } catch (error) {
    autoAnalysisStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "任务创建失败"}`;
    runAutoAnalysisButton.disabled = false;
  }
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

loadCase();
