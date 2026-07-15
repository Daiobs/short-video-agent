(function initializeWorkbenchTasks(global) {
  "use strict";

  const root = document.querySelector("[data-workbench-overview-root]");
  if (!root) {
    return;
  }

  const overviewUrl = "/api/workbench/overview";
  const maxItems = 5;
  const validRoutes = new Set(["single", "profile"]);
  const validStages = new Set(["import", "processing", "case", "pool", "select", "enrich", "distill", "export"]);
  const validResumeModes = new Set(["observe", "manual", "result"]);
  const safeResourceId = /^[A-Za-z0-9_-]{1,100}$/;
  const safeJobId = /^job_[A-Za-z0-9-]{1,80}$/;
  const sourceLabels = Object.freeze({
    jobs: "任务状态",
    cases: "Case 索引",
    creator_runtime: "Creator 索引",
    creator_sample_sets: "Creator 素材池索引",
    douyin_source: "抖音数据源",
    llm: "LLM 状态",
    preflight: "本地工具",
  });
  const statusLabels = Object.freeze({
    pending: {label: "等待中", tone: "pending"},
    running: {label: "运行中", tone: "running"},
    success: {label: "已完成", tone: "ready"},
    ready: {label: "已就绪", tone: "ready"},
    resumable: {label: "可继续", tone: "resumable"},
    recoverable: {label: "可继续", tone: "resumable"},
    failed: {label: "失败", tone: "failed"},
    missing: {label: "缺失", tone: "failed"},
    stale: {label: "可能已停止", tone: "stale"},
    disabled: {label: "未启用", tone: "neutral"},
  });

  const capabilityContainer = document.getElementById("workbench-capabilities");
  const priorityContainer = document.getElementById("workbench-priority");
  const warningContainer = document.getElementById("workbench-source-warning");
  const announcement = document.getElementById("workbench-overview-announcement");
  const refreshButton = document.getElementById("workbench-overview-refresh");
  const recentContainers = Object.freeze({
    cases: document.getElementById("workbench-recent-cases"),
    creators: document.getElementById("workbench-recent-creators"),
    strategies: document.getElementById("workbench-recent-strategies"),
    failures: document.getElementById("workbench-recent-failures"),
  });

  let requestSequence = 0;
  let actionSequence = 0;
  let latestPayload = null;
  const actions = new Map();

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function publicText(value, fallback = "", maxLength = 180) {
    const text = String(value ?? "").replace(/\s+/g, " ").trim().slice(0, maxLength);
    return text || fallback;
  }

  function itemList(value) {
    return Array.isArray(value)
      ? value.filter((item) => item && typeof item === "object").slice(0, maxItems)
      : [];
  }

  function textList(value, limit = 5) {
    return Array.isArray(value)
      ? value.map((item) => publicText(item, "", 80)).filter(Boolean).slice(0, limit)
      : [];
  }

  function safeCount(value) {
    const count = Number(value);
    return Number.isFinite(count) ? Math.max(0, Math.round(count)) : 0;
  }

  function safeProgress(value) {
    return Math.min(100, safeCount(value));
  }

  function formatTime(value) {
    const date = new Date(value || "");
    if (Number.isNaN(date.getTime())) {
      return "时间未知";
    }
    return date.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  }

  function statusMeta(value) {
    return statusLabels[String(value || "").toLowerCase()] || {label: "待确认", tone: "neutral"};
  }

  function normalizeTarget(value) {
    if (!value || typeof value !== "object") {
      return null;
    }
    const route = String(value.route || "").toLowerCase();
    if (!validRoutes.has(route)) {
      return null;
    }
    const resourceId = String(value.resource_id || "").trim();
    const jobId = String(value.job_id || "").trim();
    const taskType = String(value.task_type || "").trim().slice(0, 64);
    const stage = String(value.stage || "").toLowerCase();
    const mode = String(value.mode || "manual").toLowerCase();
    return {
      route,
      resource_id: safeResourceId.test(resourceId) ? resourceId : "",
      job_id: safeJobId.test(jobId) ? jobId : "",
      task_type: taskType,
      stage: validStages.has(stage) ? stage : "",
      mode: validResumeModes.has(mode) ? mode : "manual",
      open_url: normalizeOpenUrl(value.open_url),
    };
  }

  function normalizeOpenUrl(value) {
    const raw = String(value || "").trim();
    if (!raw) {
      return "";
    }
    let url;
    try {
      url = new URL(raw, global.location.origin);
    } catch {
      return "";
    }
    if (url.origin !== global.location.origin || url.search || url.hash) {
      return "";
    }
    const path = url.pathname;
    if (/^\/cases\/[A-Za-z0-9_-]{1,100}$/.test(path)) {
      return path;
    }
    if (/^\/api\/creator-clone\/sets\/[A-Za-z0-9_-]{1,100}\/files\/creator_clone\.(?:html|md)$/.test(path)) {
      return path;
    }
    return "";
  }

  function registerAction(action) {
    actionSequence += 1;
    const id = `overview-action-${actionSequence}`;
    actions.set(id, action);
    return id;
  }

  function actionButton(label, action, className = "") {
    const actionId = registerAction(action);
    const safeClassName = className === "primary" ? " primary" : "";
    return `<button type="button" class="workbench-row-action${safeClassName}" data-workbench-action-id="${actionId}">${escapeHtml(label)}</button>`;
  }

  function dispatchWorkbenchEvent(name, detail) {
    document.dispatchEvent(new CustomEvent(name, {detail}));
  }

  function renderCapabilities(payload) {
    if (!capabilityContainer) {
      return;
    }
    const capabilities = payload?.capabilities && typeof payload.capabilities === "object"
      ? payload.capabilities
      : {};
    const douyin = capabilities.douyin_source && typeof capabilities.douyin_source === "object"
      ? capabilities.douyin_source
      : {};
    const llm = capabilities.llm && typeof capabilities.llm === "object" ? capabilities.llm : {};
    const preflight = capabilities.preflight && typeof capabilities.preflight === "object"
      ? capabilities.preflight
      : {};
    const runningCount = safeCount(capabilities.running_task_count);
    const staleCount = safeCount(capabilities.stale_task_count);
    const douyinStatus = String(douyin.status || "unknown").toLowerCase();
    const douyinTone = douyinStatus === "success"
      ? "ready"
      : (douyinStatus === "failed" ? "failed" : (douyinStatus === "not_configured" ? "neutral" : "pending"));
    const llmTone = llm.configured ? "ready" : (String(llm.status || "") === "unknown" ? "pending" : "neutral");
    const preflightReady = safeCount(preflight.ready_count);
    const preflightTotal = safeCount(preflight.total_count);
    const preflightTone = preflightTotal && preflightReady === preflightTotal ? "ready" : "pending";
    const llmLabel = llm.configured
      ? [publicText(llm.label, "已配置", 24), publicText(llm.model, "", 48)].filter(Boolean).join(" · ")
      : publicText(llm.label, "未配置", 48);
    const items = [
      {label: "抖音数据源", value: publicText(douyin.label, "状态待确认", 48), tone: douyinTone},
      {label: "LLM", value: llmLabel, tone: llmTone},
      {label: "本地工具", value: `${preflightReady}/${preflightTotal}`, tone: preflightTone},
      {
        label: "运行任务",
        value: staleCount ? `${runningCount} 运行 · ${staleCount} 待确认` : String(runningCount),
        tone: runningCount ? "running" : (staleCount ? "pending" : "neutral"),
      },
    ];
    capabilityContainer.innerHTML = items.map((item) => `
      <div class="workbench-capability-item ${item.tone}">
        <span>${escapeHtml(item.label)}</span>
        <strong title="${escapeHtml(item.value)}">${escapeHtml(item.value)}</strong>
      </div>
    `).join("");
  }

  function partialResultNotices(meta, {hasSourceErrors = false} = {}) {
    if (!meta || typeof meta !== "object" || meta.partial !== true) {
      return [];
    }
    const truncatedSources = Array.isArray(meta.truncated_sources)
      ? meta.truncated_sources.map((item) => String(item || "")).slice(0, maxItems)
      : [];
    const notices = [];
    if (truncatedSources.includes("creator_runtime") || truncatedSources.includes("creator_sample_sets")) {
      notices.push({
        message: "创作者任务索引仅展示最近一部分记录，较早的任务或报告可能未列出。",
        followup: "完整历史浏览将在后续资产库阶段提供。",
      });
    }
    if (!notices.length && !hasSourceErrors) {
      notices.push({
        message: "任务概览当前仅返回部分结果，可用任务和最近结果仍已正常展示。",
        followup: "刷新概览后可再次检查本地索引状态。",
      });
    }
    return notices;
  }

  function renderWarnings(sourceErrors, meta = {}, {requestFailed = false} = {}) {
    if (!warningContainer) {
      return;
    }
    const errors = itemList(sourceErrors);
    const partialNotices = partialResultNotices(meta, {hasSourceErrors: Boolean(errors.length)});
    if (!requestFailed && !errors.length && !partialNotices.length) {
      warningContainer.classList.add("hidden");
      warningContainer.classList.remove("partial-only");
      warningContainer.innerHTML = "";
      return;
    }
    const details = errors.map((item) => {
      const source = sourceLabels[String(item.source || "")] || "本地数据";
      const message = publicText(item.message, "暂时不可用。", 160);
      return `<li><strong>${escapeHtml(source)}</strong><span>${escapeHtml(message)}</span></li>`;
    }).join("");
    const partialDetails = partialNotices.map((item) => `
      <div class="workbench-partial-result-note">
        <p>${escapeHtml(item.message)}</p>
        <p>${escapeHtml(item.followup)}</p>
      </div>
    `).join("");
    const partialOnly = !requestFailed && !errors.length && Boolean(partialNotices.length);
    warningContainer.classList.remove("hidden");
    if (partialOnly) {
      warningContainer.classList.add("partial-only");
    } else {
      warningContainer.classList.remove("partial-only");
    }
    warningContainer.innerHTML = `
      <strong>${requestFailed ? "任务概览暂时无法读取" : (errors.length ? "部分状态已安全降级" : "当前展示部分结果")}</strong>
      ${requestFailed || errors.length ? "<p>新建任务仍可使用；不可用的本地索引不会阻断现有工作流。</p>" : ""}
      ${partialDetails}
      ${details ? `<ul>${details}</ul>` : ""}
    `;
  }

  function renderNewTaskButton(route, title, description) {
    const actionId = registerAction({kind: "navigate", route});
    return `
      <button type="button" class="workbench-new-task-button" data-workbench-action-id="${actionId}">
        <strong>${escapeHtml(title)}</strong>
        <span>${escapeHtml(description)}</span>
      </button>
    `;
  }

  function renderNewTaskPriority() {
    return `
      <header class="workbench-section-heading">
        <div>
          <span>开始新任务</span>
          <h3 id="workbench-priority-title">选择分析对象</h3>
        </div>
      </header>
      <div class="workbench-new-task-grid">
        ${renderNewTaskButton("single", "分析单条作品", "从作品链接生成 Case 与拆解结果")}
        ${renderNewTaskButton("profile", "分析创作者账号", "导入作品池并完成富化、蒸馏与策略复用")}
      </div>
    `;
  }

  function targetAction(item, label, className = "primary") {
    const target = normalizeTarget(item?.resume_target || item?.target);
    const openUrl = target?.open_url || normalizeOpenUrl(item?.open_url);
    if (target) {
      return actionButton(label, {kind: "open-target", target, openUrl}, className);
    }
    if (openUrl) {
      return actionButton(label, {kind: "open-url", openUrl}, className);
    }
    return "";
  }

  function renderRunningTask(item, focusedTaskId) {
    const taskId = safeResourceId.test(String(item.task_id || "")) ? String(item.task_id) : "";
    const meta = statusMeta(item.status || "running");
    const progress = safeProgress(item.progress);
    const title = publicText(item.title, "后台任务", 120);
    const stage = publicText(item.stage, "处理中", 80);
    const message = publicText(item.message, "任务正在运行。", 200);
    const isFocused = Boolean(taskId && taskId === focusedTaskId);
    const viewButton = actionButton("查看任务", {kind: "refresh-task", taskId, title});
    const enterButton = targetAction(item, "进入对应页面");
    return `
      <article class="workbench-running-task${isFocused ? " is-selected" : ""}" data-overview-task-id="${escapeHtml(taskId)}" tabindex="-1">
        <header>
          <div>
            <h4>${escapeHtml(title)}</h4>
            <p>${escapeHtml(stage)} · 开始 ${escapeHtml(formatTime(item.created_at))} · 更新 ${escapeHtml(formatTime(item.updated_at))}</p>
          </div>
          <span class="workbench-item-status ${meta.tone}">${escapeHtml(meta.label)}</span>
        </header>
        <p class="workbench-task-message">${escapeHtml(message)}</p>
        <div class="workbench-task-progress">
          <progress value="${progress}" max="100">${progress}%</progress>
          <span>${progress}%</span>
        </div>
        <footer>${viewButton}${enterButton}</footer>
      </article>
    `;
  }

  function renderStaleTask(item, focusedTaskId = "") {
    const taskId = safeJobId.test(String(item.task_id || "")) ? String(item.task_id) : "";
    const title = publicText(item.title, "后台任务", 120);
    const stage = publicText(item.stage, "处理中", 80);
    const message = publicText(item.message, "任务最后一次状态已保留。", 200);
    const recoveryHint = publicText(
      item.recovery_hint,
      "请先查看状态，再进入对应步骤手动决定是否重新执行。",
      260,
    );
    const completedStage = publicText(item.last_completed_stage, "尚未确认", 100);
    const availableResults = textList(item.available_results);
    const isFocused = Boolean(taskId && taskId === focusedTaskId);
    const viewButton = actionButton("查看状态", {kind: "refresh-task", taskId, title});
    const reopenButton = targetAction(item, "重新打开当前步骤");
    return `
      <article class="workbench-stale-task${isFocused ? " is-selected" : ""}" data-overview-task-id="${escapeHtml(taskId)}" tabindex="-1">
        <header>
          <div>
            <h4>${escapeHtml(title)}</h4>
            <p>${escapeHtml(stage)} · 最后更新 ${escapeHtml(formatTime(item.updated_at))}</p>
          </div>
          <span class="workbench-item-status stale">可能已停止</span>
        </header>
        <p class="workbench-task-message">${escapeHtml(message)}</p>
        <dl class="workbench-recovery-facts">
          <div><dt>已完成到</dt><dd>${escapeHtml(completedStage)}</dd></div>
          <div><dt>仍可使用</dt><dd>${escapeHtml(availableResults.join("、") || "暂无已确认结果")}</dd></div>
        </dl>
        <p class="workbench-recovery-hint">${escapeHtml(recoveryHint)}</p>
        <p class="workbench-manual-note">只会打开和读取状态，不会自动重试或修改任务状态。</p>
        <footer>${viewButton}${reopenButton}</footer>
      </article>
    `;
  }

  function renderResumableTask(item) {
    const title = publicText(item.title, "上次任务", 120);
    const step = publicText(item.stage || item.current_step, "继续处理", 100);
    const sampleCount = safeCount(item.sample_count);
    const selectedCount = safeCount(item.selected_count);
    const reportStatus = publicText(item.report_status, "待生成", 40);
    const meta = statusMeta(item.status || "recoverable");
    const detailParts = [];
    if (sampleCount || selectedCount) {
      detailParts.push(`样本 ${selectedCount}/${sampleCount}`);
    }
    detailParts.push(`报告 ${reportStatus}`);
    detailParts.push(`更新于 ${formatTime(item.updated_at)}`);
    const recoveryHint = publicText(item.recovery_hint, "恢复后不会自动执行下一步。", 220);
    const continueButton = targetAction(item, "继续任务");
    return `
      <article class="workbench-resumable-task">
        <header>
          <div>
            <h4>${escapeHtml(title)}</h4>
            <p>${escapeHtml(step)}</p>
          </div>
          <span class="workbench-item-status ${meta.tone}">${escapeHtml(meta.label)}</span>
        </header>
        <p class="workbench-task-detail">${escapeHtml(detailParts.join(" · "))}</p>
        <p class="workbench-recovery-hint">${escapeHtml(recoveryHint)}</p>
        ${continueButton ? `<footer>${continueButton}</footer>` : ""}
      </article>
    `;
  }

  function renderPriority(payload, focusedTaskId = "") {
    if (!priorityContainer) {
      return;
    }
    const runningTasks = itemList(payload?.running_tasks);
    const staleTasks = itemList(payload?.stale_tasks);
    const resumableTasks = itemList(payload?.resumable_tasks);
    if (runningTasks.length) {
      const reportedTotal = safeCount(payload?.capabilities?.running_task_count);
      const runningTotal = Math.max(runningTasks.length, reportedTotal);
      const runningCountLabel = runningTotal > runningTasks.length
        ? `显示 ${runningTasks.length} / 共 ${runningTotal} 个运行任务`
        : `${runningTasks.length} 个任务`;
      const reportedStaleTotal = safeCount(payload?.capabilities?.stale_task_count);
      const staleTotal = Math.max(staleTasks.length, reportedStaleTotal);
      const staleCountLabel = staleTotal > staleTasks.length
        ? `显示 ${staleTasks.length} / 共 ${staleTotal} 条待人工确认`
        : `${staleTasks.length} 条待人工确认`;
      priorityContainer.innerHTML = `
        <header class="workbench-section-heading">
          <div>
            <span>实时任务</span>
            <h3 id="workbench-priority-title">正在运行</h3>
          </div>
          <strong>${escapeHtml(runningCountLabel)}</strong>
        </header>
        <div class="workbench-running-list">
          ${runningTasks.map((item) => renderRunningTask(item, focusedTaskId)).join("")}
        </div>
        ${staleTasks.length ? `
          <section class="workbench-stale-subsection" aria-label="可能已停止更新的任务">
            <header><strong>可能已停止更新</strong><span>${escapeHtml(staleCountLabel)}</span></header>
            <div class="workbench-stale-list">${staleTasks.map((item) => renderStaleTask(item, focusedTaskId)).join("")}</div>
          </section>
        ` : ""}
      `;
      return;
    }
    if (staleTasks.length) {
      const reportedTotal = safeCount(payload?.capabilities?.stale_task_count);
      const staleTotal = Math.max(staleTasks.length, reportedTotal);
      priorityContainer.innerHTML = `
        <header class="workbench-section-heading">
          <div>
            <span>人工确认</span>
            <h3 id="workbench-priority-title">任务可能已停止更新</h3>
          </div>
          <strong>${staleTotal} 个任务</strong>
        </header>
        <div class="workbench-stale-list">
          ${staleTasks.map((item) => renderStaleTask(item, focusedTaskId)).join("")}
        </div>
      `;
      return;
    }
    if (resumableTasks.length) {
      priorityContainer.innerHTML = `
        <header class="workbench-section-heading">
          <div>
            <span>任务恢复</span>
            <h3 id="workbench-priority-title">继续上次任务</h3>
          </div>
          <strong>${resumableTasks.length} 个可继续</strong>
        </header>
        <div class="workbench-resumable-list">
          ${resumableTasks.map(renderResumableTask).join("")}
        </div>
      `;
      return;
    }
    priorityContainer.innerHTML = renderNewTaskPriority();
  }

  function recentActionLabel(sectionKey, hasOpenUrl) {
    if (sectionKey === "cases") {
      return hasOpenUrl ? "打开 Case" : "进入单作品";
    }
    if (sectionKey === "failures") {
      return "进入对应页面";
    }
    return "进入报告";
  }

  function renderFailureTask(item) {
    const title = publicText(item.title, "失败任务", 120);
    const errorCode = publicText(item.error_code, "TASK_FAILED", 80);
    const message = publicText(item.message, "任务未完成。", 180);
    const completedStage = publicText(item.last_completed_stage, "尚未确认", 100);
    const availableResults = textList(item.available_results);
    const recoveryHint = publicText(
      item.recovery_hint,
      "重新打开对应页面，核对已有结果后手动决定是否继续。",
      260,
    );
    const recoveryButton = item.recoverable ? targetAction(item, "按提示恢复") : "";
    return `
      <article class="workbench-recent-item workbench-failure-item">
        <div class="workbench-recent-copy">
          <div>
            <h4>${escapeHtml(title)}</h4>
            <span class="workbench-item-status failed">失败</span>
          </div>
          <p><strong>${escapeHtml(errorCode)}</strong> · ${escapeHtml(formatTime(item.updated_at))}</p>
          <p class="workbench-recent-message">${escapeHtml(message)}</p>
          <dl class="workbench-recovery-facts compact">
            <div><dt>已完成到</dt><dd>${escapeHtml(completedStage)}</dd></div>
            <div><dt>仍可使用</dt><dd>${escapeHtml(availableResults.join("、") || "暂无已确认结果")}</dd></div>
          </dl>
          <p class="workbench-recovery-hint">${escapeHtml(recoveryHint)}</p>
        </div>
        ${recoveryButton ? `<div class="workbench-recent-actions">${recoveryButton}</div>` : ""}
      </article>
    `;
  }

  function renderRecentItem(item, sectionKey) {
    const title = publicText(item.title, "未命名记录", 120);
    const type = publicText(item.type || item.task_group, "本地记录", 60);
    const meta = sectionKey === "strategies" && String(item.status || "").toLowerCase() === "stale"
      ? {label: "需更新", tone: "pending"}
      : statusMeta(item.status);
    const target = normalizeTarget(item.resume_target || item.target);
    const openUrl = target?.open_url || normalizeOpenUrl(item.open_url);
    const primaryAction = target
      ? actionButton(recentActionLabel(sectionKey, Boolean(openUrl)), {kind: "open-target", target, openUrl}, "primary")
      : (openUrl ? actionButton(recentActionLabel(sectionKey, true), {kind: "open-url", openUrl}, "primary") : "");
    const exportAction = target?.route === "profile" && openUrl
      ? actionButton("打开导出", {kind: "open-url", openUrl})
      : "";
    const message = sectionKey === "failures" ? publicText(item.message, "", 140) : "";
    return `
      <article class="workbench-recent-item">
        <div class="workbench-recent-copy">
          <div>
            <h4>${escapeHtml(title)}</h4>
            <span class="workbench-item-status ${meta.tone}">${escapeHtml(meta.label)}</span>
          </div>
          <p>${escapeHtml(type)} · ${escapeHtml(formatTime(item.updated_at))}</p>
          ${message ? `<p class="workbench-recent-message">${escapeHtml(message)}</p>` : ""}
        </div>
        ${primaryAction || exportAction ? `<div class="workbench-recent-actions">${primaryAction}${exportAction}</div>` : ""}
      </article>
    `;
  }

  function renderRecentList(container, items, sectionKey, emptyLabel) {
    if (!container) {
      return;
    }
    const safeItems = itemList(items);
    container.innerHTML = safeItems.length
      ? safeItems.map((item) => sectionKey === "failures" ? renderFailureTask(item) : renderRecentItem(item, sectionKey)).join("")
      : `<p class="workbench-empty-state">${escapeHtml(emptyLabel)}</p>`;
  }

  function renderRecents(payload, {requestFailed = false} = {}) {
    const suffix = requestFailed ? "概览暂不可用" : "暂无记录";
    renderRecentList(recentContainers.cases, payload?.recent_cases, "cases", `最近 Case：${suffix}`);
    renderRecentList(recentContainers.creators, payload?.recent_creator_reports, "creators", `Creator 报告：${suffix}`);
    renderRecentList(recentContainers.strategies, payload?.recent_strategy_plans, "strategies", `Strategy Plan：${suffix}`);
    renderRecentList(recentContainers.failures, payload?.recent_failures, "failures", `失败任务：${suffix}`);
  }

  function renderOverview(payload, {focusedTaskId = ""} = {}) {
    actions.clear();
    actionSequence = 0;
    latestPayload = payload;
    renderCapabilities(payload);
    renderWarnings(payload?.source_errors, payload?.meta);
    renderPriority(payload, focusedTaskId);
    renderRecents(payload);
  }

  function renderRequestFailure() {
    actions.clear();
    actionSequence = 0;
    latestPayload = null;
    renderCapabilities({capabilities: {}});
    renderWarnings([], {}, {requestFailed: true});
    if (priorityContainer) {
      priorityContainer.innerHTML = renderNewTaskPriority();
    }
    renderRecents({}, {requestFailed: true});
  }

  function focusRunningTask(taskId) {
    if (!taskId || !priorityContainer) {
      return false;
    }
    const card = Array.from(priorityContainer.querySelectorAll("[data-overview-task-id]"))
      .find((item) => item.dataset.overviewTaskId === taskId);
    if (!card) {
      return false;
    }
    card.focus({preventScroll: true});
    card.scrollIntoView({behavior: "smooth", block: "nearest"});
    return true;
  }

  async function loadOverview({focusedTaskId = "", taskTitle = ""} = {}) {
    requestSequence += 1;
    const requestId = requestSequence;
    root.setAttribute("aria-busy", "true");
    if (refreshButton) {
      refreshButton.disabled = true;
    }
    if (announcement) {
      announcement.textContent = taskTitle ? `正在刷新「${publicText(taskTitle, "当前任务", 80)}」...` : "正在刷新任务概览...";
    }
    try {
      const response = await fetch(overviewUrl, {
        cache: "no-store",
        headers: {Accept: "application/json"},
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok || !payload || payload.ok === false || typeof payload !== "object") {
        throw new Error("overview unavailable");
      }
      if (requestId !== requestSequence) {
        return;
      }
      renderOverview(payload, {focusedTaskId});
      const focused = focusRunningTask(focusedTaskId);
      if (announcement) {
        announcement.textContent = focusedTaskId
          ? (focused ? "任务状态已刷新，当前任务卡已显示。" : "任务已离开运行队列，概览已更新。")
          : `概览更新于 ${new Date().toLocaleTimeString("zh-CN", {hour: "2-digit", minute: "2-digit", hour12: false})}`;
      }
    } catch {
      if (requestId !== requestSequence) {
        return;
      }
      renderRequestFailure();
      if (announcement) {
        announcement.textContent = "概览读取失败；新建任务入口仍可使用。";
      }
    } finally {
      if (requestId === requestSequence) {
        root.setAttribute("aria-busy", "false");
        if (refreshButton) {
          refreshButton.disabled = false;
        }
      }
    }
  }

  root.addEventListener("click", (event) => {
    const staticRouteButton = event.target.closest("[data-workbench-static-route]");
    if (staticRouteButton && root.contains(staticRouteButton)) {
      const route = String(staticRouteButton.dataset.workbenchStaticRoute || "");
      if (validRoutes.has(route)) {
        dispatchWorkbenchEvent("workbench:navigate", {route});
      }
      return;
    }
    const button = event.target.closest("[data-workbench-action-id]");
    if (!button || !root.contains(button)) {
      return;
    }
    const action = actions.get(button.dataset.workbenchActionId);
    if (!action) {
      return;
    }
    if (action.kind === "refresh-task") {
      loadOverview({focusedTaskId: action.taskId, taskTitle: action.title});
      return;
    }
    if (action.kind === "navigate" && validRoutes.has(action.route)) {
      dispatchWorkbenchEvent("workbench:navigate", {route: action.route});
      return;
    }
    if (action.kind === "open-target") {
      dispatchWorkbenchEvent("workbench:open-target", {target: action.target, open_url: action.openUrl});
      return;
    }
    if (action.kind === "open-url" && action.openUrl) {
      dispatchWorkbenchEvent("workbench:open-url", {open_url: action.openUrl});
    }
  });

  refreshButton?.addEventListener("click", () => loadOverview());

  document.addEventListener("workbench:target-result", (event) => {
    if (announcement && event.detail?.ok === false) {
      announcement.textContent = publicText(event.detail.message, "无法恢复指定任务，请从对应页面重新导入。", 160);
    }
  });

  global.WorkbenchTasks = Object.freeze({
    refresh: () => loadOverview(),
    getLatestOverview: () => latestPayload,
    normalizeResumeTarget: (value) => normalizeTarget(value),
  });

  loadOverview();
})(window);
