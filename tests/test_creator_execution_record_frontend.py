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


def _frontend_record(*, status: str = "in_progress") -> dict:
    return {
        "version": "1.0",
        "project_id": "clone_frontend_test",
        "execution_pack_generated_at": "2026-08-09T10:00:00+00:00",
        "execution_pack_topic_index": 1,
        "selected_topic": "<三种人物状态>",
        "status": status,
        "production_status": {
            "shooting": "completed",
            "editing": "pending",
            "publishing": "skipped",
        },
        "feedback": {
            "was_used": True,
            "difficulty": "normal",
            "quality_rating": 4,
            "result_rating": None,
            "notes": "<需要补一个近景>",
        },
        "created_at": "2026-08-09T10:01:00+00:00",
        "updated_at": "2026-08-09T10:02:00+00:00",
    }


@pytest.mark.skipif(NODE_BINARY is None, reason="Node.js is unavailable")
def test_execution_record_view_renders_status_controls_and_feedback_patch() -> None:
    source = Path("app/static/modules/creator-execution-record.js").read_text(encoding="utf-8")
    record = _frontend_record()
    assert "fetch(" not in source
    assert "setInterval" not in source

    script = r'''
const vm = require("vm");
const source = __SOURCE__;
const record = __RECORD__;
const context = {console};
context.window = context;
const before = Object.keys(context);
vm.runInNewContext(source, context, {filename: "creator-execution-record.js"});
const api = context.CreatorExecutionRecordView;
const markup = api.renderRecord(record);
const archivedMarkup = api.renderRecord({...record, status: "archived"});
const values = {
  was_used: {checked: false},
  difficulty: {value: "hard"},
  quality_rating: {value: "5"},
  result_rating: {value: ""},
  notes: {value: "复盘备注"},
};
const container = {
  innerHTML: markup,
  querySelector(selector) {
    if (selector === ".creator-execution-record") return {};
    const match = selector.match(/data-execution-feedback="([^"]+)"/);
    return match ? values[match[1]] : null;
  },
};
process.stdout.write(JSON.stringify({
  added: Object.keys(context).filter((key) => !before.includes(key)),
  frozen: Object.isFrozen(api),
  escaped: markup.includes("&lt;三种人物状态&gt;") && markup.includes("&lt;需要补一个近景&gt;"),
  status: markup.includes("执行中"),
  stages: ["拍摄", "剪辑", "发布", "标记完成", "跳过"].every((value) => markup.includes(value)),
  feedback: ["执行难度", "方案质量", "实际结果", "保存反馈"].every((value) => markup.includes(value)),
  archive: markup.includes('data-execution-record-action="archive"'),
  archivedNoArchive: !archivedMarkup.includes('data-execution-record-action="archive"') && archivedMarkup.includes("disabled"),
  feedbackPatch: api.feedbackPatch(container),
  stagePatches: ["shooting", "editing", "publishing"].map((stage) => api.stagePatch(stage, "completed")),
  invalidStage: api.stagePatch("unknown", "completed"),
  hasRecord: api.hasRecord(container),
}));
'''
    script = script.replace("__SOURCE__", json.dumps(source)).replace(
        "__RECORD__",
        json.dumps(record, ensure_ascii=False),
    )
    result = run_node(script)

    assert result["added"] == ["CreatorExecutionRecordView"]
    assert result["frozen"] is True
    assert result["escaped"] is True
    assert result["status"] is True
    assert result["stages"] is True
    assert result["feedback"] is True
    assert result["archive"] is True
    assert result["archivedNoArchive"] is True
    assert result["feedbackPatch"] == {
        "feedback": {
            "was_used": False,
            "difficulty": "hard",
            "quality_rating": 5,
            "result_rating": None,
            "notes": "复盘备注",
        }
    }
    assert result["stagePatches"] == [
        {"production_status": {"shooting": "completed"}},
        {"production_status": {"editing": "completed"}},
        {"production_status": {"publishing": "completed"}},
    ]
    assert result["invalidStage"] is None
    assert result["hasRecord"] is True


