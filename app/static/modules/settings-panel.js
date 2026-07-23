(function initializeSettingsPanel(global) {
  "use strict";

  const instances = new WeakMap();

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function items(value) {
    if (Array.isArray(value)) {
      return value;
    }
    return value === undefined || value === null || value === "" ? [] : [value];
  }

  function numberText(value) {
    const number = Number(value || 0);
    return Number.isFinite(number) ? number.toLocaleString("zh-CN") : "0";
  }

  function errorText(error, fallback) {
    return `${error?.error_code || "ERROR"}：${error?.message || fallback}`;
  }

  function noOpController() {
    const returnsFalse = () => false;
    const resolvesFalse = async () => false;
    return Object.freeze({
      open: returnsFalse,
      close: returnsFalse,
      renderLlmStatus: returnsFalse,
      renderDataSourceStatus: returnsFalse,
      renderLoginStateStatus: returnsFalse,
      renderCookieTestResult: returnsFalse,
      loadLlmStatus: resolvesFalse,
      loadDataSourceStatus: resolvesFalse,
      loadLoginStateStatus: resolvesFalse,
    });
  }

  function init({elements = {}, requestJson, callbacks = {}} = {}) {
    const root = elements.modal || elements.toggle || elements.llmForm || elements.douyinForm;
    if (!root || typeof requestJson !== "function") {
      return noOpController();
    }
    if (instances.has(root)) {
      return instances.get(root);
    }

    function close() {
      if (!elements.modal) {
        return false;
      }
      elements.modal.classList.add("hidden");
      return true;
    }

    function open() {
      if (!elements.modal) {
        return false;
      }
      elements.modal.classList.remove("hidden");
      Promise.resolve(callbacks.refreshPreflight?.()).catch(() => {
        if (elements.preflightSummary) {
          elements.preflightSummary.textContent = "本地工具预检失败，请查看后端日志。";
        }
        callbacks.onPreflightFailure?.();
      });
      Promise.resolve(loadLoginStateStatus()).catch(() => {});
      Promise.resolve(loadDataSourceStatus()).catch(() => {});
      return true;
    }

    function renderLlmStatus(rawLlm = {}) {
      const llm = rawLlm && typeof rawLlm === "object" ? rawLlm : {};
      const configured = Boolean(llm.configured);
      if (elements.llmStatusBadge) {
        elements.llmStatusBadge.textContent = configured ? "已启用" : "未配置";
        elements.llmStatusBadge.classList.toggle("success", configured);
        elements.llmStatusBadge.classList.toggle("muted-badge", !configured);
      }
      if (elements.testLlmButton) {
        elements.testLlmButton.disabled = !configured;
      }
      elements.llmConfigHint?.classList.toggle("hidden", configured);
      if (elements.llmStatusList) {
        elements.llmStatusList.innerHTML = `
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
      if (elements.llmProviderInput) elements.llmProviderInput.value = llm.provider || "disabled";
      if (elements.llmApiBaseInput) elements.llmApiBaseInput.value = llm.api_base || "";
      if (elements.llmModelInput) elements.llmModelInput.value = llm.model || "";
      if (elements.llmTimeoutInput) elements.llmTimeoutInput.value = llm.timeout_seconds || 90;
      if (elements.llmTemperatureInput) elements.llmTemperatureInput.value = llm.temperature ?? 0.2;
      if (elements.llmApiKeyInput) {
        elements.llmApiKeyInput.value = "";
        elements.llmApiKeyInput.placeholder = llm.has_api_key
          ? `留空保留当前 Key（${llm.masked_api_key || "已配置"}）`
          : "粘贴 API Key";
      }
      if (elements.llmClearKeyInput) elements.llmClearKeyInput.checked = false;
      callbacks.onLlmStatus?.(llm);
      return true;
    }

    function cookieDiagnosticsRows(diagnostics = {}) {
      if (!diagnostics.has_cookie) {
        return "";
      }
      const important = items(diagnostics.present_important_keys).join(" / ") || "未检测到";
      const missing = items(diagnostics.missing_login_keys).join(" / ") || "无";
      return `
        <dt>Cookie 字段</dt><dd>${numberText(diagnostics.pair_count)} 个；登录态字段 ${numberText(diagnostics.login_key_count)} 个</dd>
        <dt>关键字段</dt><dd>${escapeHtml(important)}</dd>
        <dt>缺失登录字段</dt><dd>${escapeHtml(missing)}</dd>
      `;
    }

    function renderDataSourceStatus(rawStatus = {}) {
      const status = rawStatus && typeof rawStatus === "object" ? rawStatus : {};
      const configured = Boolean(status.configured);
      const hasCookie = Boolean(status.has_cookie);
      if (elements.dataSourceStatusBadge) {
        elements.dataSourceStatusBadge.textContent = configured
          ? "主力数据源已配置"
          : hasCookie ? "配置需修正" : "待配置";
        elements.dataSourceStatusBadge.className = `status-badge ${configured ? "success" : hasCookie ? "warning" : "muted-badge"}`;
      }
      if (elements.dataSourceStatusList) {
        elements.dataSourceStatusList.innerHTML = `
          <dl>
            <dt>Cookie API</dt><dd>${configured ? "已配置可用" : hasCookie ? "已保存但不可用" : "未配置"}</dd>
            <dt>凭据来源</dt><dd>${status.source === "chrome_extension" ? "Chrome 扩展同步" : status.source === "manual_local" ? "本机手工配置" : status.source === "environment" ? "环境变量" : "未配置"}</dd>
            <dt>User-Agent</dt><dd>${status.user_agent_configured ? "已配置" : "未配置"}</dd>
            <dt>Referer</dt><dd>${escapeHtml(status.referer || "https://www.douyin.com/")}</dd>
            ${cookieDiagnosticsRows(status.cookie_diagnostics || {})}
            <dt>当前策略</dt><dd>个人账号 Cookie / Web API 是主页扫描主路径；失败时明确提示人工更新，并保留作品链接、JSON/CSV、已有 Case 等安全兜底。</dd>
          </dl>
        `;
      }
      if (elements.douyinCookieInput) {
        elements.douyinCookieInput.value = "";
        elements.douyinCookieInput.placeholder = hasCookie
          ? `留空保留当前 Cookie（${status.masked_cookie || "已配置"}）`
          : "粘贴 Douyin Cookie";
      }
      if (elements.douyinUserAgentInput) elements.douyinUserAgentInput.value = status.user_agent || "";
      if (elements.douyinRefererInput) elements.douyinRefererInput.value = status.referer || "https://www.douyin.com/";
      if (elements.douyinClearCookieInput) elements.douyinClearCookieInput.checked = false;
      return true;
    }

    function renderLoginStateStatus(rawState = {}) {
      const state = rawState && typeof rawState === "object" ? rawState : {};
      const configured = Boolean(state.configured);
      const paired = Boolean(state.paired);
      if (elements.loginStateStatusBadge) {
        elements.loginStateStatusBadge.textContent = configured ? "已同步" : paired ? "已配对" : "未配对";
        elements.loginStateStatusBadge.className = `status-badge ${configured ? "success" : paired ? "warning" : "muted-badge"}`;
      }
      if (elements.loginStateStatusList) {
        elements.loginStateStatusList.innerHTML = `
          <dl>
            <dt>连接状态</dt><dd>${paired ? "已完成一次配对" : "等待配对"}</dd>
            <dt>抖音登录状态</dt><dd>${configured ? "已安全同步" : "尚未同步"}</dd>
            <dt>最近同步</dt><dd>${escapeHtml(state.last_synced_at || "暂无")}</dd>
            <dt>Cookie 安全预览</dt><dd>${configured ? "********" : "未保存"}</dd>
            <dt>字段数量</dt><dd>${numberText(state.pair_count)} 个；登录态字段 ${numberText(state.login_key_count)} 个</dd>
          </dl>
        `;
      }
      return true;
    }

    function renderCookieTestResult(rawTest = {}) {
      if (!elements.douyinCookieTestResult) {
        return false;
      }
      const test = rawTest && typeof rawTest === "object" ? rawTest : {};
      const diagnostics = test.cookie_diagnostics || {};
      const statusClass = test.status === "ok"
        ? "success"
        : ["config_only", "not_configured"].includes(test.status) ? "muted-badge" : "warning";
      const rows = [
        ["自检状态", test.status || ""],
        ["错误码", test.error_code || ""],
        ["Cookie 结构", diagnostics.has_cookie ? `${numberText(diagnostics.pair_count)} 个字段，${numberText(diagnostics.login_key_count)} 个登录态字段` : "未配置"],
        ["关键字段", items(diagnostics.present_important_keys).join(" / ") || "未检测到"],
        ["API 请求", test.api_checked ? `已请求，HTTP ${test.status_code || "未知"}` : "未请求"],
        ["返回类型", test.api_checked ? `${test.is_json ? "JSON" : "非 JSON"}${test.content_type ? ` · ${test.content_type}` : ""}` : "未检测"],
        ["发生跳转", test.api_checked ? (test.redirected ? "是，已停止" : "否") : ""],
        ["重试次数", test.api_checked ? numberText(test.retry_count) : ""],
        ["返回作品", test.api_checked ? `${numberText(test.aweme_count)} 条` : "未检测"],
      ].filter(([, value]) => value !== "");
      const nextSteps = items(test.safe_next_steps);
      const endpointResults = items(test.endpoint_results);
      elements.douyinCookieTestResult.className = `settings-test-result ${statusClass}`;
      elements.douyinCookieTestResult.innerHTML = `
        <strong>${escapeHtml(test.message || "Cookie API 自检完成。")}</strong>
        <dl>${rows.map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd>`).join("")}</dl>
        ${endpointResults.length ? `
          <div class="endpoint-test-list">
            <strong>候选接口</strong>
            ${endpointResults.map((item) => `<span>${escapeHtml(item.endpoint || "")} · ${escapeHtml(item.status || "")}${item.status_code ? ` · HTTP ${escapeHtml(String(item.status_code))}` : ""}${item.aweme_count ? ` · ${numberText(item.aweme_count)} 条` : ""}</span>`).join("")}
          </div>
        ` : ""}
        ${nextSteps.length ? `<ul>${nextSteps.map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ul>` : ""}
      `;
      return true;
    }

    async function loadLlmStatus() {
      try {
        const payload = await requestJson("/api/settings/llm", {cache: "no-store"});
        renderLlmStatus(payload.llm || {});
        return true;
      } catch (error) {
        if (elements.llmStatusBadge) elements.llmStatusBadge.textContent = "读取失败";
        if (elements.llmStatusList) elements.llmStatusList.textContent = errorText(error, "无法读取 AI 配置");
        if (elements.testLlmButton) elements.testLlmButton.disabled = true;
        callbacks.onLlmLoadFailure?.();
        return false;
      }
    }

    async function loadDataSourceStatus() {
      if (elements.dataSourceStatusList) {
        elements.dataSourceStatusList.textContent = "正在读取数据源设置...";
      }
      try {
        const payload = await requestJson("/api/settings/data-sources", {cache: "no-store"});
        renderDataSourceStatus(payload.data_sources || {});
        return true;
      } catch (error) {
        if (elements.dataSourceStatusBadge) elements.dataSourceStatusBadge.textContent = "读取失败";
        if (elements.dataSourceStatusList) elements.dataSourceStatusList.textContent = errorText(error, "无法读取数据源设置");
        return false;
      }
    }

    async function loadLoginStateStatus() {
      if (elements.loginStateStatusList) {
        elements.loginStateStatusList.textContent = "正在读取扩展同步状态...";
      }
      try {
        const payload = await requestJson("/api/local-login-state/status", {cache: "no-store"});
        renderLoginStateStatus(payload.login_state || {});
        return true;
      } catch (error) {
        if (elements.loginStateStatusBadge) elements.loginStateStatusBadge.textContent = "读取失败";
        if (elements.loginStateStatusList) {
          elements.loginStateStatusList.textContent = errorText(error, "无法读取扩展同步状态");
        }
        return false;
      }
    }

    elements.toggle?.addEventListener("click", open);
    elements.close?.addEventListener("click", close);
    elements.modal?.addEventListener("click", (event) => {
      if (event.target === elements.modal) close();
    });

    elements.llmForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (elements.saveLlmButton) elements.saveLlmButton.disabled = true;
      if (elements.llmSaveResult) elements.llmSaveResult.textContent = "正在保存...";
      try {
        const payload = {
          provider: elements.llmProviderInput?.value || "disabled",
          api_base: elements.llmApiBaseInput?.value || "",
          model: elements.llmModelInput?.value || "",
          timeout_seconds: Number(elements.llmTimeoutInput?.value || 90),
          temperature: Number(elements.llmTemperatureInput?.value || 0.2),
          clear_api_key: Boolean(elements.llmClearKeyInput?.checked),
        };
        const apiKey = String(elements.llmApiKeyInput?.value || "").trim();
        if (apiKey) payload.api_key = apiKey;
        const result = await requestJson("/api/settings/llm", {
          method: "PUT",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload),
        });
        renderLlmStatus(result.llm || {});
        if (elements.llmSaveResult) elements.llmSaveResult.textContent = "已保存到本机运行时配置。";
        await Promise.resolve(callbacks.refreshPreflight?.()).catch(() => {});
      } catch (error) {
        if (elements.llmSaveResult) elements.llmSaveResult.textContent = errorText(error, "保存失败");
      } finally {
        if (elements.saveLlmButton) elements.saveLlmButton.disabled = false;
      }
    });

    elements.douyinForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (elements.saveDouyinButton) elements.saveDouyinButton.disabled = true;
      if (elements.douyinSaveResult) elements.douyinSaveResult.textContent = "正在保存...";
      try {
        const payload = {
          user_agent: elements.douyinUserAgentInput?.value || "",
          referer: elements.douyinRefererInput?.value || "https://www.douyin.com/",
          clear_cookie: Boolean(elements.douyinClearCookieInput?.checked),
        };
        const cookie = String(elements.douyinCookieInput?.value || "").trim();
        if (cookie) payload.douyin_cookie = cookie;
        const result = await requestJson("/api/settings/data-sources/douyin", {
          method: "PUT",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload),
        });
        renderDataSourceStatus(result.data_sources || {});
        if (elements.douyinSaveResult) elements.douyinSaveResult.textContent = "已保存到本机运行时配置。";
      } catch (error) {
        if (elements.douyinSaveResult) elements.douyinSaveResult.textContent = errorText(error, "保存失败");
      } finally {
        if (elements.saveDouyinButton) elements.saveDouyinButton.disabled = false;
      }
    });

    elements.startLoginStatePairingButton?.addEventListener("click", async () => {
      elements.startLoginStatePairingButton.disabled = true;
      if (elements.loginStatePairingResult) {
        elements.loginStatePairingResult.classList.remove("hidden");
        elements.loginStatePairingResult.textContent = "正在生成一次性配对码...";
      }
      try {
        const result = await requestJson("/api/local-login-state/pair/start", {method: "POST"});
        const pairing = result.pairing || {};
        if (elements.loginStatePairingResult) {
          elements.loginStatePairingResult.innerHTML = `
            <span class="muted">在 Douyin Login State Extractor 扩展中输入：</span>
            <code>${escapeHtml(pairing.pairing_code || "")}</code>
            <span class="muted">配对码将在 ${numberText(pairing.expires_in_seconds || 600)} 秒内失效。</span>
          `;
        }
      } catch (error) {
        if (elements.loginStatePairingResult) {
          elements.loginStatePairingResult.textContent = errorText(error, "配对码生成失败");
        }
      } finally {
        elements.startLoginStatePairingButton.disabled = false;
      }
    });

    elements.refreshLoginStateButton?.addEventListener("click", async () => {
      elements.refreshLoginStateButton.disabled = true;
      try {
        await loadLoginStateStatus();
        await loadDataSourceStatus();
      } finally {
        elements.refreshLoginStateButton.disabled = false;
      }
    });

    elements.testDouyinButton?.addEventListener("click", async () => {
      elements.testDouyinButton.disabled = true;
      if (elements.douyinCookieTestResult) elements.douyinCookieTestResult.textContent = "正在自检 Cookie 结构和 Cookie API...";
      try {
        const payload = callbacks.getDouyinTestPayload?.() || {count: 5};
        const result = await requestJson("/api/settings/data-sources/douyin/test", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload),
        });
        renderCookieTestResult(result.test || {});
        await loadLoginStateStatus();
        await loadDataSourceStatus();
      } catch (error) {
        if (elements.douyinCookieTestResult) elements.douyinCookieTestResult.textContent = errorText(error, "Cookie API 自检失败");
      } finally {
        elements.testDouyinButton.disabled = false;
      }
    });

    elements.testLlmButton?.addEventListener("click", async () => {
      elements.testLlmButton.disabled = true;
      if (elements.llmTestResult) elements.llmTestResult.textContent = "正在测试...";
      try {
        const payload = await requestJson("/api/settings/llm/test", {method: "POST"});
        if (elements.llmTestResult) elements.llmTestResult.textContent = `测试通过：${payload.test?.message || "pong"}`;
      } catch (error) {
        if (elements.llmTestResult) elements.llmTestResult.textContent = errorText(error, "测试失败");
      } finally {
        await loadLlmStatus();
      }
    });

    elements.refreshPreflightButton?.addEventListener("click", async () => {
      elements.refreshPreflightButton.disabled = true;
      try {
        await callbacks.refreshPreflight?.();
      } catch (error) {
        if (elements.preflightSummary) elements.preflightSummary.textContent = errorText(error, "本地工具预检失败");
      } finally {
        elements.refreshPreflightButton.disabled = false;
      }
    });

    elements.preflightList?.addEventListener("click", async (event) => {
      const button = event.target.closest?.("[data-preflight-copy-index]");
      if (!button) return;
      const index = Number(button.dataset.preflightCopyIndex);
      const originalText = button.textContent;
      try {
        const copied = await callbacks.copyPreflightSnippet?.(index);
        button.textContent = copied ? "已复制" : "复制失败";
      } catch (_error) {
        button.textContent = "复制失败";
      } finally {
        global.setTimeout(() => {
          button.textContent = originalText;
        }, 1600);
      }
    });

    const controller = Object.freeze({
      open,
      close,
      renderLlmStatus,
      renderDataSourceStatus,
      renderLoginStateStatus,
      renderCookieTestResult,
      loadLlmStatus,
      loadDataSourceStatus,
      loadLoginStateStatus,
    });
    instances.set(root, controller);
    return controller;
  }

  global.SettingsPanel = Object.freeze({init});
})(window);
