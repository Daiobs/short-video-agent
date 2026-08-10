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


def _frontend_outcome() -> dict:
    return {
        "version": "1.0",
        "project_id": "clone_frontend_outcome",
        "expected_metric": "停留与评论 <script>",
        "publication": {
            "platform": "douyin",
            "platform_item_id": "76543210",
            "published_url": "https://www.douyin.com/video/76543210",
            "published_at": "2026-08-10T09:30:00+08:00",
        },
        "snapshots": [
            {
                "snapshot_id": "snapshot_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "captured_at": "2026-08-10T02:00:00+00:00",
                "source": "manual",
                "metrics": {"views": 1000, "likes": 100, "comments": 10, "shares": None, "collects": 0},
                "derived": {
                    "known_interactions": 110,
                    "known_interaction_metric_count": 3,
                    "engagement_rate": None,
                    "like_rate": 0.1,
                    "comment_rate": 0.01,
                    "share_rate": None,
                    "collect_rate": 0,
                    "delta_from_previous": {"views": None, "likes": None, "comments": None, "shares": None, "collects": None},
                },
            },
            {
                "snapshot_id": "snapshot_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "captured_at": "2026-08-10T03:00:00+00:00",
                "source": "manual",
                "metrics": {"views": 900, "likes": 120, "comments": 15, "shares": 2, "collects": 0},
                "derived": {
                    "known_interactions": 137,
                    "known_interaction_metric_count": 4,
                    "engagement_rate": 137 / 900,
                    "like_rate": 120 / 900,
                    "comment_rate": 15 / 900,
                    "share_rate": 2 / 900,
                    "collect_rate": 0,
                    "delta_from_previous": {"views": -100, "likes": 20, "comments": 5, "shares": None, "collects": 0},
                },
            },
        ],
        "summary": {
            "snapshot_count": 2,
            "latest_snapshot_id": "snapshot_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "latest_captured_at": "2026-08-10T03:00:00+00:00",
            "latest_metrics": {"views": 900, "likes": 120, "comments": 15, "shares": 2, "collects": 0},
            "latest_derived": {
                "engagement_rate": 137 / 900,
                "like_rate": 120 / 900,
                "comment_rate": 15 / 900,
                "share_rate": 2 / 900,
                "collect_rate": 0,
            },
        },
    }


@pytest.mark.skipif(NODE_BINARY is None, reason="Node.js is unavailable")
def test_outcome_view_preserves_missing_zero_rates_history_and_escaping() -> None:
    source = Path("app/static/modules/creator-outcome-snapshot.js").read_text(encoding="utf-8")
    outcome = _frontend_outcome()
    assert "fetch(" not in source
    assert "setInterval" not in source

    script = r'''
const vm = require("vm");
const source = __SOURCE__;
const outcome = __OUTCOME__;
const context = {console};
context.window = context;
vm.runInNewContext(source, context, {filename: "creator-outcome-snapshot.js"});
const api = context.CreatorOutcomeSnapshotView;
const markup = api.renderOutcome(outcome);
const values = {
  views: {value: ""},
  likes: {value: "0"},
  comments: {value: "12"},
  shares: {value: ""},
  collects: {value: "3"},
};
const metricContainer = {
  querySelector(selector) {
    const match = selector.match(/data-outcome-new-metric="([^"]+)"/);
    return match ? values[match[1]] : null;
  },
};
const publicationValues = {
  platform: {value: "xhs"},
  platform_item_id: {value: " note_1 "},
  published_url: {value: " https://www.xiaohongshu.com/explore/note_1 "},
  published_at: {value: ""},
};
const publicationContainer = {
  querySelector(selector) {
    const match = selector.match(/data-outcome-publication="([^"]+)"/);
    return match ? publicationValues[match[1]] : null;
  },
};
process.stdout.write(JSON.stringify({
  frozen: Object.isFrozen(api),
  escaped: markup.includes("停留与评论 &lt;script&gt;") && !markup.includes("<script>"),
  sections: ["作品信息", "预期关注指标", "最新数据", "新增数据快照", "数据快照历史", "修正数据"].every((value) => markup.includes(value)),
  missing: markup.includes("—"),
  explicitZero: markup.includes(">0</strong>"),
  rates: markup.includes("13.33%") && markup.includes("0.00%"),
  negativeDelta: markup.includes("-100"),
  positiveDelta: markup.includes("+20"),
  metricsPayload: api.metricsPayload(metricContainer, "new"),
  publicationPayload: api.publicationPayload(publicationContainer),
  invalidMetrics: api.metricsPayload({querySelector() { return {value: "1.5"}; }}, "new"),
}));
'''
    script = script.replace("__SOURCE__", json.dumps(source)).replace(
        "__OUTCOME__",
        json.dumps(outcome, ensure_ascii=False),
    )
    result = run_node(script)

    assert result["frozen"] is True
    assert result["escaped"] is True
    assert result["sections"] is True
    assert result["missing"] is True
    assert result["explicitZero"] is True
    assert result["rates"] is True
    assert result["negativeDelta"] is True
    assert result["positiveDelta"] is True
    assert result["metricsPayload"] == {
        "views": None,
        "likes": 0,
        "comments": 12,
        "shares": None,
        "collects": 3,
    }
    assert result["publicationPayload"] == {
        "platform": "xhs",
        "platform_item_id": "note_1",
        "published_url": "https://www.xiaohongshu.com/explore/note_1",
        "published_at": None,
    }
    assert result["invalidMetrics"] is None


