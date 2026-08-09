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


def _frontend_pack() -> dict:
    return {
        "version": "1.0",
        "topic": {
            "title": "三种人物状态测试",
            "angle": "同一妆造做甜美、冷感和反差对比",
            "audience": "COS 观众",
            "goal": "验证停留",
            "expected_metric": "停留与评论",
        },
        "creative_basis": {
            "summary": "来自代表样本与首帧规律。",
            "creator_rules": ["首帧直接出现人物"],
            "hook_patterns": ["0-1 秒近景"],
            "formulas": ["结果前置三拍结构"],
        },
        "hook": {
            "visual": "第一帧人物近景",
            "spoken_or_caption": "你更喜欢哪一种？",
            "purpose": "建立对比悬念",
            "duration_hint": "0-3s",
        },
        "script": {
            "opening": "先给完整妆造",
            "beats": [
                {"purpose": "甜美", "script": "微笑看镜头", "duration_hint": "3-6s"},
            ],
            "ending": "三种状态并列",
            "cta": "评论选择",
            "caption_or_voice_over": "同一妆造三种状态",
        },
        "shot_plan": [
            {
                "order": index,
                "duration_hint": f"{index}-{index + 2}s",
                "shot_type": "近景",
                "subject_action": f"动作 {index}",
                "camera": "固定",
                "composition": "居中",
                "lighting_or_scene": "柔光",
                "purpose": "推进",
            }
            for index in range(1, 5)
        ],
        "cover": {
            "visual": "人物近景",
            "composition": "主体居中",
            "headline": "三种状态",
            "reason": "沿用首帧规律",
        },
        "titles": [
            {"direction": "curiosity", "text": "你更喜欢哪一种？"},
            {"direction": "contrast", "text": "同一妆造差别有多大"},
            {"direction": "result", "text": "三种状态一次拍完"},
        ],
        "publish_copy": "同一妆造试了三种状态。",
        "hashtags": ["#COS", "#妆造", "#拍摄", "#人物状态", "#短视频"],
        "editing_notes": {
            "pace": "三秒一切",
            "cuts": "动作点切镜",
            "subtitle": "短标签",
            "music_or_sound_direction": "清晰节拍",
            "transition_notes": "匹配切换",
        },
        "production_checklist": ["检查 1", "检查 2", "检查 3", "检查 4", "检查 5"],
        "evidence_refs": [
            {"type": "sample", "sample_id": "sample_1", "title": "代表样本 1", "reason": "首帧依据"},
        ],
        "confidence": "low",
        "warnings": ["部分视觉建议需要人工确认。"],
    }


@pytest.mark.skipif(NODE_BINARY is None, reason="Node.js is unavailable")
def test_execution_pack_view_renders_actions_copy_and_collapsed_evidence() -> None:
    source = Path("app/static/modules/creator-execution-pack.js").read_text(encoding="utf-8")
    pack = _frontend_pack()
    assert "fetch(" not in source
    assert "setInterval" not in source

    script = r"""
const vm = require("vm");
const source = __SOURCE__;
const pack = __PACK__;
const context = {console};
context.window = context;
const before = Object.keys(context);
vm.runInNewContext(source, context, {filename: "creator-execution-pack.js"});
const api = context.CreatorExecutionPackView;
const topics = api.renderTopicChoices([
  {title: "选题 A", angle: "角度 A", expected_metric: "评论"},
  {title: "<unsafe>", requires_review: true},
]);
const markup = api.renderPack(pack);
const fullText = api.packText(pack);
const scriptText = api.packText(pack, "script");
const publishText = api.packText(pack, "publish");
const container = {innerHTML: markup, querySelector(selector) { return selector === ".creator-execution-pack" ? {} : null; }};
process.stdout.write(JSON.stringify({
  added: Object.keys(context).filter((key) => !before.includes(key)),
  frozen: Object.isFrozen(api),
  topicAction: topics.includes('data-execution-topic-index="0"') && topics.includes("用这个选题生成"),
  escapedTopic: topics.includes("&lt;unsafe&gt;") && !topics.includes("<unsafe>"),
  lowWarning: markup.includes("建议人工复核"),
  sections: ["为什么值得拍", "前 3 秒 Hook", "具体脚本", "实际镜头表", "封面", "标题候选", "发布文案", "剪辑建议", "发布前检查"].every((value) => markup.includes(value)),
  evidenceCollapsed: /<details class="execution-pack-evidence-details">/.test(markup) && !/<details[^>]*\sopen(?:\s|>)/.test(markup),
  evidenceRendered: markup.includes("代表样本 1") && markup.includes("为什么这样生成"),
  fullCopy: fullText.includes("# 三种人物状态测试") && fullText.includes("## 为什么值得拍") && fullText.includes("## 镜头表") && fullText.includes("## 发布前检查") && fullText.includes("## 人工复核提示"),
  scriptCopy: scriptText.includes("开场：先给完整妆造") && scriptText.includes("CTA：评论选择"),
  publishCopy: publishText.includes("同一妆造试了三种状态") && publishText.includes("#COS"),
  hasPack: api.hasPack(container),
}));
"""
    script = script.replace("__SOURCE__", json.dumps(source)).replace(
        "__PACK__",
        json.dumps(pack, ensure_ascii=False),
    )
    result = run_node(script)

    assert result["added"] == ["CreatorExecutionPackView"]
    assert result["frozen"] is True
    assert result["topicAction"] is True
    assert result["escapedTopic"] is True
    assert result["lowWarning"] is True
    assert result["sections"] is True
    assert result["evidenceCollapsed"] is True
    assert result["evidenceRendered"] is True
    assert result["fullCopy"] is True
    assert result["scriptCopy"] is True
    assert result["publishCopy"] is True
    assert result["hasPack"] is True


