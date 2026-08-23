(function initializeCreatorExecutionRecordView(global) {
  "use strict";

  const STATUS_LABELS = Object.freeze({
    draft: "尚未开始",
    in_progress: "执行中",
    completed: "执行已完成",
    archived: "已归档",
  });
  const STAGE_LABELS = Object.freeze({
    shooting: "拍摄",
    editing: "剪辑",
    publishing: "发布",
  });
  const PRODUCTION_LABELS = Object.freeze({
    pending: "未完成",
    completed: "已完成",
    skipped: "已跳过",
  });

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function objectValue(value) {
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  }

  function selected(value, expected) {
    return String(value ?? "") === String(expected) ? " selected" : "";
  }

  function ratingOptions(value) {
    return `
      <option value="">暂不填写</option>
      ${[1, 2, 3, 4, 5].map((rating) => `<option value="${rating}"${selected(value, rating)}>${rating}</option>`).join("")}
    `;
  }

  function renderStage(stage, value, archived, readOnly = false) {
    const stageLabel = STAGE_LABELS[stage] || stage;
    const statusLabel = PRODUCTION_LABELS[value] || PRODUCTION_LABELS.pending;
    return `
      <article class="execution-record-stage" data-execution-record-stage="${escapeHtml(stage)}">
        <div>
          <span>${escapeHtml(stageLabel)}</span>
          <strong class="execution-record-stage-status status-${escapeHtml(value || "pending")}">${escapeHtml(statusLabel)}</strong>
        </div>
        ${readOnly ? "" : `<div class="execution-record-stage-actions">
          <button type="button" class="secondary-button" data-execution-stage="${escapeHtml(stage)}" data-execution-stage-value="completed"${archived ? " disabled" : ""}>标记完成</button>
          <button type="button" class="secondary-button" data-execution-stage="${escapeHtml(stage)}" data-execution-stage-value="skipped"${archived ? " disabled" : ""}>跳过</button>
        </div>`}
      </article>
    `;
  }

  function renderRecord(recordValue, options = {}) {
    const record = objectValue(recordValue);
    const production = objectValue(record.production_status);
    const feedback = objectValue(record.feedback);
    const archived = record.status === "archived";
    const readOnly = options.readOnly === true;
    return `
      <section class="creator-execution-record" data-execution-record-version="${escapeHtml(record.version || "1.0")}">
        <div class="execution-record-summary">
          <div>
            <span>执行状态</span>
            <h4>${escapeHtml(STATUS_LABELS[record.status] || record.status || "尚未开始")}</h4>
            <p>${escapeHtml(record.selected_topic || "未命名执行方案")}</p>
          </div>
          ${archived ? '<span class="status-badge muted-badge">已归档</span>' : ""}
        </div>
        <div class="execution-record-stage-grid">
          ${renderStage("shooting", production.shooting || "pending", archived, readOnly)}
          ${renderStage("editing", production.editing || "pending", archived, readOnly)}
          ${renderStage("publishing", production.publishing || "pending", archived, readOnly)}
        </div>
        ${readOnly ? `
        <section class="execution-record-feedback execution-record-feedback-readonly" aria-label="执行反馈只读摘要">
          <div class="profile-card-heading"><div><span class="entry-label">Feedback</span><h4>执行反馈</h4></div></div>
          <dl class="iteration-readonly-facts">
            <div><dt>实际使用</dt><dd>${feedback.was_used ? "是" : "否"}</dd></div>
            <div><dt>执行难度</dt><dd>${escapeHtml(feedback.difficulty || "—")}</dd></div>
            <div><dt>方案质量</dt><dd>${escapeHtml(feedback.quality_rating ?? "—")}</dd></div>
            <div><dt>实际结果</dt><dd>${escapeHtml(feedback.result_rating ?? "—")}</dd></div>
            <div><dt>备注</dt><dd>${escapeHtml(feedback.notes || "—")}</dd></div>
          </dl>
        </section>` : `
        <section class="execution-record-feedback" aria-label="执行反馈">
          <div class="profile-card-heading">
            <div>
              <span class="entry-label">Feedback</span>
              <h4>执行反馈</h4>
            </div>
            <span class="muted compact-copy">评分可以稍后补充</span>
          </div>
          <div class="execution-record-feedback-grid">
            <label class="execution-record-check-field">
              <input type="checkbox" data-execution-feedback="was_used"${feedback.was_used ? " checked" : ""}>
              <span>已实际使用这份方案</span>
            </label>
            <label>
              <span>执行难度</span>
              <select data-execution-feedback="difficulty">
                <option value=""${selected(feedback.difficulty, "")}>暂不填写</option>
                <option value="easy"${selected(feedback.difficulty, "easy")}>简单</option>
                <option value="normal"${selected(feedback.difficulty, "normal")}>一般</option>
                <option value="hard"${selected(feedback.difficulty, "hard")}>困难</option>
              </select>
            </label>
            <label>
              <span>方案质量</span>
              <select data-execution-feedback="quality_rating">${ratingOptions(feedback.quality_rating)}</select>
            </label>
            <label>
              <span>实际结果</span>
              <select data-execution-feedback="result_rating">${ratingOptions(feedback.result_rating)}</select>
            </label>
            <label class="execution-record-notes-field">
              <span>备注</span>
              <textarea data-execution-feedback="notes" maxlength="1000" rows="4" placeholder="记录拍摄、剪辑或发布后的真实感受。">${escapeHtml(feedback.notes || "")}</textarea>
            </label>
          </div>
          <div class="execution-record-footer-actions">
            <button type="button" data-execution-record-action="save-feedback">保存反馈</button>
            ${archived ? "" : '<button type="button" class="secondary-button" data-execution-record-action="archive">归档</button>'}
          </div>
        </section>`}
      </section>
    `;
  }

  function ratingValue(value) {
    const raw = String(value ?? "").trim();
    return raw ? Number(raw) : null;
  }

  function feedbackPatch(container) {
    const field = (name) => container?.querySelector?.(`[data-execution-feedback="${name}"]`) || null;
    return {
      feedback: {
        was_used: Boolean(field("was_used")?.checked),
        difficulty: String(field("difficulty")?.value || ""),
        quality_rating: ratingValue(field("quality_rating")?.value),
        result_rating: ratingValue(field("result_rating")?.value),
        notes: String(field("notes")?.value || ""),
      },
    };
  }

  function stagePatch(stage, value) {
    if (!Object.hasOwn(STAGE_LABELS, stage) || !Object.hasOwn(PRODUCTION_LABELS, value) || value === "pending") {
      return null;
    }
    return {production_status: {[stage]: value}};
  }

  function hasRecord(container) {
    if (!container) {
      return false;
    }
    if (typeof container.querySelector === "function") {
      return Boolean(container.querySelector(".creator-execution-record"));
    }
    return String(container.innerHTML || "").includes("creator-execution-record");
  }

  global.CreatorExecutionRecordView = Object.freeze({
    feedbackPatch,
    hasRecord,
    renderRecord,
    stagePatch,
  });
})(window);
