(function initializeCreatorIterationHistoryView(global) {
  "use strict";

  const ARTIFACT_LABELS = Object.freeze({
    "execution-pack": "Execution Pack",
    "execution-record": "Execution Record",
    outcome: "Outcome Timeline",
  });
  const RECORD_LABELS = Object.freeze({
    missing: "未生成",
    invalid: "不可读取",
    draft: "尚未开始",
    in_progress: "执行中",
    completed: "已完成",
    archived: "已归档",
  });
  const STATE_LABELS = Object.freeze({active: "当前", closed: "已结束"});

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

  function listValue(value) {
    return Array.isArray(value) ? value : [];
  }

  function formatMetric(value) {
    if (value === null || value === undefined || value === "") {
      return "—";
    }
    const number = Number(value);
    return Number.isFinite(number) ? number.toLocaleString("zh-CN") : "—";
  }

  function formatDate(value) {
    const raw = String(value || "").trim();
    if (!raw) {
      return "—";
    }
    const parsed = new Date(raw);
    return Number.isNaN(parsed.getTime()) ? escapeHtml(raw) : escapeHtml(parsed.toLocaleString("zh-CN"));
  }

  function currentFacts(summaryValue) {
    const summary = objectValue(summaryValue);
    const production = objectValue(summary.production_status);
    return `
      <div class="creator-iteration-current-facts">
        <div><span>当前选题</span><strong>${escapeHtml(summary.selected_topic || "尚未选择")}</strong></div>
        <div><span>执行方案</span><strong>${escapeHtml(summary.execution_pack_status === "ready" ? "已生成" : summary.execution_pack_status === "invalid" ? "不可读取" : "未生成")}</strong></div>
        <div><span>执行状态</span><strong>${escapeHtml(RECORD_LABELS[summary.execution_record_status] || summary.execution_record_status || "未生成")}</strong></div>
        <div><span>发布状态</span><strong>${escapeHtml(production.publishing === "completed" ? "已发布" : production.publishing === "skipped" ? "已跳过" : "未完成")}</strong></div>
        <div><span>结果快照</span><strong>${formatMetric(summary.snapshot_count)}</strong></div>
      </div>
    `;
  }

  function startNextControls(policyValue, hasIterations) {
    if (!hasIterations) {
      return '<p class="muted compact-copy">生成第一份 Execution Pack 后，系统会将它识别为第 1 轮；无需预先创建轮次。</p>';
    }
    const policy = objectValue(policyValue);
    const explicit = policy.requires_explicit_close === true;
    return `
      <div class="creator-iteration-start-controls" data-iteration-explicit-close="${explicit ? "true" : "false"}">
        ${explicit ? `
          <label>
            <span>结束当前轮次</span>
            <select data-iteration-close-reason>
              <option value="">请选择原因</option>
              <option value="cancelled">取消本轮</option>
              <option value="superseded">被新方案替代</option>
              <option value="not_published">未发布结束</option>
              <option value="other">其它</option>
            </select>
          </label>
          <label class="creator-iteration-close-note">
            <span>备注（可选）</span>
            <input type="text" maxlength="500" data-iteration-close-note placeholder="只记录结束原因，不填写密钥或登录信息">
          </label>
        ` : `<p class="muted compact-copy">当前执行已结束，可以安全开始下一轮。</p>`}
        <button type="button" data-iteration-action="start-next">开始下一轮</button>
      </div>
    `;
  }

  function historyItem(summaryValue) {
    const summary = objectValue(summaryValue);
    const metrics = objectValue(summary.latest_metrics);
    return `
      <li class="creator-iteration-history-item${summary.is_current ? " is-current" : ""}" data-iteration-id="${escapeHtml(summary.iteration_id || "")}">
        <div class="creator-iteration-history-heading">
          <div>
            <span class="status-badge ${summary.is_current ? "" : "muted-badge"}">${escapeHtml(STATE_LABELS[summary.state] || summary.state || "未知")}</span>
            <strong>${escapeHtml(summary.label || `第 ${summary.sequence || "—"} 轮`)}</strong>
          </div>
          <button type="button" class="secondary-button" data-iteration-action="open" data-iteration-id="${escapeHtml(summary.iteration_id || "")}">查看只读详情</button>
        </div>
        <p>${escapeHtml(summary.selected_topic || "尚未选择选题")}</p>
        <dl class="creator-iteration-history-facts">
          <div><dt>执行</dt><dd>${escapeHtml(RECORD_LABELS[summary.execution_record_status] || summary.execution_record_status || "—")}</dd></div>
          <div><dt>发布</dt><dd>${escapeHtml(objectValue(summary.production_status).publishing || "—")}</dd></div>
          <div><dt>快照</dt><dd>${formatMetric(summary.snapshot_count)}</dd></div>
          <div><dt>播放</dt><dd>${formatMetric(metrics.views)}</dd></div>
          <div><dt>点赞</dt><dd>${formatMetric(metrics.likes)}</dd></div>
          <div><dt>评论</dt><dd>${formatMetric(metrics.comments)}</dd></div>
        </dl>
        <p class="muted compact-copy">创建 ${formatDate(summary.created_at)} · 结束 ${formatDate(summary.closed_at)}</p>
      </li>
    `;
  }

  function renderOverview(payloadValue) {
    const payload = objectValue(payloadValue);
    const iterations = listValue(payload.iterations);
    const current = iterations.find((item) => objectValue(item).is_current) || null;
    return `
      <div class="creator-iteration-overview" data-current-iteration-id="${escapeHtml(payload.current_iteration_id || "")}">
        <div class="creator-iteration-current">
          <div class="creator-iteration-current-heading">
            <div>
              <span class="entry-label">Iteration</span>
              <h4>${current ? `当前第 ${escapeHtml(current.sequence)} 轮` : "尚未开始创作迭代"}</h4>
            </div>
            ${current ? `<span class="status-badge">${escapeHtml(current.storage_mode === "legacy_root" ? "兼容旧轮次" : "当前轮次")}</span>` : ""}
          </div>
          ${current ? currentFacts(current) : ""}
          ${startNextControls(payload.current_policy, iterations.length > 0)}
          <div class="inline-status muted" data-iteration-status aria-live="polite"></div>
        </div>
        <details class="creator-iteration-history"${iterations.length > 1 ? "" : ""}>
          <summary>历史迭代${iterations.length ? ` · ${iterations.length} 轮` : ""}</summary>
          ${iterations.length
            ? `<ol>${iterations.slice().reverse().map(historyItem).join("")}</ol>`
            : '<p class="muted">尚无历史轮次。</p>'}
          <div class="creator-iteration-detail" data-iteration-detail aria-live="polite"></div>
        </details>
      </div>
    `;
  }

  function startNextPayload(container) {
    const controls = container?.querySelector?.("[data-iteration-explicit-close]");
    const explicit = controls?.dataset?.iterationExplicitClose === "true";
    const closeReason = String(container?.querySelector?.("[data-iteration-close-reason]")?.value || "");
    const closeNote = String(container?.querySelector?.("[data-iteration-close-note]")?.value || "");
    if (explicit && !closeReason) {
      return null;
    }
    return {
      close_current: explicit,
      close_reason: explicit ? closeReason : "",
      close_note: explicit ? closeNote : "",
    };
  }

  function setBusy(container, busy, message = "") {
    container?.querySelectorAll?.("button, input, select").forEach((control) => {
      control.disabled = Boolean(busy);
    });
    const button = container?.querySelector?.('[data-iteration-action="start-next"]');
    if (button) {
      button.textContent = busy ? "正在开始..." : "开始下一轮";
    }
    const status = container?.querySelector?.("[data-iteration-status]");
    if (status && message) {
      status.textContent = message;
    }
  }

  function artifactMarkup(name, availability, payload, views) {
    const label = ARTIFACT_LABELS[name] || name;
    if (availability !== "ready" || !payload) {
      return `<section class="creator-iteration-artifact"><h5>${escapeHtml(label)}</h5><p class="muted">${availability === "invalid" ? "产物不可安全读取。" : "尚未生成。"}</p></section>`;
    }
    let body = "";
    if (name === "execution-pack") {
      body = views.pack?.renderPack?.(payload) || "";
    } else if (name === "execution-record") {
      body = views.record?.renderRecord?.(payload, {readOnly: true}) || "";
    } else if (name === "outcome") {
      body = views.outcome?.renderOutcome?.(payload, {readOnly: true}) || "";
    }
    return `<section class="creator-iteration-artifact" data-history-artifact="${escapeHtml(name)}"><h5>${escapeHtml(label)}</h5>${body || '<p class="muted">无法渲染该产物。</p>'}</section>`;
  }

  function renderDetail(detailValue, artifactsValue, views = {}) {
    const detail = objectValue(detailValue);
    const summary = objectValue(detail.summary);
    const availability = objectValue(detail.artifact_availability);
    const artifacts = objectValue(artifactsValue);
    return `
      <section class="creator-iteration-detail-card" data-history-iteration-id="${escapeHtml(summary.iteration_id || "")}">
        <div class="profile-card-heading">
          <div><span class="entry-label">Read only</span><h4>${escapeHtml(summary.label || "创作迭代详情")}</h4></div>
          <span class="status-badge muted-badge">历史只读</span>
        </div>
        ${artifactMarkup("execution-pack", availability.execution_pack, artifacts["execution-pack"], views)}
        ${artifactMarkup("execution-record", availability.execution_record, artifacts["execution-record"], views)}
        ${artifactMarkup("outcome", availability.outcome, artifacts.outcome, views)}
      </section>
    `;
  }

  global.CreatorIterationHistoryView = Object.freeze({
    formatMetric,
    renderDetail,
    renderOverview,
    setBusy,
    startNextPayload,
  });
})(window);