@pytest.mark.skipif(NODE_BINARY is None, reason="Node.js is unavailable")
def test_outcome_flow_gates_requests_and_restores_controls_after_failure() -> None:
    app_source = Path("app/static/app.js").read_text(encoding="utf-8")
    start = app_source.index("function creatorExecutionPublishingCompleted")
    end = app_source.index("function setCreatorExecutionRecordBusy", start)
    outcome_source = app_source[start:end]
    assert "setInterval" not in outcome_source
    assert "/api/jobs/" not in outcome_source

    script = r'''
const source = __SOURCE__;
function classList() {
  const values = new Set(["hidden"]);
  return {add(...items) { items.forEach((item) => values.add(item)); }, remove(...items) { items.forEach((item) => values.delete(item)); }, has(value) { return values.has(value); }};
}
const controls = [{disabled: false}, {disabled: false}];
const creatorOutcomeResult = {innerHTML: "", querySelectorAll() { return controls; }};
const creatorOutcomeCard = {classList: classList()};
const creatorOutcomeStatus = {textContent: ""};
const creatorOutcomeView = {
  renderLocked() { return "LOCKED"; },
  renderPublicationOnly() { return "PUBLICATION"; },
  renderOutcome(outcome) { return `READY:${outcome.summary?.snapshot_count || 0}`; },
  hasOutcome(container) { return container.innerHTML.startsWith("READY:"); },
  publicationPayload() { return {platform: "douyin", platform_item_id: "1", published_url: "", published_at: null}; },
  metricsPayload() { return {views: null, likes: 0, comments: 1, shares: null, collects: 0}; },
};
let currentCreatorExecutionRecord = {production_status: {publishing: "pending"}};
let currentCreatorOutcome = null;
let creatorOutcomeRunning = false;
function resetCreatorOutcomeUi() { currentCreatorOutcome = null; creatorOutcomeResult.innerHTML = ""; creatorOutcomeCard.classList.add("hidden"); }
function currentCreatorCloneSetId() { return "clone_outcome_frontend"; }
async function readJsonResponse(response) { return response.payload; }
const requests = [];
let failure = false;
function outcome(count) { return {version: "1.0", snapshots: [], summary: {snapshot_count: count}}; }
async function fetch(url, options = {}) {
  requests.push({url, method: options.method || "GET", body: options.body || ""});
  if (failure) return {payload: {ok: false, error_code: "MOCK_FAILED", message: "mock failure"}};
  if ((options.method || "GET") === "GET") return {payload: {ok: true, outcome: outcome(1)}};
  if (options.method === "PUT") return {payload: {ok: true, outcome: outcome(0)}};
  if (options.method === "POST") return {payload: {ok: true, outcome: outcome(2)}};
  return {payload: {ok: true, outcome: outcome(3)}};
}
eval(source);
(async () => {
  configureCreatorOutcomeUi(currentCreatorExecutionRecord);
  const pendingLocked = creatorOutcomeResult.innerHTML === "LOCKED" && requests.length === 0;
  currentCreatorExecutionRecord = {production_status: {publishing: "completed"}};
  configureCreatorOutcomeUi(currentCreatorExecutionRecord);
  const publicationReady = creatorOutcomeResult.innerHTML === "PUBLICATION";
  await hydrateCreatorOutcome("clone_outcome_frontend");
  const hydrated = currentCreatorOutcome.summary.snapshot_count === 1;
  await saveCreatorOutcomePublication();
  await addCreatorOutcomeSnapshot();
  const snapshotElement = {dataset: {outcomeSnapshotId: "snapshot_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}};
  await patchCreatorOutcomeSnapshot(snapshotElement);
  failure = true;
  const failed = await addCreatorOutcomeSnapshot();
  process.stdout.write(JSON.stringify({
    pendingLocked,
    publicationReady,
    hydrated,
    methods: requests.slice(0, 4).map((item) => item.method),
    paths: requests.slice(0, 4).map((item) => item.url),
    postBody: JSON.parse(requests.find((item) => item.method === "POST")?.body || "{}"),
    failed,
    controlsRestored: controls.every((item) => item.disabled === false),
    failureMessage: creatorOutcomeStatus.textContent,
    running: creatorOutcomeRunning,
  }));
})();
'''
    script = script.replace("__SOURCE__", json.dumps(outcome_source))
    result = run_node(script)

    assert result["pendingLocked"] is True
    assert result["publicationReady"] is True
    assert result["hydrated"] is True
    assert result["methods"] == ["GET", "PUT", "POST", "PATCH"]
    assert result["paths"][-1].endswith("/outcome/snapshots/snapshot_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    assert result["postBody"] == {
        "views": None,
        "likes": 0,
        "comments": 1,
        "shares": None,
        "collects": 0,
    }
    assert result["failed"] is False
    assert result["controlsRestored"] is True
    assert "MOCK_FAILED" in result["failureMessage"]
    assert result["running"] is False


def test_index_and_css_expose_responsive_outcome_controls() -> None:
    response = TestClient(app).get("/")
    css = Path("app/static/app.css").read_text(encoding="utf-8")

    assert response.status_code == 200
    assert 'id="creator-outcome-card"' in response.text
    assert 'id="creator-outcome-status"' in response.text
    assert 'id="creator-outcome-result"' in response.text
    assert "/static/modules/creator-outcome-snapshot.js" in response.text
    assert response.text.index('id="creator-execution-record-card"') < response.text.index('id="creator-outcome-card"')
    assert ".creator-outcome-metric-grid" in css
    assert "@media (max-width: 720px)" in css
    assert ".creator-outcome-publication-grid" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in css
