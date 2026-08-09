from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.errors import AppError, ErrorCode
from app.main import app
from app.models import Job
from app.services.creator_clone import CloneSample, CloneSampleSet, creator_clone_dir, save_sample_set
from app.services.creator_intelligence import execution_pack as execution_pack_module
from app.services.creator_intelligence.execution_pack import (
    EXECUTION_PACK_FILENAME,
    ExecutionPackValidationContext,
    build_creator_execution_pack_prompt,
    generate_creator_execution_pack,
    validate_creator_execution_pack,
)
from app.services.creator_intelligence.llm_execution import LLMExecutionEngine
from app.services.llm_budget import DistillDeadline


client = TestClient(app)


class FakeProvider:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0
        self.prompts: list[str] = []

    def analyze(self, prompt: str, image_paths: list[Path]) -> Any:
        self.calls += 1
        self.prompts.append(prompt)
        outcome = self.outcomes[min(self.calls - 1, len(self.outcomes) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return copy.deepcopy(outcome)

    def public_diagnostics(self) -> dict[str, str]:
        return {"provider": "mock"}


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


class ClockedProvider(FakeProvider):
    def __init__(self, outcomes: list[Any], *, clock: FakeClock, first_attempt_seconds: float) -> None:
        super().__init__(outcomes)
        self.clock = clock
        self.first_attempt_seconds = first_attempt_seconds

    def analyze(self, prompt: str, image_paths: list[Path]) -> Any:
        if self.calls == 0:
            self.clock.advance(self.first_attempt_seconds)
        return super().analyze(prompt, image_paths)


def _sample_set(*, partial: bool = False) -> CloneSampleSet:
    count = 6 if partial else 3
    samples: list[CloneSample] = []
    for index in range(count):
        failed = partial and index == count - 1
        samples.append(
            CloneSample(
                sample_id=f"sample_{index + 1}",
                aweme_id=f"76500000000000000{index + 1}",
                title=f"代表样本 {index + 1}",
                source_type="douyin",
                media_type="video",
                duration=12.0 + index,
                like_count=1000 - index * 50,
                comment_count=30 + index,
                share_count=12 + index,
                collect_count=18 + index,
                understanding_level="metadata_only" if failed else "full",
                has_video=not failed,
                has_frames=not failed,
                has_asr=not failed,
                has_ocr=not failed,
                has_comments=not failed,
                enrichment_status="failed" if failed else "success",
                selected=True,
            )
        )
    return CloneSampleSet(
        set_id="clone_execution_pack_test",
        title="执行包测试素材池",
        creator_name="测试创作者",
        source_platform="douyin",
        content_profile="beauty_cos",
        profile_metadata={
            "profile_url": "https://www.douyin.com/user/redacted",
            "cookie": "sessionid=must-not-leak",
        },
        samples=samples,
        selected_sample_ids=[sample.sample_id for sample in samples],
    )


def _report(*, score: int = 88) -> dict[str, Any]:
    return {
        "creator_clone_strategy": {
            "positioning": "甜美 COS 近景视觉账号",
            "content_strategy": ["首帧先给最终造型，再补动作变化"],
            "hooks": ["0-1 秒人物近景直接给脸和眼神"],
            "templates": [
                {
                    "name": "结果前置三拍结构",
                    "beat_structure": ["首帧结果", "动作递进", "互动收口"],
                }
            ],
            "anti_patterns": ["不要用空镜拖慢开头"],
            "idea_bank": [{"title": "同一妆造三种人物状态"}],
            "validation_rules": ["3 秒内必须出现主体和信息差"],
        },
        "creator_positioning": {
            "audience_promise": "喜欢甜美 COS 和低成本出片的年轻观众",
        },
        "creator_report_view_model": {
            "sections": {
                "formulas": ["结果前置 + 动作递进 + 评论提问"],
                "next_ideas": ["同一造型甜美、冷感、反差三版"],
            }
        },
        "report_quality": {"quality_score": score},
        "diagnostics": {"source_label": "mocked creator report"},
        "untrusted": {
            "authorization": "Bearer hidden",
            "signed_url": "https://video.example.test/signed?token=hidden",
        },
    }


def _strategy_plan(*, low_confidence: bool = False) -> dict[str, Any]:
    topics = [
        {
            "title": "同一妆造三种人物状态测试",
            "angle": "甜美、冷感、反差各拍一版",
            "audience": "喜欢甜美 COS 和低成本出片的年轻观众",
            "goal": "验证哪一种人物状态更能带来停留和评论",
            "expected_metric": "停留与评论",
            "why": "已有样本证明首帧人物状态能影响停留",
        }
    ]
    topics.extend(
        {
            "title": f"可执行选题 {index}",
            "angle": f"结构迁移测试 {index}",
            "expected_metric": "停留与互动",
        }
        for index in range(2, 6)
    )
    return {
        "next_topics": topics,
        "script_templates": [
            {"name": f"脚本结构 {index}", "beats": ["结果前置", "动作推进", "互动收口"]}
            for index in range(1, 4)
        ],
        "shot_templates": [
            {"name": f"镜头结构 {index}", "timeline": ["近景", "中景", "细节"]}
            for index in range(1, 4)
        ],
        "title_cover_suggestions": [
            {"title": f"封面方向 {index}", "cover": "人物居中近景"}
            for index in range(1, 6)
        ],
        "pre_publish_checklist": [f"发布检查 {index}" for index in range(1, 6)],
        "low_confidence_notes": ["部分视觉样本证据不足，需要人工确认。"] if low_confidence else [],
        "source": {"content_profile": "beauty_cos"},
    }


def _execution_payload(*, project_id: str = "clone_execution_pack_test") -> dict[str, Any]:
    topic = _strategy_plan()["next_topics"][0]
    return {
        "version": "1.0",
        "project_id": project_id,
        "topic_index": 0,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "topic": {
            "title": topic["title"],
            "angle": topic["angle"],
            "audience": topic["audience"],
            "goal": topic["goal"],
            "expected_metric": topic["expected_metric"],
        },
        "creative_basis": {
            "summary": "首帧人物状态与动作递进都有既有报告和代表样本支撑。",
            "creator_rules": ["3 秒内必须出现主体和信息差"],
            "hook_patterns": ["0-1 秒人物近景直接给脸和眼神"],
            "formulas": ["结果前置三拍结构"],
            "representative_samples": [
                {"sample_id": "sample_1", "reason": "高互动样本验证首帧近景有效"},
            ],
        },
        "hook": {
            "visual": "第一帧用人物近景直接展示完成妆造，眼神看向镜头。",
            "spoken_or_caption": "同一套妆造，哪种状态最适合我？",
            "purpose": "结果前置并建立三种状态的比较悬念。",
            "duration_hint": "0-3s",
        },
        "script": {
            "opening": "定格完成妆造，字幕提出三种状态对比。",
            "beats": [
                {"order": 1, "purpose": "展示甜美", "script": "微笑并轻抬手", "duration_hint": "3-6s"},
                {"order": 2, "purpose": "展示冷感", "script": "收表情并侧看镜头", "duration_hint": "6-9s"},
                {"order": 3, "purpose": "制造反差", "script": "快速转身切换动作", "duration_hint": "9-12s"},
            ],
            "ending": "三种状态快速并列回放。",
            "cta": "评论告诉我下一条保留哪一种。",
            "caption_or_voice_over": "同一套妆造，甜美、冷感和反差，你选哪一个？",
        },
        "shot_plan": [
            {
                "order": index,
                "duration_hint": f"{(index - 1) * 3}-{index * 3}s",
                "shot_type": "近景" if index < 3 else "中景",
                "subject_action": f"完成第 {index} 个明确动作",
                "camera": "固定机位，最后一拍轻推近",
                "composition": "人物居中，脸部位于上三分之一",
                "lighting_or_scene": "柔光正面补光，背景保持干净",
                "purpose": f"推进状态对比 {index}",
            }
            for index in range(1, 5)
        ],
        "cover": {
            "visual": "甜美状态的人物近景",
            "composition": "人物占画面三分之二，标题放左下",
            "headline": "同一妆造三种状态",
            "reason": "首帧人物状态是已有报告中最稳定的视觉规律",
        },
        "titles": [
            {"direction": "curiosity", "text": "同一套妆造，哪种状态更适合我？"},
            {"direction": "contrast", "text": "甜美、冷感、反差，我居然选错了"},
            {"direction": "result", "text": "三种人物状态一次拍完"},
        ],
        "publish_copy": "同一套妆造试了三种人物状态，最后一版最意外。你更喜欢哪一种？",
        "hashtags": ["#COS", "#妆造", "#拍摄", "#人物状态", "#短视频创作"],
        "editing_notes": {
            "pace": "每 3 秒切换一次状态，开头不留空镜。",
            "cuts": "动作顶点切镜，结尾三连闪回。",
            "subtitle": "每个状态只保留一个短标签。",
            "music_or_sound_direction": "选择节拍清晰、不过度抢人声的音乐。",
            "transition_notes": "用同位置动作匹配切换，不使用复杂特效。",
        },
        "production_checklist": [
            "首帧是否直接出现完整妆造",
            "三种状态是否有清晰动作差异",
            "镜头曝光和肤色是否一致",
            "字幕是否在手机小屏可读",
            "结尾是否给出明确评论问题",
        ],
        "evidence_refs": [
            {"type": "sample", "sample_id": "sample_1", "reason": "代表样本验证首帧近景"},
            {
                "type": "creator_rule",
                "field": "hooks",
                "value": "0-1 秒人物近景直接给脸和眼神",
                "reason": "沿用已蒸馏的首帧规律",
            },
        ],
        "confidence": "high",
        "warnings": [],
        "source": {},
    }


def _validation_context(*, sample_count: int = 3, score: int = 88) -> ExecutionPackValidationContext:
    report = _report(score=score)
    plan = _strategy_plan()
    return ExecutionPackValidationContext(
        project_id="clone_execution_pack_test",
        topic_index=0,
        topic=_execution_payload()["topic"],
        valid_samples={f"sample_{index}": f"代表样本 {index}" for index in range(1, sample_count + 1)},
        creator_rule_catalog={
            "hooks": (report["creator_clone_strategy"]["hooks"][0],),
            "validation_rules": (report["creator_clone_strategy"]["validation_rules"][0],),
        },
        strategy_plan_catalog={"next_topics": (plan["next_topics"][0]["title"],)},
        source={
            "report_quality_score": score,
            "selected_count": sample_count,
            "evidence_ready_count": sample_count,
            "failed_evidence_count": 0,
            "selected_topic_index": 0,
        },
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def _write_upstream(*, partial: bool = False, score: int = 88, low_confidence: bool = False) -> tuple[CloneSampleSet, Path]:
    sample_set = _sample_set(partial=partial)
    save_sample_set(sample_set)
    output_dir = creator_clone_dir(sample_set.set_id)
    (output_dir / "creator_clone_result.json").write_text(
        json.dumps(_report(score=score), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "creator_strategy_plan.json").write_text(
        json.dumps(_strategy_plan(low_confidence=low_confidence), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return sample_set, output_dir


def test_execution_pack_schema_normalizes_bounds() -> None:
    payload = _execution_payload()
    payload["shot_plan"] = payload["shot_plan"] * 3
    payload["titles"] = payload["titles"] + [
        {"direction": "emotion", "text": "第四个真实标题"},
        {"direction": "knowledge", "text": "第五个真实标题"},
        {"direction": "result", "text": "第六个真实标题"},
    ]
    payload["hashtags"] = [f"#话题{index}" for index in range(12)]
    payload["evidence_refs"] = [
        {"type": "sample", "sample_id": f"sample_{index}", "reason": f"样本依据 {index}"}
        for index in range(1, 11)
    ]

    normalized = validate_creator_execution_pack(payload, context=_validation_context(sample_count=10))

    assert normalized["version"] == "1.0"
    assert len(normalized["shot_plan"]) == 10
    assert len(normalized["titles"]) == 5
    assert len(normalized["hashtags"]) == 10
    assert len(normalized["evidence_refs"]) == 8


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload.pop("script"), "script must be an object"),
        (lambda payload: payload.update(shot_plan=payload["shot_plan"][:3]), "shot_plan"),
        (lambda payload: payload.update(titles=payload["titles"][:2]), "titles"),
        (
            lambda payload: payload["titles"][0].update(text="示例标题 1"),
            "publishable",
        ),
        (
            lambda payload: payload["titles"][0].update(text="真实标题候选 A"),
            "publishable",
        ),
    ],
)
def test_execution_pack_schema_rejects_missing_or_short_required_sections(mutation, message: str) -> None:
    payload = _execution_payload()
    mutation(payload)

    with pytest.raises(ValueError, match=message):
        validate_creator_execution_pack(payload, context=_validation_context())


def test_invalid_evidence_and_sample_basis_are_dropped_with_warning() -> None:
    payload = _execution_payload()
    payload["creative_basis"]["creator_rules"].append("模型虚构的账号规律")
    payload["creative_basis"]["formulas"].append("模型虚构的爆款公式")
    payload["creative_basis"]["representative_samples"].append(
        {"sample_id": "sample_invented", "reason": "模型虚构的样本"}
    )
    payload["evidence_refs"].append(
        {"type": "sample", "sample_id": "sample_invented", "reason": "模型虚构的证据"}
    )

    normalized = validate_creator_execution_pack(payload, context=_validation_context())
    serialized = json.dumps(normalized, ensure_ascii=False)

    assert "sample_invented" not in serialized
    assert "模型虚构的账号规律" not in serialized
    assert "模型虚构的爆款公式" not in serialized
    assert any("无法匹配代表样本" in warning for warning in normalized["warnings"])
    assert any("无法验证的证据" in warning for warning in normalized["warnings"])


def test_generate_api_requires_report_strategy_and_valid_topic() -> None:
    sample_set = _sample_set()
    save_sample_set(sample_set)
    output_dir = creator_clone_dir(sample_set.set_id)

    response = client.post(
        f"/api/creator-intelligence/projects/{sample_set.set_id}/generate-execution-pack",
        json={"topic_index": 0},
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == ErrorCode.CREATOR_REPORT_NOT_READY

    (output_dir / "creator_clone_result.json").write_text(json.dumps(_report()), encoding="utf-8")
    response = client.post(
        f"/api/creator-intelligence/projects/{sample_set.set_id}/generate-execution-pack",
        json={"topic_index": 0},
    )
    assert response.json()["error_code"] == ErrorCode.STRATEGY_PLAN_NOT_READY

    (output_dir / "creator_strategy_plan.json").write_text(json.dumps(_strategy_plan()), encoding="utf-8")
    response = client.post(
        f"/api/creator-intelligence/projects/{sample_set.set_id}/generate-execution-pack",
        json={"topic_index": 99},
    )
    assert response.json()["error_code"] == ErrorCode.EXECUTION_TOPIC_INVALID


def test_get_api_uses_not_ready_contract_before_generation() -> None:
    sample_set, _ = _write_upstream()

    response = client.get(f"/api/creator-intelligence/projects/{sample_set.set_id}/execution-pack")

    assert response.status_code == 400
    assert response.json()["error_code"] == ErrorCode.EXECUTION_PACK_NOT_READY


def test_project_id_alias_cannot_open_another_execution_pack() -> None:
    sample_set, _ = _write_upstream()
    generate_creator_execution_pack(
        sample_set.set_id,
        0,
        provider=FakeProvider([_execution_payload()]),
    )

    response = client.get(
        f"/api/creator-intelligence/projects/{sample_set.set_id}../execution-pack"
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == ErrorCode.EXECUTION_PACK_NOT_READY


def test_generate_get_and_regenerate_are_atomic_without_upstream_side_effects(monkeypatch) -> None:
    sample_set, output_dir = _write_upstream()
    upstream_names = ("samples.json", "creator_clone_result.json", "creator_strategy_plan.json")
    upstream_before = {name: (output_dir / name).read_bytes() for name in upstream_names}
    with SessionLocal() as session:
        jobs_before = session.query(Job).count()

    side_effect_calls: list[str] = []

    def forbidden(*args, **kwargs):
        side_effect_calls.append("called")
        raise AssertionError("Execution Pack must not invoke an upstream side effect")

    monkeypatch.setattr("app.services.profile_scan.scan_profile", forbidden)
    monkeypatch.setattr("app.services.downloader.download_candidate", forbidden)
    monkeypatch.setattr("app.services.asr.run_case_asr", forbidden)
    monkeypatch.setattr("app.services.ocr.run_case_ocr", forbidden)
    monkeypatch.setattr("app.services.creator_clone.distill_creator_clone", forbidden)

    first_provider = FakeProvider([_execution_payload()])
    monkeypatch.setattr(
        "app.services.creator_intelligence.execution_pack.get_llm_provider",
        lambda **kwargs: first_provider,
    )
    response = client.post(
        f"/api/creator-intelligence/projects/{sample_set.set_id}/generate-execution-pack",
        json={"topic_index": 0},
    )
    assert response.status_code == 200
    first_pack = response.json()["execution_pack"]
    assert response.headers["cache-control"] == "no-store"
    assert first_provider.calls == 1
    assert (output_dir / EXECUTION_PACK_FILENAME).is_file()

    get_response = client.get(f"/api/creator-intelligence/projects/{sample_set.set_id}/execution-pack")
    assert get_response.status_code == 200
    assert get_response.json()["execution_pack"] == first_pack
    assert get_response.headers["cache-control"] == "no-store"

    second_payload = _execution_payload()
    second_payload["publish_copy"] = "第二版发布正文，用于验证原子覆盖。"
    second_provider = FakeProvider([second_payload])
    monkeypatch.setattr(
        "app.services.creator_intelligence.execution_pack.get_llm_provider",
        lambda **kwargs: second_provider,
    )
    second_response = client.post(
        f"/api/creator-intelligence/projects/{sample_set.set_id}/generate-execution-pack",
        json={"topic_index": 0},
    )
    assert second_response.status_code == 200
    assert second_response.json()["execution_pack"]["publish_copy"].startswith("第二版")
    assert not list(output_dir.glob(f".{EXECUTION_PACK_FILENAME}.*.tmp"))
    assert {name: (output_dir / name).read_bytes() for name in upstream_names} == upstream_before
    assert side_effect_calls == []
    with SessionLocal() as session:
        assert session.query(Job).count() == jobs_before


def test_partial_evidence_allows_generation_with_lower_confidence() -> None:
    sample_set, _ = _write_upstream(partial=True)
    provider = FakeProvider([_execution_payload()])

    result = generate_creator_execution_pack(sample_set.set_id, 0, provider=provider)

    assert provider.calls == 1
    assert result["confidence"] == "medium"
    assert result["source"]["selected_count"] == 6
    assert result["source"]["evidence_ready_count"] == 5
    assert result["source"]["failed_evidence_count"] == 1
    assert any("富化失败" in warning for warning in result["warnings"])
    assert any("5/6" in warning for warning in result["warnings"])


def test_evidence_allowlist_matches_the_eight_samples_exposed_to_the_model() -> None:
    sample_set = _sample_set()
    for index in range(4, 10):
        sample_set.samples.append(
            CloneSample(
                sample_id=f"sample_{index}",
                title=f"代表样本 {index}",
                source_type="douyin",
                media_type="video",
                understanding_level="full",
                has_frames=True,
                enrichment_status="success",
                selected=True,
            )
        )
    sample_set.selected_sample_ids = [sample.sample_id for sample in sample_set.samples]
    save_sample_set(sample_set)
    output_dir = creator_clone_dir(sample_set.set_id)
    (output_dir / "creator_clone_result.json").write_text(json.dumps(_report()), encoding="utf-8")
    (output_dir / "creator_strategy_plan.json").write_text(json.dumps(_strategy_plan()), encoding="utf-8")
    payload = _execution_payload()
    payload["creative_basis"]["representative_samples"].append(
        {"sample_id": "sample_9", "reason": "未发送给模型的样本"}
    )
    payload["evidence_refs"].append(
        {"type": "sample", "sample_id": "sample_9", "reason": "未发送给模型的证据"}
    )

    result = generate_creator_execution_pack(
        sample_set.set_id,
        0,
        provider=FakeProvider([payload]),
    )

    assert "sample_9" not in json.dumps(result, ensure_ascii=False)
    assert any("无法验证的证据" in warning for warning in result["warnings"])


def test_low_quality_report_allows_generation_but_caps_confidence() -> None:
    sample_set, _ = _write_upstream(score=64)
    provider = FakeProvider([_execution_payload()])

    result = generate_creator_execution_pack(sample_set.set_id, 0, provider=provider)

    assert result["confidence"] == "low"
    assert result["source"]["report_quality_score"] == 64
    assert any("64/100" in warning for warning in result["warnings"])


@pytest.mark.parametrize(
    ("error_code", "status_code"),
    [
        (ErrorCode.LLM_AUTH_FAILED, 401),
        (ErrorCode.LLM_AUTH_FAILED, 403),
        (ErrorCode.LLM_RATE_LIMITED, 429),
        (ErrorCode.LLM_QUOTA_EXCEEDED, 429),
    ],
    ids=("http-401", "http-403", "http-429", "quota"),
)
def test_terminal_llm_errors_are_not_retried(error_code: str, status_code: int) -> None:
    sample_set, _ = _write_upstream()
    provider = FakeProvider([AppError(error_code, details={"status_code": status_code})])

    with pytest.raises(AppError) as captured:
        generate_creator_execution_pack(sample_set.set_id, 0, provider=provider)

    assert captured.value.code == error_code
    assert provider.calls == 1


@pytest.mark.parametrize(
    "first_outcome",
    [
        "not valid json",
        AppError(ErrorCode.LLM_UPSTREAM_UNAVAILABLE, "mock HTTP 503"),
    ],
)
def test_retryable_llm_failures_use_at_most_one_compact_retry(first_outcome: Any) -> None:
    sample_set, _ = _write_upstream()
    provider = FakeProvider([first_outcome, _execution_payload()])

    result = generate_creator_execution_pack(sample_set.set_id, 0, provider=provider)

    assert provider.calls == 2
    assert result["source"]["llm_attempts"] == 2
    assert result["source"]["llm_repaired"] is True
    assert "紧凑修复" in provider.prompts[1]


def test_structured_retry_is_rejected_with_59_seconds_remaining() -> None:
    clock = FakeClock()
    deadline = DistillDeadline.start(180, clock=clock)
    provider = ClockedProvider(
        [AppError(ErrorCode.LLM_UPSTREAM_UNAVAILABLE), {"ok": True}],
        clock=clock,
        first_attempt_seconds=121,
    )

    with pytest.raises(AppError) as captured:
        LLMExecutionEngine(provider, max_retries=2, deadline=deadline).execute_structured(
            "main prompt",
            validator=lambda payload: payload,
            repair_instruction="compact retry",
            retry_min_remaining_seconds=60,
        )

    assert captured.value.code == ErrorCode.LLM_GATEWAY_TIMEOUT
    assert captured.value.details["phase"] == "structured_execution_retry"
    assert provider.calls == 1


def test_structured_retry_is_allowed_with_61_seconds_remaining() -> None:
    clock = FakeClock()
    deadline = DistillDeadline.start(180, clock=clock)
    provider = ClockedProvider(
        [AppError(ErrorCode.LLM_UPSTREAM_UNAVAILABLE), {"ok": True}],
        clock=clock,
        first_attempt_seconds=119,
    )

    result = LLMExecutionEngine(provider, max_retries=2, deadline=deadline).execute_structured(
        "main prompt",
        validator=lambda payload: payload,
        repair_instruction="compact retry",
        retry_min_remaining_seconds=60,
    )

    assert result.payload == {"ok": True}
    assert result.attempts == 2
    assert provider.calls == 2


def test_execution_pack_uses_runtime_compact_retry_threshold(monkeypatch) -> None:
    sample_set, _ = _write_upstream()
    clock = FakeClock()
    deadline = DistillDeadline.start(180, clock=clock)
    provider = ClockedProvider(
        [AppError(ErrorCode.LLM_UPSTREAM_UNAVAILABLE), _execution_payload()],
        clock=clock,
        first_attempt_seconds=91,
    )

    class DeadlineFactory:
        @staticmethod
        def start(total_budget_seconds: float) -> DistillDeadline:
            assert total_budget_seconds == 180
            return deadline

    monkeypatch.setattr(execution_pack_module, "DistillDeadline", DeadlineFactory)
    monkeypatch.setattr(
        execution_pack_module,
        "effective_llm_settings",
        lambda: {
            "creator_distill_request_timeout_seconds": 180,
            "compact_retry_min_remaining_seconds": 90,
        },
    )

    with pytest.raises(AppError) as captured:
        generate_creator_execution_pack(sample_set.set_id, 0, provider=provider)

    assert captured.value.code == ErrorCode.LLM_GATEWAY_TIMEOUT
    assert provider.calls == 1


@pytest.mark.parametrize(
    ("runtime_timeout", "expected_timeout"),
    [(120, 120), (300, 180)],
)
def test_execution_pack_provider_timeout_respects_runtime_cap(
    monkeypatch,
    runtime_timeout: int,
    expected_timeout: int,
) -> None:
    sample_set, _ = _write_upstream()
    captured: dict[str, Any] = {}
    provider = FakeProvider([_execution_payload()])

    monkeypatch.setattr(
        execution_pack_module,
        "effective_llm_settings",
        lambda: {
            "creator_distill_request_timeout_seconds": runtime_timeout,
            "compact_retry_min_remaining_seconds": 60,
        },
    )

    def provider_factory(**kwargs):
        captured.update(kwargs)
        return provider

    monkeypatch.setattr(execution_pack_module, "get_llm_provider", provider_factory)

    result = generate_creator_execution_pack(sample_set.set_id, 0)

    assert result["source"]["llm_attempts"] == 1
    assert captured["timeout_seconds"] == expected_timeout
    assert captured["deadline"].total_budget_seconds == 180


def test_prompt_is_create_only_and_excludes_sensitive_upstream_data() -> None:
    sample_set = _sample_set()
    report = _report()
    plan = _strategy_plan()
    prompt = build_creator_execution_pack_prompt(
        sample_set=sample_set,
        report=report,
        strategy_plan=plan,
        selected_samples=sample_set.samples,
        selected_topic=_execution_payload()["topic"],
        topic_index=0,
    )

    assert "你不是重新分析账号" in prompt
    assert "不得发明 sample_id" in prompt
    assert "sample_1" in prompt
    assert "sessionid=must-not-leak" not in prompt
    assert "Bearer hidden" not in prompt
    assert "video.example.test" not in prompt
    assert "douyin.com/user" not in prompt


def test_api_and_persisted_pack_redact_sensitive_model_output(monkeypatch) -> None:
    sample_set, output_dir = _write_upstream()
    payload = _execution_payload()
    payload["publish_copy"] = "Cookie=session-secret Authorization: Bearer top-secret sk-1234567890abcdef"
    payload["titles"][0]["text"] = "打开 https://signed.example.test/video?token=secret"
    payload["warnings"] = ["本机文件 /Users/test/private/video.mp4 不可访问"]
    payload["unknown_raw_body"] = "raw upstream body should be ignored"
    provider = FakeProvider([payload])
    monkeypatch.setattr(
        "app.services.creator_intelligence.execution_pack.get_llm_provider",
        lambda **kwargs: provider,
    )

    response = client.post(
        f"/api/creator-intelligence/projects/{sample_set.set_id}/generate-execution-pack",
        json={"topic_index": 0},
    )
    assert response.status_code == 200
    response_text = json.dumps(response.json(), ensure_ascii=False).lower()
    file_text = (output_dir / EXECUTION_PACK_FILENAME).read_text(encoding="utf-8").lower()
    for serialized in (response_text, file_text):
        assert "session-secret" not in serialized
        assert "bearer top-secret" not in serialized
        assert "sk-1234567890abcdef" not in serialized
        assert "/users/test" not in serialized
        assert "signed.example.test" not in serialized
        assert "raw upstream body" not in serialized


def test_corrupt_persisted_pack_uses_not_ready_contract() -> None:
    sample_set, output_dir = _write_upstream()
    (output_dir / EXECUTION_PACK_FILENAME).write_text("{broken", encoding="utf-8")

    response = client.get(f"/api/creator-intelligence/projects/{sample_set.set_id}/execution-pack")

    assert response.status_code == 400
    assert response.json()["error_code"] == ErrorCode.EXECUTION_PACK_NOT_READY


def test_corrupt_strategy_context_does_not_escape_as_server_error() -> None:
    sample_set, output_dir = _write_upstream()
    generate_creator_execution_pack(
        sample_set.set_id,
        0,
        provider=FakeProvider([_execution_payload()]),
    )
    strategy = _strategy_plan()
    strategy["next_topics"][0] = {}
    (output_dir / "creator_strategy_plan.json").write_text(
        json.dumps(strategy, ensure_ascii=False),
        encoding="utf-8",
    )

    response = client.get(f"/api/creator-intelligence/projects/{sample_set.set_id}/execution-pack")

    assert response.status_code == 400
    assert response.json()["error_code"] == ErrorCode.EXECUTION_PACK_NOT_READY
