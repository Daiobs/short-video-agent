from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


NODE_CANDIDATES = [
    shutil.which("node"),
    Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node",
]
NODE_BINARY = next(
    (
        Path(value)
        for value in NODE_CANDIDATES
        if value and Path(value).is_file()
    ),
    None,
)


def run_node(script: str) -> dict:
    assert NODE_BINARY is not None
    completed = subprocess.run(
        [str(NODE_BINARY), "-e", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return json.loads(completed.stdout)


@pytest.mark.skipif(NODE_BINARY is None, reason="Node.js is unavailable")
def test_representative_sample_selector_ui_preserves_explicit_manual_selection() -> None:
    source = Path("app/static/modules/representative-sample-selector.js").read_text(encoding="utf-8")
    assert "fetch(" not in source
    assert "dispatchEvent" not in source
    assert "selected_sample_ids" not in source

    script = f"""
const vm = require("vm");
const source = {json.dumps(source)};
const context = {{console}};
context.window = context;
const before = Object.keys(context);
vm.runInNewContext(source, context, {{filename: "representative-sample-selector.js"}});
const added = Object.keys(context).filter((key) => !before.includes(key));
const api = context.RepresentativeSampleSelectorUI;
const raw = {{
  algorithm_version: "representative-v1",
  target_count: 6,
  available_count: 9,
  coverage: {{BREAKOUT_HIT: true, COMMENT_MAGNET: true}},
  recommendations: [
    {{sample_id: "sample_a", rank: 1, score: 92, primary_role: "BREAKOUT_HIT", roles: ["BREAKOUT_HIT"], reasons: ["点赞位于账号 P97"]}},
    {{sample_id: "sample_b", rank: 2, score: 81, primary_role: "COMMENT_MAGNET", roles: ["COMMENT_MAGNET"], reasons: ["评论位于账号 P95"]}},
    {{sample_id: "../unsafe", rank: 3, score: 99, primary_role: "BREAKOUT_HIT"}},
    {{sample_id: "sample_a", rank: 4, score: 75, primary_role: "RECENT_WINNER"}},
  ],
}};
const normalized = api.normalizeSelection(raw);
const items = [{{sample_id: "sample_a"}}, {{sample_id: "sample_b"}}, {{sample_id: "sample_c"}}];
const selectedBeforeRecommendation = Object.freeze(["sample_c"]);
const generatedOnly = api.normalizeSelection({{...raw, recommendations: [...raw.recommendations].reverse()}});
const selectedAfterGeneration = [...selectedBeforeRecommendation];
const applied = api.matchingItems(normalized, items, (item) => item.sample_id).map((item) => item.sample_id);
const afterManualRemove = api.nextManualSelection(applied, "sample_a", false);
const regeneratedAgain = api.normalizeSelection(raw);
process.stdout.write(JSON.stringify({{
  added,
  namespaceFrozen: Object.isFrozen(api),
  selectionFrozen: Object.isFrozen(normalized),
  recommendationFrozen: Object.isFrozen(normalized.recommendations[0]),
  ids: api.recommendedIds(normalized),
  applied,
  selectedBeforeRecommendation,
  selectedAfterGeneration,
  generatedIds: api.recommendedIds(generatedOnly),
  afterManualRemove,
  regeneratedIds: api.recommendedIds(regeneratedAgain),
  lookupScore: api.recommendationById(normalized, "sample_a").score,
}}));
"""
    result = run_node(script)

    assert result["added"] == ["RepresentativeSampleSelectorUI"]
    assert result["namespaceFrozen"] is True
    assert result["selectionFrozen"] is True
    assert result["recommendationFrozen"] is True
    assert result["ids"] == ["sample_a", "sample_b"]
    assert result["applied"] == ["sample_a", "sample_b"]
    assert result["selectedBeforeRecommendation"] == ["sample_c"]
    assert result["selectedAfterGeneration"] == ["sample_c"]
    assert result["afterManualRemove"] == ["sample_b"]
    assert result["regeneratedIds"] == ["sample_a", "sample_b"]
    assert result["lookupScore"] == 92


@pytest.mark.skipif(NODE_BINARY is None, reason="Node.js is unavailable")
def test_creator_report_view_module_is_safe_bounded_and_frozen() -> None:
    source = Path("app/static/modules/creator-report-view.js").read_text(encoding="utf-8")
    assert "fetch(" not in source
    assert "currentCloneSetId" not in source
    assert "dispatchEvent" not in source

    script = f"""
const vm = require("vm");
const source = {json.dumps(source)};
const context = {{console: {{error() {{}}}}}};
context.window = context;
const before = Object.keys(context);
vm.runInNewContext(source, context, {{filename: "creator-report-view.js"}});
const added = Object.keys(context).filter((key) => !before.includes(key));
function esc(value) {{
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}}
function list(value) {{ return Array.isArray(value) ? value : value ? [value] : []; }}
const helpers = {{
  compactReportList(...values) {{ return values.flatMap(list).map(String).filter(Boolean); }},
  creatorStrategyFromResult(result) {{ return result.creator_strategy || {{}}; }},
  formatNumber(value) {{ return String(Number(value || 0)); }},
  normalizeItems: list,
  publicValueHasContent(value) {{ return list(value).length > 0 || Boolean(value && typeof value === "object"); }},
  qualityLabelFromScore(value) {{ return Number(value || 0) >= 60 ? "可用" : "待补证据"; }},
  renderCompactPerformanceSegments() {{ return '<div class="segments"></div>'; }},
  renderCreatorCloneEvidenceOverview() {{ return '<div class="evidence"></div>'; }},
  renderFormulaCards(value) {{ return `<div>${{list(value).map(esc).join("|")}}</div>`; }},
  renderPublicCard(title, body, tone = "") {{ return `<article class=\"${{esc(tone)}}\"><h4>${{esc(title)}}</h4>${{body}}</article>`; }},
  renderPublicFields(rows) {{ return `<dl>${{list(rows).map((row) => `<dt>${{esc(row[0])}}</dt><dd>${{esc(row[1] || "")}}</dd>`).join("")}}</dl>`; }},
  renderPublicList(value, empty = "empty") {{ const rows = list(value); return rows.length ? `<ul>${{rows.map((item) => `<li>${{esc(item)}}</li>`).join("")}}</ul>` : `<p>${{esc(empty)}}</p>`; }},
  renderTopicBuckets(value) {{ return `<div>${{list(value).map(esc).join("|")}}</div>`; }},
  cleanPublicReportText(value) {{ return String(value || "").trim(); }},
}};
const renderer = context.CreatorReportView.createRenderer(helpers);
function container() {{
  return {{
    innerHTML: "",
    querySelector(selector) {{ return selector === ".creator-distillation-report" && this.innerHTML.includes("creator-distillation-report") ? {{}} : null; }},
  }};
}}
const target = container();
const result = {{
  summary: "稳定总结。<script>unsafe()</script>",
  creator_positioning: {{what_the_creator_sells: "清晰定位"}},
  creator_strategy: {{positioning: "清晰定位", templates: ["模板 A"]}},
}};
const viewModel = {{
  headline: "<img src=x onerror=unsafe()>",
  summary: "安全摘要",
  sections: {{core_judgment: {{bullets: ["动作"]}}, formulas: ["公式"], next_actions: ["执行"], next_ideas: ["选题"]}},
  value_upgrade: {{observation: {{bullets: ["观察"]}}, explanation: {{bullets: ["解释"]}}, execution: {{bullets: ["执行"]}}}},
}};
const normal = renderer.render({{container: target, result, overview: {{selected_count: 1, sample_count: 2}}, templateLabel: "自动", viewModel}});
const normalHtml = target.innerHTML;
const missingDom = renderer.render({{container: null, result, overview: {{}}, viewModel}});
const emptyTarget = container();
const empty = renderer.render({{container: emptyTarget, result: {{}}, overview: {{}}, viewModel: {{}}}});
const malformedTarget = container();
const malformed = renderer.render({{container: malformedTarget, result: "bad", overview: null, viewModel: []}});
const failureTarget = container();
renderer.showFailure(failureTarget, "<script>failure()</script>");
const cleared = renderer.clear(failureTarget);
process.stdout.write(JSON.stringify({{
  added,
  namespaceFrozen: Object.isFrozen(context.CreatorReportView),
  rendererFrozen: Object.isFrozen(renderer),
  api: Object.keys(renderer).sort(),
  normal,
  hasReport: renderer.hasReport(target),
  escaped: normalHtml.includes("&lt;script&gt;") && normalHtml.includes("&lt;img"),
  rawUnsafe: normalHtml.includes("<script>") || normalHtml.includes("<img src=x"),
  missingDom,
  empty,
  malformed,
  failureEscaped: !failureTarget.innerHTML.includes("<script>"),
  cleared,
  clearValue: failureTarget.innerHTML,
}}));
"""
    result = run_node(script)

    assert result["added"] == ["CreatorReportView"]
    assert result["namespaceFrozen"] is True
    assert result["rendererFrozen"] is True
    assert result["api"] == [
        "clear",
        "hasReport",
        "render",
        "renderReportMarkup",
        "renderSummary",
        "showFailure",
    ]
    assert result["normal"] is True
    assert result["hasReport"] is True
    assert result["escaped"] is True
    assert result["rawUnsafe"] is False
    assert result["missingDom"] is False
    assert result["empty"] is True
    assert result["malformed"] is True
    assert result["failureEscaped"] is True
    assert result["cleared"] is True
    assert result["clearValue"] == ""


@pytest.mark.skipif(NODE_BINARY is None, reason="Node.js is unavailable")
def test_settings_panel_module_coordinates_existing_safe_settings_flow_once() -> None:
    source = Path("app/static/modules/settings-panel.js").read_text(encoding="utf-8")
    assert "currentCloneSetId" not in source

    script = f"""
const vm = require("vm");
const source = {json.dumps(source)};
const context = {{console, setTimeout(callback) {{ callback(); }}}};
context.window = context;
const before = Object.keys(context);
vm.runInNewContext(source, context, {{filename: "settings-panel.js"}});
const added = Object.keys(context).filter((key) => !before.includes(key));
function element(initialClasses = []) {{
  const classes = new Set(initialClasses);
  return {{
    textContent: "", innerHTML: "", value: "", placeholder: "", className: "", disabled: false, checked: false,
    dataset: {{}}, listeners: {{}},
    classList: {{
      add(...values) {{ values.forEach((value) => classes.add(value)); }},
      remove(...values) {{ values.forEach((value) => classes.delete(value)); }},
      toggle(value, force) {{ if (force === undefined ? !classes.has(value) : force) classes.add(value); else classes.delete(value); }},
      contains(value) {{ return classes.has(value); }},
    }},
    addEventListener(type, listener) {{ (this.listeners[type] ||= []).push(listener); }},
  }};
}}
async function emit(target, type, event = {{}}) {{
  const payload = {{preventDefault() {{}}, target, ...event}};
  for (const listener of target.listeners[type] || []) await listener(payload);
}}
  const e = {{
  toggle: element(), modal: element(["hidden"]), close: element(),
  llmStatusBadge: element(), llmStatusList: element(), llmConfigHint: element(), llmForm: element(),
  llmProviderInput: element(), llmApiBaseInput: element(), llmModelInput: element(), llmApiKeyInput: element(),
  llmTimeoutInput: element(), llmCreatorDistillTimeoutInput: element(), llmFinalReduceTimeoutInput: element(),
  llmQuickDistillBudgetInput: element(), llmDeepDistillBudgetInput: element(), llmBatchJobBudgetInput: element(),
  llmFinalReduceReserveInput: element(), llmCompactRetryMinInput: element(),
  llmTemperatureInput: element(), llmClearKeyInput: element(), saveLlmButton: element(),
  llmSaveResult: element(), testLlmButton: element(), llmTestResult: element(), dataSourceStatusBadge: element(),
  dataSourceStatusList: element(), douyinForm: element(), douyinCookieInput: element(), douyinUserAgentInput: element(),
  douyinRefererInput: element(), douyinClearCookieInput: element(), saveDouyinButton: element(), douyinSaveResult: element(),
  testDouyinButton: element(), douyinCookieTestResult: element(), refreshPreflightButton: element(),
    preflightSummary: element(), preflightList: element(),
    loginStateStatusBadge: element(), loginStateStatusList: element(), startLoginStatePairButton: element(),
    refreshLoginStateButton: element(), loginStatePairResult: element(),
  }};
const requests = [];
async function requestJson(url, options = {{}}) {{
  requests.push([url, options.method || "GET", options.body || ""]);
  if (url === "/api/settings/llm/test") return {{test: {{message: "pong"}}}};
  if (url === "/api/settings/llm") return {{llm: {{
    configured: true, provider: "openai_compatible", api_base: "https://api.example.test/v1",
    model: "vision", has_api_key: true, masked_api_key: "sk-****abcd", temperature: 0.2,
    timeout_seconds: 90, creator_distill_request_timeout_seconds: 180,
    final_reduce_timeout_seconds: 600, quick_distill_budget_seconds: 240,
    deep_distill_budget_seconds: 600, batch_job_budget_seconds: 600,
    final_reduce_min_reserve_seconds: 120, compact_retry_min_remaining_seconds: 60,
  }}}};
  if (url === "/api/settings/data-sources/douyin/test") return {{test: {{status: "ok", message: "通过", cookie_diagnostics: {{has_cookie: true, pair_count: 5, login_key_count: 2}}, api_checked: true, status_code: 200, is_json: true, aweme_count: 3}}}};
  if (url === "/api/settings/data-sources/douyin") return {{data_sources: {{has_cookie: true, masked_cookie: "sessionid=****abcd", user_agent_configured: true, user_agent: "UA", referer: "https://www.douyin.com/"}}}};
  if (url === "/api/settings/data-sources") return {{data_sources: {{has_cookie: true, masked_cookie: "sessionid=****abcd", user_agent_configured: true, user_agent: "UA", referer: "https://www.douyin.com/"}}}};
  if (url === "/api/local-login-state/status") return {{login_state: {{paired: true, configured: true, source: "chrome_extension", masked_cookie: "********", pair_count: 5, login_key_count: 2, extension_version: "1.0.0", health: {{status: "success"}}}}}};
  if (url === "/api/local-login-state/pair/start") return {{pairing: {{pairing_code: "ABCD2345", expires_in_seconds: 600}}}};
  throw {{error_code: "UNEXPECTED", message: url}};
}}
let preflightCalls = 0;
let llmStatusCalls = 0;
const options = {{
  elements: e,
  requestJson,
  callbacks: {{
    refreshPreflight() {{ preflightCalls += 1; }},
    onLlmStatus() {{ llmStatusCalls += 1; }},
    getDouyinTestPayload() {{ return {{count: 5, profile_url: "https://www.douyin.com/user/safe"}}; }},
    copyPreflightSnippet() {{ return true; }},
  }},
}};
(async () => {{
const first = context.SettingsPanel.init(options);
const second = context.SettingsPanel.init(options);
await first.loadLlmStatus();
await first.loadDataSourceStatus();
await first.loadLoginStateStatus();
await emit(e.toggle, "click");
const opened = !e.modal.classList.contains("hidden");
await emit(e.close, "click");
const closed = e.modal.classList.contains("hidden");
e.llmApiKeyInput.value = "sk-live-secret-never-render";
await emit(e.llmForm, "submit");
e.douyinCookieInput.value = "sessionid=raw-cookie-never-render";
await emit(e.douyinForm, "submit");
await emit(e.testLlmButton, "click");
await emit(e.testDouyinButton, "click");
await emit(e.startLoginStatePairButton, "click");
await emit(e.refreshLoginStateButton, "click");
first.renderLlmStatus(null);
first.renderDataSourceStatus("bad");
first.renderCookieTestResult([]);
const visible = [e.llmStatusList.innerHTML, e.llmStatusList.textContent, e.llmApiKeyInput.value, e.llmApiKeyInput.placeholder,
  e.dataSourceStatusList.innerHTML, e.douyinCookieInput.value, e.douyinCookieInput.placeholder,
  e.llmSaveResult.textContent, e.douyinSaveResult.textContent, e.llmTestResult.textContent, e.douyinCookieTestResult.innerHTML].join("|");
const noDom = context.SettingsPanel.init({{elements: {{}}, requestJson}});
const llmPutRequest = requests.find((item) => item[0] === "/api/settings/llm" && item[1] === "PUT");
process.stdout.write(JSON.stringify({{
  added,
  namespaceFrozen: Object.isFrozen(context.SettingsPanel),
  controllerFrozen: Object.isFrozen(first),
  sameController: first === second,
  toggleListeners: e.toggle.listeners.click.length,
  llmSubmitListeners: e.llmForm.listeners.submit.length,
  opened, closed, preflightCalls, llmStatusCalls,
  requestPairs: requests.map((item) => item.slice(0, 2)),
  llmPutBody: JSON.parse(llmPutRequest[2]),
  leakedKey: visible.includes("sk-live-secret-never-render"),
      leakedCookie: visible.includes("raw-cookie-never-render"),
      pairingCodeShown: e.loginStatePairResult.innerHTML.includes("ABCD2345"),
  noDomOpen: noDom.open(),
  api: Object.keys(first).sort(),
}}));
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
    result = run_node(script)

    assert result["added"] == ["SettingsPanel"]
    assert result["namespaceFrozen"] is True
    assert result["controllerFrozen"] is True
    assert result["sameController"] is True
    assert result["toggleListeners"] == 1
    assert result["llmSubmitListeners"] == 1
    assert result["opened"] is True
    assert result["closed"] is True
    assert result["preflightCalls"] >= 2
    assert result["llmStatusCalls"] >= 2
    assert ["/api/settings/llm", "PUT"] in result["requestPairs"]
    assert ["/api/settings/llm/test", "POST"] in result["requestPairs"]
    assert ["/api/settings/data-sources/douyin", "PUT"] in result["requestPairs"]
    assert ["/api/settings/data-sources/douyin/test", "POST"] in result["requestPairs"]
    assert ["/api/local-login-state/status", "GET"] in result["requestPairs"]
    assert ["/api/local-login-state/pair/start", "POST"] in result["requestPairs"]
    assert result["llmPutBody"]["timeout_seconds"] == 90
    assert result["llmPutBody"]["creator_distill_request_timeout_seconds"] == 180
    assert result["llmPutBody"]["quick_distill_budget_seconds"] == 240
    assert result["llmPutBody"]["deep_distill_budget_seconds"] == 600
    assert result["llmPutBody"]["batch_job_budget_seconds"] == 600
    assert result["llmPutBody"]["final_reduce_timeout_seconds"] == 600
    assert result["llmPutBody"]["final_reduce_min_reserve_seconds"] == 120
    assert result["llmPutBody"]["compact_retry_min_remaining_seconds"] == 60
    assert result["leakedKey"] is False
    assert result["leakedCookie"] is False
    assert result["pairingCodeShown"] is True
    assert result["noDomOpen"] is False
    assert result["api"] == [
        "close",
        "loadDataSourceStatus",
        "loadLlmStatus",
        "loadLoginStateStatus",
        "open",
        "renderCookieTestResult",
        "renderDataSourceStatus",
        "renderLlmStatus",
        "renderLoginStateStatus",
    ]
