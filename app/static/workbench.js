(function initializeWorkbenchShell(global) {
  "use strict";

  const ROUTES = new Set(["workbench", "single", "profile"]);
  const BADGE_STATES = new Set(["ready", "partial", "missing", "disabled"]);

  function normalizeRoute(value) {
    const route = String(value || "")
      .trim()
      .replace(/^#/, "")
      .toLowerCase();
    return ROUTES.has(route) ? route : "workbench";
  }

  function routeFromHash(hash) {
    return normalizeRoute(hash);
  }

  function normalizeBadgeState(value) {
    const state = String(value || "").trim().toLowerCase();
    return BADGE_STATES.has(state) ? state : "partial";
  }

  function preflightBadge(item, fallbackLabel = "检查项") {
    if (!item || typeof item !== "object") {
      return {
        status: "partial",
        label: `${fallbackLabel} 状态未知`,
      };
    }
    const status = normalizeBadgeState(item.status);
    const label = String(item.label || fallbackLabel || item.id || "检查项");
    const suffix = {
      ready: "可用",
      partial: "待确认",
      missing: "缺失",
      disabled: "关闭",
    }[status];
    return {status, label: `${label} ${suffix}`};
  }

  function apiFailureBadge(label = "状态") {
    return {
      status: "partial",
      label: `${label} 读取失败`,
    };
  }

  function comingSoonBehavior(label = "该模块") {
    return {
      disabled: true,
      shouldFetch: false,
      message: `${label}尚未接入，本轮只保留工作台信息架构位置。`,
    };
  }

  function settingsTarget(section) {
    return {
      "data-source": "douyin-data-source-settings",
      ai: "llm-capability-settings",
      diagnostics: "system-diagnostics-settings",
    }[String(section || "").trim()] || "";
  }

  function formatRefreshTime(value = Date.now()) {
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) {
      return "未知时间";
    }
    return date.toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  }

  function initNavigation(documentRef) {
    if (!documentRef?.querySelectorAll) {
      return;
    }
    documentRef.querySelectorAll("[data-workbench-nav-toggle]").forEach((button) => {
      button.addEventListener("click", () => {
        const group = button.closest("[data-workbench-nav-group]");
        if (!group) {
          return;
        }
        const collapsed = group.dataset.itemsCollapsed !== "false";
        group.dataset.itemsCollapsed = collapsed ? "false" : "true";
        button.setAttribute("aria-expanded", collapsed ? "true" : "false");
      });
    });
    documentRef.querySelectorAll("[data-workbench-open-settings]").forEach((item) => {
      item.addEventListener("click", () => {
        const section = item.dataset.workbenchOpenSettings || "";
        documentRef.dispatchEvent(new CustomEvent("workbench:open-settings", {
          detail: {section, targetId: settingsTarget(section)},
        }));
      });
    });
    documentRef.querySelectorAll("[data-workbench-coming-soon]").forEach((item) => {
      item.addEventListener("click", (event) => {
        event.preventDefault();
        const behavior = comingSoonBehavior(item.dataset.workbenchComingSoon || "该模块");
        documentRef.dispatchEvent(new CustomEvent("workbench:coming-soon", {detail: behavior}));
      });
    });
  }

  global.WorkbenchShell = Object.freeze({
    normalizeRoute,
    routeFromHash,
    normalizeBadgeState,
    preflightBadge,
    apiFailureBadge,
    comingSoonBehavior,
    settingsTarget,
    formatRefreshTime,
    initNavigation,
  });

  if (global.document?.readyState === "loading") {
    global.document.addEventListener("DOMContentLoaded", () => initNavigation(global.document), {once: true});
  } else {
    initNavigation(global.document);
  }
})(window);
