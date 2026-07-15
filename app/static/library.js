(function initializeLibraryPage(global) {
  "use strict";

  const ASSET_TYPES = new Set(["case", "creator_report", "strategy_plan"]);
  const ASSET_STATUSES = new Set(["ready", "incomplete", "missing", "stale"]);
  const CREATOR_STAGES = new Set(["import", "pool", "select", "enrich", "distill", "export"]);
  const RESUME_STORAGE_KEY = "shortVideoAgent.library.resumeTarget.v1";
  const TYPE_LABELS = Object.freeze({
    case: "单作品 Case",
    creator_report: "创作者报告",
    strategy_plan: "策略方案",
  });
  const STATUS_LABELS = Object.freeze({
    ready: "可用",
    incomplete: "不完整",
    missing: "文件缺失",
    stale: "可能陈旧",
  });

  function safeText(value, fallback = "") {
    return String(value == null ? fallback : value).slice(0, 240);
  }

  function isSafeResourceId(value) {
    return /^(?:case|clone)_[A-Za-z0-9_-]{1,94}$/.test(String(value || ""));
  }

  function safeOpenUrl(value) {
    const candidate = String(value || "").trim();
    if (/^\/cases\/case_[A-Za-z0-9_-]{1,94}$/.test(candidate)) {
      return candidate;
    }
    if (/^\/api\/creator-clone\/sets\/clone_[A-Za-z0-9_-]{1,94}\/files\/creator_clone\.(?:html|md)$/.test(candidate)) {
      return candidate;
    }
    return "";
  }

  function normalizeResumeTarget(value) {
    const target = value && typeof value === "object" ? value : {};
    const route = ["single", "profile"].includes(target.route) ? target.route : "";
    const resourceId = isSafeResourceId(target.resource_id) ? String(target.resource_id) : "";
    if (!route || !resourceId) {
      return null;
    }
    const stage = route === "profile" && CREATOR_STAGES.has(target.stage) ? target.stage : (route === "single" ? "case" : "export");
    return {
      route,
      stage,
      resource_id: resourceId,
      job_id: "",
      task_type: safeText(target.task_type, "library_asset"),
      mode: "result",
      open_url: safeOpenUrl(target.open_url),
    };
  }

  function partialMessages(payload) {
    const messages = [];
    const sourceErrors = Array.isArray(payload?.source_errors) ? payload.source_errors : [];
    sourceErrors.forEach((item) => {
      const message = safeText(item?.message);
      if (message && !messages.includes(message)) {
        messages.push(message);
      }
    });
    const truncated = new Set(Array.isArray(payload?.meta?.truncated_sources) ? payload.meta.truncated_sources : []);
    if (truncated.has("creator_runtime")) {
      messages.push("创作者 Runtime 已达到安全读取上限；资产库仍展示已索引的最近产物，较早记录可能未列出。");
    }
    if (truncated.has("cases")) {
      messages.push("Case 索引已达到本地安全读取上限，当前仅展示最近一部分记录。");
    }
    if (truncated.has("creator_assets")) {
      messages.push("Creator 资产索引已达到安全读取或文件大小上限，部分记录或文件未完整索引。");
    }
    return [...new Set(messages)];
  }

  function formatDate(value) {
    const date = new Date(String(value || ""));
    if (Number.isNaN(date.getTime())) {
      return "未知";
    }
    return date.toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  }

  function buildApiUrl(state) {
    const params = new URLSearchParams();
    if (state.type && ASSET_TYPES.has(state.type)) params.set("type", state.type);
    if (state.status && ASSET_STATUSES.has(state.status)) params.set("status", state.status);
    if (state.query) params.set("query", state.query.slice(0, 120));
    if (state.dateFrom) params.set("date_from", state.dateFrom);
    if (state.dateTo) params.set("date_to", state.dateTo);
    params.set("page", String(Math.max(1, Number(state.page) || 1)));
    params.set("page_size", String(Math.min(100, Math.max(1, Number(state.pageSize) || 20))));
    return `/api/library/assets?${params.toString()}`;
  }

  function appendText(parent, tag, text, className = "") {
    const node = parent.ownerDocument.createElement(tag);
    node.textContent = safeText(text);
    if (className) node.className = className;
    parent.appendChild(node);
    return node;
  }

  function renderAssetRow(documentRef, asset, onReturnToCreator) {
    const row = documentRef.createElement("tr");
    row.className = "library-asset-row";

    const typeCell = documentRef.createElement("td");
    typeCell.dataset.label = "类型 / 状态";
    appendText(typeCell, "span", TYPE_LABELS[asset.asset_type] || "未知资产", "library-type-label");
    appendText(typeCell, "span", STATUS_LABELS[asset.status] || "状态未知", `library-status-badge ${ASSET_STATUSES.has(asset.status) ? asset.status : "incomplete"}`);
    row.appendChild(typeCell);

    const assetCell = documentRef.createElement("td");
    assetCell.dataset.label = "资产";
    appendText(assetCell, "strong", asset.title || "未命名资产");
    appendText(assetCell, "code", asset.asset_id || "", "library-asset-id");
    const files = Array.isArray(asset.available_files) ? asset.available_files.slice(0, 5) : [];
    if (files.length) {
      const fileList = documentRef.createElement("div");
      fileList.className = "library-file-list";
      files.forEach((name) => appendText(fileList, "span", name));
      if (asset.available_files.length > files.length) {
        appendText(fileList, "span", `+${asset.available_files.length - files.length}`);
      }
      assetCell.appendChild(fileList);
    }
    row.appendChild(assetCell);

    const creatorCell = documentRef.createElement("td");
    creatorCell.dataset.label = "创作者";
    appendText(creatorCell, "span", asset.creator_name || "未记录");
    appendText(creatorCell, "small", asset.platform || "unknown");
    row.appendChild(creatorCell);

    const sampleCell = documentRef.createElement("td");
    sampleCell.dataset.label = "样本";
    if (asset.asset_type === "case") {
      appendText(sampleCell, "span", "单条作品");
    } else {
      appendText(sampleCell, "span", `${Number(asset.selected_count) || 0} / ${Number(asset.sample_count) || 0} 已选`);
    }
    if (asset.quality_score != null) {
      appendText(sampleCell, "small", `质量 ${asset.quality_score}`);
    }
    row.appendChild(sampleCell);

    const dateCell = documentRef.createElement("td");
    dateCell.dataset.label = "更新时间";
    appendText(dateCell, "time", formatDate(asset.updated_at || asset.created_at));
    row.appendChild(dateCell);

    const actionCell = documentRef.createElement("td");
    actionCell.dataset.label = "操作";
    actionCell.className = "library-row-actions";
    const openUrl = safeOpenUrl(asset.open_url);
    if (openUrl) {
      const link = documentRef.createElement("a");
      link.href = openUrl;
      link.className = "library-open-button";
      link.textContent = asset.asset_type === "case" ? "打开 Case" : "打开报告";
      if (asset.asset_type !== "case") {
        link.target = "_blank";
        link.rel = "noopener noreferrer";
      }
      actionCell.appendChild(link);
    }
    const target = normalizeResumeTarget(asset.resume_target);
    if (target?.route === "profile") {
      const button = documentRef.createElement("button");
      button.type = "button";
      button.className = "ghost-button";
      button.textContent = "返回 Creator";
      button.addEventListener("click", () => onReturnToCreator(target));
      actionCell.appendChild(button);
    }
    if (!actionCell.children.length) {
      appendText(actionCell, "span", "暂无可用入口", "library-no-action");
    }
    row.appendChild(actionCell);
    return row;
  }

  function initLibraryPage(documentRef) {
    const root = documentRef.querySelector("[data-library-root]");
    if (!root) return null;
    const elements = {
      form: documentRef.getElementById("library-filters"),
      query: documentRef.getElementById("library-query"),
      type: documentRef.getElementById("library-type"),
      status: documentRef.getElementById("library-status"),
      dateFrom: documentRef.getElementById("library-date-from"),
      dateTo: documentRef.getElementById("library-date-to"),
      pageSize: documentRef.getElementById("library-page-size"),
      items: documentRef.getElementById("library-items"),
      empty: documentRef.getElementById("library-empty"),
      announcement: documentRef.getElementById("library-announcement"),
      warning: documentRef.getElementById("library-source-warning"),
      resultCount: documentRef.getElementById("library-result-count"),
      pageLabel: documentRef.getElementById("library-page-label"),
      previous: documentRef.getElementById("library-page-previous"),
      next: documentRef.getElementById("library-page-next"),
      refresh: documentRef.getElementById("library-refresh"),
      reset: documentRef.getElementById("library-filter-reset"),
      total: documentRef.getElementById("library-total-count"),
      caseCount: documentRef.getElementById("library-case-count"),
      reportCount: documentRef.getElementById("library-report-count"),
      strategyCount: documentRef.getElementById("library-strategy-count"),
    };
    const urlParams = new URLSearchParams(global.location?.search || "");
    const state = {
      type: ASSET_TYPES.has(urlParams.get("type")) ? urlParams.get("type") : "",
      status: ASSET_STATUSES.has(urlParams.get("status")) ? urlParams.get("status") : "",
      query: safeText(urlParams.get("query"), "").slice(0, 120),
      dateFrom: safeText(urlParams.get("date_from"), ""),
      dateTo: safeText(urlParams.get("date_to"), ""),
      page: Math.max(1, Number(urlParams.get("page")) || 1),
      pageSize: [20, 50, 100].includes(Number(urlParams.get("page_size"))) ? Number(urlParams.get("page_size")) : 20,
      requestId: 0,
    };
    elements.type.value = state.type;
    elements.status.value = state.status;
    elements.query.value = state.query;
    elements.dateFrom.value = state.dateFrom;
    elements.dateTo.value = state.dateTo;
    elements.pageSize.value = String(state.pageSize);

    function writePageUrl() {
      const url = new URL(global.location.href);
      const apiParams = new URLSearchParams(buildApiUrl(state).split("?")[1] || "");
      url.search = apiParams.toString();
      global.history.replaceState({}, "", url);
    }

    function returnToCreator(target) {
      try {
        global.sessionStorage.setItem(RESUME_STORAGE_KEY, JSON.stringify(target));
      } catch (_error) {
        return;
      }
      global.location.assign("/#profile");
    }

    function renderWarning(payload) {
      const messages = partialMessages(payload);
      elements.warning.replaceChildren();
      elements.warning.classList.toggle("hidden", !messages.length);
      messages.forEach((message) => appendText(elements.warning, "p", message));
    }

    function renderSummary(payload) {
      const types = payload?.facets?.types || {};
      elements.total.textContent = String(Object.values(types).reduce((sum, value) => sum + (Number(value) || 0), 0));
      elements.caseCount.textContent = String(Number(types.case) || 0);
      elements.reportCount.textContent = String(Number(types.creator_report) || 0);
      elements.strategyCount.textContent = String(Number(types.strategy_plan) || 0);
    }

    function renderPayload(payload) {
      const items = Array.isArray(payload.items) ? payload.items : [];
      const pagination = payload.pagination || {};
      elements.items.replaceChildren(...items.map((asset) => renderAssetRow(documentRef, asset, returnToCreator)));
      elements.empty.querySelector("strong").textContent = "没有匹配的资产";
      elements.empty.querySelector("p").textContent = "调整关键词、类型、状态或日期范围后再试。";
      elements.empty.classList.toggle("hidden", items.length > 0);
      elements.resultCount.textContent = `显示 ${items.length} / 共 ${Number(pagination.total) || 0} 项`;
      elements.pageLabel.textContent = `第 ${Number(pagination.page) || 1} 页`;
      elements.previous.disabled = (Number(pagination.page) || 1) <= 1;
      elements.next.disabled = !pagination.has_next;
      elements.announcement.textContent = items.length ? "资产索引已更新。" : "当前筛选条件下没有资产。";
      renderSummary(payload);
      renderWarning(payload);
      root.setAttribute("aria-busy", "false");
    }

    async function loadAssets(forceRefresh = false) {
      const requestId = ++state.requestId;
      root.setAttribute("aria-busy", "true");
      elements.announcement.textContent = "正在读取本地资产索引...";
      elements.refresh.disabled = true;
      try {
        const requestUrl = `${buildApiUrl(state)}${forceRefresh ? "&refresh=true" : ""}`;
        const response = await global.fetch(requestUrl, {cache: "no-store"});
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          throw new Error(payload.message || "资产索引读取失败");
        }
        if (requestId !== state.requestId) return;
        renderPayload(payload);
        writePageUrl();
      } catch (error) {
        if (requestId !== state.requestId) return;
        elements.announcement.textContent = safeText(error?.message, "资产索引读取失败，请稍后重试。");
        elements.items.replaceChildren();
        elements.empty.classList.remove("hidden");
        elements.empty.querySelector("strong").textContent = "资产索引暂时不可用";
        elements.empty.querySelector("p").textContent = "现有资产没有被修改，请稍后重试。";
        root.setAttribute("aria-busy", "false");
      } finally {
        if (requestId === state.requestId) elements.refresh.disabled = false;
      }
    }

    elements.form.addEventListener("submit", (event) => {
      event.preventDefault();
      state.query = elements.query.value.trim();
      state.type = elements.type.value;
      state.status = elements.status.value;
      state.dateFrom = elements.dateFrom.value;
      state.dateTo = elements.dateTo.value;
      state.page = 1;
      loadAssets();
    });
    [elements.type, elements.status, elements.dateFrom, elements.dateTo].forEach((element) => {
      element.addEventListener("change", () => elements.form.requestSubmit());
    });
    elements.pageSize.addEventListener("change", () => {
      state.pageSize = Number(elements.pageSize.value) || 20;
      state.page = 1;
      loadAssets();
    });
    elements.previous.addEventListener("click", () => {
      state.page = Math.max(1, state.page - 1);
      loadAssets();
    });
    elements.next.addEventListener("click", () => {
      state.page += 1;
      loadAssets();
    });
    elements.refresh.addEventListener("click", () => loadAssets(true));
    elements.reset.addEventListener("click", () => {
      elements.form.reset();
      elements.pageSize.value = "20";
      Object.assign(state, {type: "", status: "", query: "", dateFrom: "", dateTo: "", page: 1, pageSize: 20});
      loadAssets();
    });
    loadAssets();
    return {state, loadAssets, renderPayload};
  }

  global.LibraryPage = Object.freeze({
    buildApiUrl,
    normalizeResumeTarget,
    partialMessages,
    renderAssetRow,
    safeOpenUrl,
    initLibraryPage,
  });

  if (global.document?.readyState === "loading") {
    global.document.addEventListener("DOMContentLoaded", () => initLibraryPage(global.document), {once: true});
  } else {
    initLibraryPage(global.document);
  }
})(window);
