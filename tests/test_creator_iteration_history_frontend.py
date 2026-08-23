from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


NODE_CANDIDATES = [
    shutil.which("node"),
    Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node",
]
NODE_BINARY = next(
    (Path(value) for value in NODE_CANDIDATES if value and Path(value).is_file()),
    None,
)
client = TestClient(app)


def _run_node(script: str) -> dict:
    assert NODE_BINARY is not None
    completed = subprocess.run(
        [str(NODE_BINARY), "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


@pytest.mark.skipif(NODE_BINARY is None, reason="Node.js is unavailable")
def test_iteration_view_renders_empty_current_history_and_policy_states() -> None:
    source = Path("app/static/modules/creator-iteration-history.js").read_text(encoding="utf-8")
    script = f"""
const vm = require("vm");
const context = {{window: {{}}}};
vm.runInNewContext({json.dumps(source)}, context, {{filename: "creator-iteration-history.js"}});
const view = context.window.CreatorIterationHistoryView;
const empty = view.renderOverview({{iterations: [], current_iteration_id: "", current_policy: {{can_start_next: true}}}});
const virtualLegacy = {{
  iteration_id: "iteration_legacy_001", sequence: 1, label: "第 1 轮", storage_mode: "legacy_root",
  state: "active", is_current: true, selected_topic: "旧轮次选题", execution_pack_status: "ready",
  execution_record_status: "completed", production_status: {{publishing: "completed"}}, outcome_status: "ready",
  snapshot_count: 1, latest_metrics: {{views: 0, likes: null, comments: 2}}, created_at: "2026-08-01T00:00:00+00:00", closed_at: ""
}};
const natural = view.renderOverview({{
  iterations: [virtualLegacy], current_iteration_id: virtualLegacy.iteration_id,
  current_policy: {{can_start_next: true, requires_explicit_close: false, natural_close_reason: "execution_completed"}}
}});
const explicit = view.renderOverview({{
  iterations: [{{...virtualLegacy, execution_record_status: "in_progress"}}], current_iteration_id: virtualLegacy.iteration_id,
  current_policy: {{can_start_next: false, requires_explicit_close: true, blocking_reason: "active"}}
}});
console.log(JSON.stringify({{
  empty: empty.includes("尚未开始创作迭代") && !empty.includes('data-iteration-action="start-next"'),
  virtual: natural.includes("兼容旧轮次") && natural.includes("旧轮次选题"),
  natural: natural.includes('data-iteration-action="start-next"') && !natural.includes("请选择原因"),
  explicit: explicit.includes("请选择原因") && explicit.includes("取消本轮"),
  zero: natural.includes(">0<"),
  missing: natural.includes("—"),
}}));
"""

    result = _run_node(script)

    assert result == {
        "empty": True,
        "virtual": True,
        "natural": True,
        "explicit": True,
        "zero": True,
        "missing": True,
    }


@pytest.mark.skipif(NODE_BINARY is None, reason="Node.js is unavailable")
def test_historical_artifact_rendering_contains_no_write_controls() -> None:
    iteration_source = Path("app/static/modules/creator-iteration-history.js").read_text(encoding="utf-8")
    record_source = Path("app/static/modules/creator-execution-record.js").read_text(encoding="utf-8")
    outcome_source = Path("app/static/modules/creator-outcome-snapshot.js").read_text(encoding="utf-8")
    script = f"""
const vm = require("vm");
const context = {{window: {{}}}};
vm.runInNewContext({json.dumps(record_source)}, context, {{filename: "creator-execution-record.js"}});
vm.runInNewContext({json.dumps(outcome_source)}, context, {{filename: "creator-outcome-snapshot.js"}});
vm.runInNewContext({json.dumps(iteration_source)}, context, {{filename: "creator-iteration-history.js"}});
const view = context.window.CreatorIterationHistoryView;
const record = {{version: "1.0", status: "completed", selected_topic: "选题", production_status: {{shooting: "completed", editing: "completed", publishing: "completed"}}, feedback: {{was_used: true, difficulty: "normal", quality_rating: 4, result_rating: 5, notes: "done"}}}};
const outcome = {{version: "1.0", expected_metric: "播放", publication: {{platform: "douyin", platform_item_id: "123", published_at: "2026-08-10T00:00:00+00:00"}}, snapshots: [{{snapshot_id: "snapshot_a", captured_at: "2026-08-11T00:00:00+00:00", metrics: {{views: 0, likes: null, comments: 0, shares: null, collects: 0}}, derived: {{delta_from_previous: {{}}}}}}], summary: {{snapshot_count: 1, latest_metrics: {{views: 0, likes: null, comments: 0, shares: null, collects: 0}}, latest_derived: {{}}}}}};
const html = view.renderDetail(
  {{summary: {{iteration_id: "iteration_legacy_001", label: "第 1 轮"}}, artifact_availability: {{execution_pack: "missing", execution_record: "ready", outcome: "ready"}}}},
  {{"execution-record": record, outcome}},
  {{record: context.window.CreatorExecutionRecordView, outcome: context.window.CreatorOutcomeSnapshotView}}
);
console.log(JSON.stringify({{
  readonly: html.includes("历史只读") && html.includes("执行反馈") && html.includes("数据快照历史"),
  noButton: !html.includes("<button"),
  noInput: !html.includes("<input") && !html.includes("<select") && !html.includes("<textarea"),
  zero: html.includes(">0<"),
  missing: html.includes("—"),
}}));
"""

    result = _run_node(script)

    assert result == {
        "readonly": True,
        "noButton": True,
        "noInput": True,
        "zero": True,
        "missing": True,
    }


def test_home_includes_iteration_module_and_non_polling_orchestration() -> None:
    response = client.get("/")
    app_source = Path("app/static/app.js").read_text(encoding="utf-8")
    module_source = Path("app/static/modules/creator-iteration-history.js").read_text(encoding="utf-8")

    assert response.status_code == 200
    assert 'id="creator-iteration-card"' in response.text
    assert "/static/modules/creator-iteration-history.js" in response.text
    assert response.text.index("creator-iteration-history.js") < response.text.index("/static/app.js")
    assert "startNextCreatorIterationFromUi" in app_source
    assert "resetCreatorExecutionPackUi();" in app_source
    assert "hydrateCreatorIterations(setId" in app_source
    assert "setInterval" not in module_source


@pytest.mark.skipif(NODE_BINARY is None, reason="Node.js is unavailable")
def test_start_next_busy_success_and_failure_restore_without_polling() -> None:
    app_source = Path("app/static/app.js").read_text(encoding="utf-8")
    start = app_source.index("async function startNextCreatorIterationFromUi")
    end = app_source.index("function setCreatorOutcomeBusy", start)
    function_source = app_source[start:end]
    script = r'''
const source = __SOURCE__;
const status = {textContent: ""};
const creatorIterationCard = {querySelector(selector) { return selector === "[data-iteration-status]" ? status : null; }};
const busyCalls = [];
const creatorIterationHistoryView = {
  startNextPayload() { return {close_current: false, close_reason: "", close_note: ""}; },
  setBusy(_container, busy, message) { busyCalls.push({busy, message}); },
};
let creatorIterationRunning = false;
let resetCount = 0;
function resetCreatorExecutionPackUi() { resetCount += 1; }
async function hydrateCreatorIterations() { return {current_iteration_id: "iteration_new"}; }
async function readJsonResponse(response) { return response.payload; }
let mode = "pending-success";
let resolveRequest = null;
let request = null;
async function fetch(url, options) {
  request = {url, method: options.method, body: JSON.parse(options.body)};
  if (mode === "pending-success") {
    return await new Promise((resolve) => {
      resolveRequest = () => resolve({payload: {ok: true, current_iteration: {sequence: 2}}});
    });
  }
  return {payload: {ok: false, error_code: "CURRENT_ITERATION_ACTIVE", message: "仍在执行"}};
}
eval(source);
(async () => {
  const pending = startNextCreatorIterationFromUi("clone_frontend_test");
  await Promise.resolve();
  const busy = creatorIterationRunning === true && busyCalls[0]?.busy === true;
  resolveRequest();
  const success = await pending;
  const successRestored = creatorIterationRunning === false;
  mode = "failure";
  const failed = await startNextCreatorIterationFromUi("clone_frontend_test");
  const failureRestored = creatorIterationRunning === false
    && busyCalls.at(-1)?.busy === false
    && busyCalls.at(-1)?.message.includes("CURRENT_ITERATION_ACTIVE");
  process.stdout.write(JSON.stringify({
    busy,
    success,
    successRestored,
    resetCount,
    status: status.textContent,
    request,
    failed,
    failureRestored,
    hasPolling: source.includes("setInterval"),
    resetsStrategy: source.includes("currentCreatorStrategyPlan = null"),
  }));
})();
'''.replace("__SOURCE__", json.dumps(function_source))

    result = _run_node(script)

    assert result["busy"] is True
    assert result["success"] is True
    assert result["successRestored"] is True
    assert result["resetCount"] == 1
    assert "第 2 轮" in result["status"]
    assert result["request"] == {
        "url": "/api/creator-intelligence/projects/clone_frontend_test/iterations/start-next",
        "method": "POST",
        "body": {"close_current": False, "close_reason": "", "close_note": ""},
    }
    assert result["failed"] is False
    assert result["failureRestored"] is True
    assert result["hasPolling"] is False
    assert result["resetsStrategy"] is False


def test_iteration_styles_stack_without_page_level_overflow() -> None:
    css = Path("app/static/app.css").read_text(encoding="utf-8")

    assert ".creator-iteration-current-facts" in css
    assert ".creator-iteration-history-facts" in css
    assert "@media (max-width: 820px)" in css
    assert "@media (max-width: 480px)" in css
    assert "grid-template-columns: 1fr;" in css
    assert "min-width: 0;" in css