@pytest.mark.skipif(NODE_BINARY is None, reason="Node.js is unavailable")
def test_execution_record_start_hydrate_patch_and_failure_restore_controls() -> None:
    app_source = Path("app/static/app.js").read_text(encoding="utf-8")
    start = app_source.index("function renderCreatorExecutionRecord")
    end = app_source.index("function setExecutionTopicButtonsBusy", start)
    record_source = app_source[start:end]
    assert "setInterval" not in record_source
    assert "/api/jobs/" not in record_source

    script = r'''
const source = __SOURCE__;
function classList() {
  const values = new Set(["hidden"]);
  return {add(...items) { items.forEach((item) => values.add(item)); }, remove(...items) { items.forEach((item) => values.delete(item)); }, has(value) { return values.has(value); }};
}
const controls = [{disabled: false, dataset: {executionStage: "shooting"}}, {disabled: false, dataset: {}}];
const creatorExecutionRecordResult = {innerHTML: "", querySelectorAll() { return controls; }};
const creatorExecutionRecordCard = {classList: classList()};
const startCreatorExecutionRecordButton = {classList: classList(), disabled: false, textContent: "开始执行"};
const creatorExecutionRecordStatus = {textContent: ""};
const creatorExecutionRecordView = {renderRecord(record) { return `<section class="creator-execution-record">${record.status}</section>`; }, hasRecord() { return true; }};
let currentCreatorExecutionPack = {topic: {title: "测试选题"}};
let currentCreatorExecutionRecord = null;
let creatorExecutionRecordRunning = false;
function currentCreatorCloneSetId() { return "clone_frontend_test"; }
function resetCreatorExecutionRecordUi() { currentCreatorExecutionRecord = null; }
async function readJsonResponse(response) { return response.payload; }
let mode = "start-success";
let pendingResolve = null;
const requests = [];
function record(status = "draft") { return {version: "1.0", status, selected_topic: "测试选题", production_status: {shooting: "pending", editing: "pending", publishing: "pending"}, feedback: {was_used: false, difficulty: "", quality_rating: null, result_rating: null, notes: ""}}; }
async function fetch(url, options = {}) {
  requests.push({url, method: options.method || "GET", body: options.body || ""});
  if (mode === "start-pending") {
    return await new Promise((resolve) => { pendingResolve = () => resolve({payload: {ok: true, execution_record: record("draft")}}); });
  }
  if (mode === "failure-pending") {
    return await new Promise((resolve) => { pendingResolve = () => resolve({payload: {ok: false, error_code: "SAVE_FAILED", message: "mock failure"}}); });
  }
  if (mode === "hydrate") return {payload: {ok: true, execution_record: record("in_progress")}};
  if (mode === "patch") return {payload: {ok: true, execution_record: record("in_progress")}};
  return {payload: {ok: true, execution_record: record("draft")}};
}
eval(source);
(async () => {
  mode = "start-pending";
  const startPromise = startCreatorExecutionRecord();
  await Promise.resolve();
  const startBusy = creatorExecutionRecordRunning && startCreatorExecutionRecordButton.disabled && startCreatorExecutionRecordButton.textContent === "正在开始...";
  pendingResolve();
  const started = await startPromise;
  const startRestored = !creatorExecutionRecordRunning && !startCreatorExecutionRecordButton.disabled && currentCreatorExecutionRecord.status === "draft";

  mode = "patch";
  const patched = await patchCreatorExecutionRecord({production_status: {shooting: "completed"}});
  const patchRequest = requests.find((item) => item.method === "PATCH");

  mode = "hydrate";
  const hydrated = await hydrateCreatorExecutionRecord("clone_frontend_test");

  currentCreatorExecutionRecord = null;
  mode = "failure-pending";
  const failurePromise = startCreatorExecutionRecord();
  await Promise.resolve();
  const failureBusy = creatorExecutionRecordRunning && startCreatorExecutionRecordButton.disabled;
  pendingResolve();
  const failed = await failurePromise;
  const failureRestored = !creatorExecutionRecordRunning && !startCreatorExecutionRecordButton.disabled && creatorExecutionRecordStatus.textContent.includes("SAVE_FAILED");

  process.stdout.write(JSON.stringify({
    started, startBusy, startRestored,
    patched,
    patchMethod: patchRequest?.method,
    patchBody: JSON.parse(patchRequest?.body || "{}"),
    hydratedStatus: hydrated?.status,
    failed, failureBusy, failureRestored,
    hasPolling: source.includes("setInterval"),
  }));
})();
'''
    script = script.replace("__SOURCE__", json.dumps(record_source))
    result = run_node(script)

    assert result["started"] is True
    assert result["startBusy"] is True
    assert result["startRestored"] is True
    assert result["patched"] is True
    assert result["patchMethod"] == "PATCH"
    assert result["patchBody"] == {"production_status": {"shooting": "completed"}}
    assert result["hydratedStatus"] == "in_progress"
    assert result["failed"] is False
    assert result["failureBusy"] is True
    assert result["failureRestored"] is True
    assert result["hasPolling"] is False


def test_index_exposes_execution_record_controls_only_inside_execution_pack() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert 'id="start-creator-execution-record-button" class="hidden"' in response.text
    assert 'id="creator-execution-record-card"' in response.text
    assert 'id="creator-execution-record-result"' in response.text
    assert "/static/modules/creator-execution-record.js" in response.text
    assert response.text.index('id="creator-execution-pack-card"') < response.text.index('id="creator-execution-record-card"')


def test_ready_execution_pack_reveals_explicit_start_control_without_polling() -> None:
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    render_start = source.index("function renderCreatorExecutionPack")
    render_end = source.index("function renderCreatorExecutionRecord", render_start)
    render_source = source[render_start:render_end]

    assert "resetCreatorExecutionRecordUi({showStart: true});" in render_source
    assert "setInterval" not in render_source
    assert "/api/jobs/" not in render_source


def test_execution_record_mobile_css_stacks_without_page_overflow() -> None:
    css = Path("app/static/app.css").read_text(encoding="utf-8")

    assert ".execution-record-stage-grid" in css
    assert ".execution-record-feedback-grid" in css
    assert "grid-template-columns: minmax(0, 1fr);" in css
    assert ".creator-execution-record" in css
    assert "min-width: 0;" in css