@pytest.mark.skipif(NODE_BINARY is None, reason="Node.js is unavailable")
def test_execution_pack_generation_busy_success_and_failure_restore_buttons() -> None:
    app_source = Path("app/static/app.js").read_text(encoding="utf-8")
    start = app_source.index("function setExecutionTopicButtonsBusy")
    end = app_source.index("async function generateCreatorStrategyPlan", start)
    generation_source = app_source[start:end]
    assert "setInterval" not in generation_source
    assert "/api/jobs/" not in generation_source

    script = """
const generationSource = __GENERATION_SOURCE__;
function button(index) {
  return {dataset: {executionTopicIndex: String(index)}, disabled: false, textContent: "用这个选题生成"};
}
const buttons = [button(0), button(1)];
const creatorStrategyPlanResult = {querySelectorAll() { return buttons; }};
const creatorExecutionPackCard = {classList: {remove() {}}};
const creatorExecutionPackStatus = {textContent: ""};
let creatorExecutionPackRunning = false;
let currentCreatorStrategyPlan = {next_topics: [{title: "选题 A"}, {title: "选题 B"}]};
function currentCreatorCloneSetId() { return "clone_test"; }
function normalizeItems(value) { return Array.isArray(value) ? value : []; }
let renderCount = 0;
function renderCreatorExecutionPack(pack) { renderCount += 1; return Boolean(pack && pack.topic); }
async function readJsonResponse(response) { return response.payload; }
let resolveFetch;
let fetchMode = "success";
async function fetch() {
  return await new Promise((resolve) => { resolveFetch = () => resolve(fetchMode === "success"
    ? {payload: {ok: true, execution_pack: {topic: {title: "选题 A"}}}}
    : {payload: {ok: false, error_code: "LLM_REQUEST_FAILED", message: "mock failure"}}); });
}
eval(generationSource);
(async () => {
  const successPromise = generateCreatorExecutionPack(0);
  await Promise.resolve();
  const successBusy = buttons.every((item) => item.disabled) && buttons[0].textContent === "正在生成...";
  resolveFetch();
  const success = await successPromise;
  const successRestored = buttons.every((item) => !item.disabled && item.textContent === "用这个选题生成");

  fetchMode = "failure";
  const failurePromise = generateCreatorExecutionPack(1);
  await Promise.resolve();
  const failureBusy = buttons.every((item) => item.disabled) && buttons[1].textContent === "正在生成...";
  resolveFetch();
  const failure = await failurePromise;
  const failureRestored = buttons.every((item) => !item.disabled && item.textContent === "用这个选题生成");
  process.stdout.write(JSON.stringify({
    success, successBusy, successRestored,
    failure, failureBusy, failureRestored,
    renderCount,
    failureMessage: creatorExecutionPackStatus.textContent,
    running: creatorExecutionPackRunning,
  }));
})();
"""
    script = script.replace("__GENERATION_SOURCE__", json.dumps(generation_source))
    result = run_node(script)

    assert result["success"] is True
    assert result["successBusy"] is True
    assert result["successRestored"] is True
    assert result["failure"] is False
    assert result["failureBusy"] is True
    assert result["failureRestored"] is True
    assert result["renderCount"] == 1
    assert "LLM_REQUEST_FAILED" in result["failureMessage"]
    assert result["running"] is False


def test_index_exposes_execution_pack_controls_without_a_new_page() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert 'id="creator-execution-pack-card"' in response.text
    assert 'id="copy-creator-execution-pack-button"' in response.text
    assert "/static/modules/creator-execution-pack.js" in response.text
    assert "下一条内容" in response.text


def test_execution_pack_mobile_css_stacks_cards_without_page_overflow() -> None:
    css = Path("app/static/app.css").read_text(encoding="utf-8")

    assert "@media (max-width: 720px)" in css
    assert ".execution-pack-primary-grid" in css
    assert ".execution-shot-grid" in css
    assert "grid-template-columns: 1fr;" in css
    assert "min-width: 0;" in css
