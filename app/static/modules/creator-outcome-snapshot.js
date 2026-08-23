(function initializeCreatorOutcomeSnapshotView(global) {
  "use strict";

  const METRIC_FIELDS = Object.freeze(["views", "likes", "comments", "shares", "collects"]);
  const METRIC_LABELS = Object.freeze({
    views: "播放",
    likes: "点赞",
    comments: "评论",
    shares: "分享",
    collects: "收藏",
  });
  const RATE_LABELS = Object.freeze({
    like_rate: "点赞率",
    comment_rate: "评论率",
    share_rate: "分享率",
    collect_rate: "收藏率",
    engagement_rate: "综合互动率",
  });
  const PLATFORM_LABELS = Object.freeze({
    douyin: "抖音",
    xhs: "小红书",
    bili: "哔哩哔哩",
    other: "其他",
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

  function listValue(value) {
    return Array.isArray(value) ? value : [];
  }

  function selected(value, expected) {
    return String(value ?? "") === String(expected) ? " selected" : "";
  }

  function formatMetric(value) {
    if (value === null || value === undefined || value === "") {
      return "—";
    }
    const number = Number(value);
    return Number.isFinite(number) ? number.toLocaleString("zh-CN") : "—";
  }

  function formatRate(value) {
    if (value === null || value === undefined || value === "") {
      return "—";
    }
    const number = Number(value);
    return Number.isFinite(number) ? `${(number * 100).toFixed(2)}%` : "—";
  }

  function formatDelta(value) {
    if (value === null || value === undefined || value === "") {
      return "";
    }
    const number = Number(value);
    if (!Number.isFinite(number)) {
      return "";
    }
    return number >= 0 ? `+${formatMetric(number)}` : formatMetric(number);
  }

  function metricInputs(kind, metricsValue = {}) {
    const metrics = objectValue(metricsValue);
    return METRIC_FIELDS.map((field) => `
      <label>
        <span>${METRIC_LABELS[field]}</span>
        <input
          type="number"
          min="0"
          step="1"
          inputmode="numeric"
          data-outcome-${escapeHtml(kind)}-metric="${escapeHtml(field)}"
          value="${metrics[field] === null || metrics[field] === undefined ? "" : escapeHtml(metrics[field])}"
          placeholder="未知可留空"
        >
      </label>
    `).join("");
  }

  function publicationForm(publicationValue = {}) {
    const publication = objectValue(publicationValue);
    return `
      <section class="creator-outcome-publication">
        <div class="profile-card-heading">
          <div>
            <span class="entry-label">Publication</span>
            <h5>作品信息</h5>
          </div>
          <span class="muted compact-copy">仅保存，不访问链接</span>
        </div>
        <div class="creator-outcome-publication-grid">
          <label>
            <span>平台</span>
            <select data-outcome-publication="platform">
              ${Object.entries(PLATFORM_LABELS).map(([value, label]) => `<option value="${value}"${selected(publication.platform || "douyin", value)}>${label}</option>`).join("")}
            </select>
          </label>
          <label>
            <span>作品 ID</span>
            <input type="text" maxlength="160" data-outcome-publication="platform_item_id" value="${escapeHtml(publication.platform_item_id || "")}" placeholder="可留空">
          </label>
          <label class="creator-outcome-wide-field">
            <span>发布链接</span>
            <input type="url" maxlength="2048" data-outcome-publication="published_url" value="${escapeHtml(publication.published_url || "")}" placeholder="https://...">
          </label>
          <label class="creator-outcome-wide-field">
            <span>发布时间</span>
            <input type="text" data-outcome-publication="published_at" value="${escapeHtml(publication.published_at || "")}" placeholder="2026-08-10T09:30:00+08:00">
          </label>
        </div>
        <button type="button" data-outcome-action="save-publication">保存发布信息</button>
      </section>
    `;
  }

  function latestMetrics(outcome) {
    const summary = objectValue(outcome.summary);
    const metrics = objectValue(summary.latest_metrics);
    const derived = objectValue(summary.latest_derived);
    return `
      <section class="creator-outcome-latest">
        <div class="profile-card-heading">
          <div>
            <span class="entry-label">Latest</span>
            <h5>最新数据</h5>
          </div>
          <span class="muted compact-copy">${summary.snapshot_count || 0} 次记录</span>
        </div>
        <div class="creator-outcome-metric-grid">
          ${METRIC_FIELDS.map((field) => `
            <article>
              <span>${METRIC_LABELS[field]}</span>
              <strong>${formatMetric(metrics[field])}</strong>
            </article>
          `).join("")}
        </div>
        <div class="creator-outcome-rate-grid">
          ${Object.entries(RATE_LABELS).map(([field, label]) => `
            <div><span>${label}</span><strong>${formatRate(derived[field])}</strong></div>
          `).join("")}
        </div>
      </section>
    `;
  }

  function historyItem(snapshotValue) {
    const snapshot = objectValue(snapshotValue);
    const metrics = objectValue(snapshot.metrics);
    const derived = objectValue(snapshot.derived);
    const delta = objectValue(derived.delta_from_previous);
    return `
      <li class="creator-outcome-history-item" data-outcome-snapshot-id="${escapeHtml(snapshot.snapshot_id || "")}">
        <div class="creator-outcome-history-heading">
          <strong>${escapeHtml(snapshot.captured_at || "未知时间")}</strong>
          <span class="muted">人工记录</span>
        </div>
        <dl class="creator-outcome-history-metrics">
          ${METRIC_FIELDS.map((field) => `
            <div>
              <dt>${METRIC_LABELS[field]}</dt>
              <dd>${formatMetric(metrics[field])}${formatDelta(delta[field]) ? `<small>${formatDelta(delta[field])}</small>` : ""}</dd>
            </div>
          `).join("")}
        </dl>
        <details class="creator-outcome-edit-details">
          <summary>修正数据</summary>
          <div class="creator-outcome-snapshot-grid">${metricInputs("edit", metrics)}</div>
          <button type="button" class="secondary-button" data-outcome-action="save-snapshot">保存修正</button>
        </details>
      </li>
    `;
  }

  function historyItemReadOnly(snapshotValue) {
    const snapshot = objectValue(snapshotValue);
    const metrics = objectValue(snapshot.metrics);
    const derived = objectValue(snapshot.derived);
    const delta = objectValue(derived.delta_from_previous);
    return `
      <li class="creator-outcome-history-item" data-outcome-snapshot-id="${escapeHtml(snapshot.snapshot_id || "")}">
        <div class="creator-outcome-history-heading">
          <strong>${escapeHtml(snapshot.captured_at || "未知时间")}</strong>
          <span class="muted">人工记录</span>
        </div>
        <dl class="creator-outcome-history-metrics">
          ${METRIC_FIELDS.map((field) => `
            <div><dt>${METRIC_LABELS[field]}</dt><dd>${formatMetric(metrics[field])}${formatDelta(delta[field]) ? `<small>${formatDelta(delta[field])}</small>` : ""}</dd></div>
          `).join("")}
        </dl>
      </li>
    `;
  }

  function publicationSummary(publicationValue = {}) {
    const publication = objectValue(publicationValue);
    return `
      <section class="creator-outcome-publication creator-outcome-publication-readonly">
        <div class="profile-card-heading"><div><span class="entry-label">Publication</span><h5>作品信息</h5></div></div>
        <dl class="iteration-readonly-facts">
          <div><dt>平台</dt><dd>${escapeHtml(PLATFORM_LABELS[publication.platform] || publication.platform || "—")}</dd></div>
          <div><dt>作品 ID</dt><dd>${escapeHtml(publication.platform_item_id || "—")}</dd></div>
          <div><dt>发布时间</dt><dd>${escapeHtml(publication.published_at || "—")}</dd></div>
        </dl>
      </section>
    `;
  }

  function renderPublicationOnly() {
    return `
      <div class="creator-outcome" data-outcome-state="publication">
        ${publicationForm({platform: "douyin"})}
      </div>
    `;
  }

  function renderLocked() {
    return `
      <div class="creator-outcome creator-outcome-locked" data-outcome-state="locked">
        <p>完成“发布”后即可记录真实表现。</p>
      </div>
    `;
  }

  function renderOutcome(outcomeValue, options = {}) {
    const outcome = objectValue(outcomeValue);
    const snapshots = listValue(outcome.snapshots).slice().reverse();
    const readOnly = options.readOnly === true;
    return `
      <div class="creator-outcome" data-outcome-state="ready" data-outcome-version="${escapeHtml(outcome.version || "1.0")}">
        ${readOnly ? publicationSummary(outcome.publication) : publicationForm(outcome.publication)}
        <section class="creator-outcome-expectation">
          <span>预期关注指标</span>
          <strong>${escapeHtml(outcome.expected_metric || "未绑定")}</strong>
        </section>
        ${latestMetrics(outcome)}
        ${readOnly ? "" : `<section class="creator-outcome-new-snapshot">
          <div class="profile-card-heading">
            <div>
              <span class="entry-label">Measure</span>
              <h5>新增数据快照</h5>
            </div>
            <span class="muted compact-copy">未知项请留空</span>
          </div>
          <div class="creator-outcome-snapshot-grid">${metricInputs("new")}</div>
          <button type="button" data-outcome-action="add-snapshot">记录当前数据</button>
        </section>`}
        <section class="creator-outcome-history">
          <div class="profile-card-heading">
            <div>
              <span class="entry-label">History</span>
              <h5>数据快照历史</h5>
            </div>
          </div>
          ${snapshots.length ? `<ol>${snapshots.map(readOnly ? historyItemReadOnly : historyItem).join("")}</ol>` : '<p class="muted">还没有数据快照。</p>'}
        </section>
      </div>
    `;
  }

  function publicationPayload(container) {
    const field = (name) => container?.querySelector?.(`[data-outcome-publication="${name}"]`) || null;
    return {
      platform: String(field("platform")?.value || "douyin"),
      platform_item_id: String(field("platform_item_id")?.value || "").trim(),
      published_url: String(field("published_url")?.value || "").trim(),
      published_at: String(field("published_at")?.value || "").trim() || null,
    };
  }

  function metricsPayload(container, kind) {
    const payload = {};
    for (const field of METRIC_FIELDS) {
      const input = container?.querySelector?.(`[data-outcome-${kind}-metric="${field}"]`) || null;
      const raw = String(input?.value ?? "").trim();
      if (!raw) {
        payload[field] = null;
        continue;
      }
      const value = Number(raw);
      if (!Number.isInteger(value) || value < 0) {
        return null;
      }
      payload[field] = value;
    }
    return payload;
  }

  function hasOutcome(container) {
    if (!container) {
      return false;
    }
    if (typeof container.querySelector === "function") {
      return Boolean(container.querySelector('.creator-outcome[data-outcome-state="ready"]'));
    }
    return String(container.innerHTML || "").includes('data-outcome-state="ready"');
  }

  global.CreatorOutcomeSnapshotView = Object.freeze({
    formatMetric,
    formatRate,
    hasOutcome,
    metricsPayload,
    publicationPayload,
    renderLocked,
    renderOutcome,
    renderPublicationOnly,
  });
})(window);
