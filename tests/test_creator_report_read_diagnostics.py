from copy import deepcopy

import pytest

from app.routes.jobs import _distill_phase_payload
from app.services.creator_clone import (
    CloneSample,
    CloneSampleSet,
    _report_generation_diagnostics,
    _report_quality_label,
)


@pytest.mark.parametrize(
    ("score", "label"),
    [
        (None, "结构待评估"),
        ("invalid", "结构待评估"),
        (0, "结构明显缺失"),
        (49.9, "结构明显缺失"),
        (50, "结构待补全"),
        (69.9, "结构待补全"),
        (70, "结构基本完整"),
        (84.9, "结构基本完整"),
        (85, "结构较完整"),
        (100, "结构较完整"),
    ],
)
def test_report_quality_labels_describe_structure(score, label):
    assert _report_quality_label(score) == label


@pytest.mark.parametrize(
    ("quality", "score", "label"),
    [
        ({"quality_score": 95, "score": 20}, 95, "结构较完整"),
        ({"score": 72.5}, 72.5, "结构基本完整"),
        ({"quality_score": 0, "score": 95}, 0, "结构明显缺失"),
        ({}, 0, "结构待评估"),
    ],
)
def test_report_diagnostics_keep_score_contract_and_evidence_gaps(quality, score, label):
    sample = CloneSample(sample_id="metadata_sample", title="Metadata only")
    sample_set = CloneSampleSet(set_id="isolated", title="Test", samples=[sample])
    result = {
        "summary": "A locally assembled report",
        "batch_distill": {
            "batch_count": 1,
            "final_reduce_recovery": "local_fallback",
            "final_reduce_error_code": "LLM_GATEWAY_TIMEOUT",
        },
    }
    original = deepcopy((result, quality))

    diagnostics = _report_generation_diagnostics(result, [sample], sample_set, quality)

    assert diagnostics["quality_score"] == score
    assert diagnostics["quality_label"] == label
    assert diagnostics["is_fallback"] is True
    assert diagnostics["source_label"] == "本地批次汇总 / 降级"
    assert "LLM_GATEWAY_TIMEOUT" in diagnostics["fallback_reason"]
    assert diagnostics["understanding"]["metadata_only"] == 1
    assert diagnostics["missing_evidence_labels"] == ["视频", "关键帧", "ASR", "OCR", "评论"]
    assert (result, quality) == original


@pytest.mark.parametrize("current_phase", ["planning", "distill_prepare", "final_reduce", "parse_persist", "local_fallback", "complete"])
def test_stage_three_of_one_batch_is_not_a_batch_or_retry_index(current_phase):
    phase = {
        "current_phase": current_phase,
        "phase_index": 3,
        "phase_count": 3,
        "status": "success",
        "attempt_index": 2,
        "attempt_count": 2,
        "http_attempt_index": 1,
        "http_attempt_count": 1,
        "timeout_seconds": 180,
        "elapsed_seconds": 42,
        "remaining_seconds": 138,
        "retryable": False,
    }
    plan = {"batch_count": 1}
    original = deepcopy((phase, plan))

    payload = _distill_phase_payload(phase, execution_plan=plan)

    assert payload["batch_index"] is None
    assert payload["batch_count"] == 1
    for key, value in phase.items():
        assert payload[key] == value
    assert (phase, plan) == original


@pytest.mark.parametrize(("index", "count"), [(1, 1), (3, 4)])
def test_batch_reduce_exposes_actual_batch_ordinal(index, count):
    payload = _distill_phase_payload(
        {
            "current_phase": "batch_reduce",
            "phase_index": index,
            "phase_count": count,
            "batch_count": count,
            "batch_id": f"batch_{index:03d}",
            "attempt_index": 2,
            "execution_plan": {"batch_count": 1},
        },
    )

    assert payload["batch_index"] == index
    assert payload["batch_count"] == count
    assert payload["phase_index"] == index
    assert payload["attempt_index"] == 2


@pytest.mark.parametrize("index", [None, 0, -1, 3, "1", True])
def test_unreliable_batch_ordinal_is_not_invented_or_clamped(index):
    payload = _distill_phase_payload(
        {"current_phase": "batch_reduce", "phase_index": index},
        execution_plan={"batch_count": 1},
    )

    assert payload["batch_index"] is None
    assert payload["phase_index"] == index
    assert payload["batch_count"] == 1
