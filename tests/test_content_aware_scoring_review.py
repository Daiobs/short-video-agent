"""Applicable quality scores and retained diagnostics, using synthetic inputs only."""
from copy import deepcopy

import pytest

from app.services import auto_analyzer as auto
from app.services.content_analysis import normalize_focused_analysis


@pytest.fixture
def report():
    return {
        "analysis_focus": {"version": 1, "primary": "generic"},
        "request_evidence": {"visual_available": False, "valid_refs": ["metadata"],
                             "asr": {"submitted": False}, "ocr": {"submitted": False}},
        "summary": "The result is explained before the steps so the procedure is easy to follow.",
        "hook_analysis": {"first_impression": "The opening introduces a concrete problem.",
                          "why_stop_scrolling": "The promised result gives a reason to follow the steps."},
        "replication": {"remake_angle": "Explain a different procedure with the same result-first order.",
                        "copyable_points": ["Introduce a concrete problem before the steps."],
                        "avoid_copying": ["Use your own examples instead of copying the original wording."]},
        "publish_package": {"titles": ["A practical procedure explained step by step"],
                            "caption": "Start with the result, then work through each necessary step."},
        "focused_analysis": [{"observation": "The title promises a concrete result.",
                              "interpretation": "The promise helps organize the explanation.",
                              "transfer": "State the result before listing the steps.",
                              "evidence": ["metadata"], "uncertainty": ""}],
        "evidence_summary": {},
        "confidence": 0.8,
        "source": {"duration": 10},
    }


def checks_by_id(review):
    return {check["id"]: check for check in review["checks"]}


@pytest.fixture
def complete_visual_report(report):
    report.update({
        "analysis_focus": {"version": 1, "primary": "beauty_cos"},
        "summary": "人物近景和姿态变化形成视觉吸引，可迁移的是先展示妆造再改变姿态的顺序。",
        "visual_analysis": {"scene": "室内暖色布景，背景留白突出人物",
                            "subject": "人物近景居中，服化妆造是第一眼亮点",
                            "movement_rhythm": "抬手改变姿态，镜头保持固定近景"},
        "hook_analysis": {"first_impression": "人物脸和妆造在开头近景出现",
                          "why_stop_scrolling": "服化和姿态有明确第一眼吸引点"},
        "evidence_summary": {"visual_input_mode": "multi_image", "visual_evidence": [
            {"claim": "人物近景和姿态变化提供视觉吸引",
             "evidence": "关键帧显示人物近景居中，抬手改变姿态，暖色布景背景留白",
             "confidence": "high"}]},
        "replication": {"remake_angle": "保留人物近景和姿态变化的视觉结构",
                        "copyable_points": ["先展示人物近景妆造，再抬手改变姿态"],
                        "avoid_copying": ["不要照搬原视频妆造和姿势，保留自己的角色设定"]},
        "publish_package": {"titles": ["近景妆造与抬手姿态的两种表达"],
                            "caption": "用自己的角色设定尝试近景和姿态变化。"},
    })
    report["request_evidence"].update(visual_available=True, valid_refs=["metadata", "frame_001.jpg"])
    report["focused_analysis"][0]["evidence"] = ["frame_001.jpg"]
    return report


def test_complete_visual_a_is_100_strong_without_text_or_comments(complete_visual_report):
    review = auto._analysis_quality_review(complete_visual_report)
    checks = checks_by_id(review)
    assert not review["gaps"], review["gaps"]
    assert all(check["passed"] for check in review["checks"])
    assert checks["visual"]["weight"] == 15
    for key in ("copy_speech_text", "audience"):
        assert checks[key]["applicable"] is False
        assert checks[key]["weight"] == 0
    assert sum(check["weight"] for check in review["checks"]) == 75
    assert review["score"] == review["max_score"] == 100
    assert review["level"] == "strong"
    assert "适用项结构与完成度" in review["summary"]
    assert "不代表事实准确率" in review["summary"]


def test_all_applicable_d_is_100_strong(complete_visual_report):
    report = complete_visual_report
    report["request_evidence"]["asr"]["submitted"] = True
    report["request_evidence"]["valid_refs"] += ["asr", "comments"]
    report["evidence_summary"].update({
        "asr_evidence": [{"claim": "开头口播引入姿态步骤", "evidence": "先展示妆造，再抬手改变姿态。", "confidence": "high"}],
        "comment_evidence": [{"claim": "评论询问妆造线索", "evidence": "观众评论询问同款妆造的实现步骤。", "confidence": "high"}],
    })
    report["speech_analysis"] = {"has_speech": True, "opening_line": "先展示妆造，再抬手改变姿态。"}
    report["comment_insights"] = {"audience_needs": ["求同款妆造的实现步骤"],
                                  "comment_triggers": ["询问人物近景中妆造的实现步骤"]}
    review = auto._analysis_quality_review(report)
    assert not review["gaps"], review["gaps"]
    assert all(check["passed"] for check in review["checks"])
    assert sum(check["weight"] for check in review["checks"]) == 100
    assert review["score"] == review["max_score"] == 100
    assert review["level"] == "strong"


@pytest.mark.parametrize("diagnostic", ["submitted_claim_support", "focused_evidence_refs",
    "category_alignment", "model_confidence", "evidence_confidence", "time_bounds"])
def test_real_full_score_with_zero_weight_gap_is_not_strong(complete_visual_report, diagnostic):
    report = complete_visual_report
    if diagnostic == "submitted_claim_support":
        report["request_evidence"]["visual_available"] = False
        report["speech_analysis"] = {"has_speech": True, "opening_line": "An unsupported spoken claim."}
    elif diagnostic == "focused_evidence_refs":
        report["focused_analysis"][0]["evidence"].append("missing.jpg")
    elif diagnostic == "category_alignment":
        report["focused_analysis"] = []
    elif diagnostic == "model_confidence":
        report["confidence"] = None
    elif diagnostic == "evidence_confidence":
        report["evidence_summary"]["visual_evidence"][0]["confidence"] = "low"
    else:
        report["timeline"] = [{"time": "20s", "visual": "An out-of-bounds observation."}]
    review = auto._analysis_quality_review(report)
    assert review["score"] == 100
    assert diagnostic in {gap["id"] for gap in review["gaps"]}
    assert review["level"] != "strong"
    assert review["next_actions"]
    assert "仍需" in review["summary"]


@pytest.mark.parametrize("primary,visual_available", [
    ("generic", False), ("tutorial", False), ("beauty_cos", True), ("photo_beauty", True),
])
def test_score_uses_applicable_weight(report, primary, visual_available):
    report["analysis_focus"]["primary"] = primary
    report["request_evidence"]["visual_available"] = visual_available
    review = auto._analysis_quality_review(report)
    applicable = [c for c in review["checks"] if c.get("applicable", True) and c["weight"] > 0]
    total = sum(c["weight"] for c in applicable)
    earned = sum(c["weight"] for c in applicable if c["passed"])
    assert 0 < total < 100
    assert review["score"] == round(100 * earned / total)
    assert review["max_score"] == 100
    assert 0 <= review["score"] <= 100


@pytest.mark.parametrize("checks,expected", [
    ([], 0),
    ([{"weight": 0, "passed": True}], 0),
    ([{"weight": 0, "passed": False}], 0),
    ([{"weight": 15, "passed": True, "applicable": False}], 0),
    ([{"weight": 10, "passed": True}, {"weight": 15, "passed": True}], 100),
    ([{"weight": 10, "passed": True}, {"weight": 15, "passed": False}], 40),
    ([{"weight": 10, "passed": False}, {"weight": 15, "passed": False}], 0),
    ([{"weight": 10, "passed": True}, {"weight": 15, "passed": False, "applicable": False}], 100),
])
def test_applicable_score_boundaries(checks, expected):
    assert auto._applicable_quality_score(checks) == expected


@pytest.mark.parametrize("failed", [False, True])
def test_full_applicable_score_does_not_hide_zero_weight_failure(report, monkeypatch, failed):
    checks = [{"id": "summary", "weight": 10, "passed": True, "action": "summary"},
              {"id": "diagnostic", "weight": 0, "passed": not failed, "action": "review"}]
    monkeypatch.setattr(auto, "_focused_quality_checks", lambda *_: checks)
    review = auto._analysis_quality_review(report)
    assert review["score"] == review["max_score"] == 100
    assert (review["level"] == "strong") is (not failed)
    assert review["gaps"] == ([checks[1]] if failed else [])
    assert review["next_actions"] == (["review"] if failed else [])


def test_zero_denominator_is_weak(report, monkeypatch):
    monkeypatch.setattr(auto, "_focused_quality_checks", lambda *_: [])
    review = auto._analysis_quality_review(report)
    assert review["score"] == 0
    assert review["max_score"] == 100
    assert review["level"] == "weak"


@pytest.mark.parametrize("focus", [None, {}, {"primary": "tutorial"}, {"version": 0}, {"version": 2}])
def test_legacy_scores_and_checks_unchanged(report, focus):
    report.pop("analysis_focus")
    baseline = auto._analysis_quality_review(report)
    if focus is not None:
        report["analysis_focus"] = focus
    review = auto._analysis_quality_review(report)
    assert review == baseline
    assert review["score"] == sum(c["weight"] for c in review["checks"] if c["passed"])
    assert {"visual_input", "content_ratio_balance", "evidence_gaps"} <= checks_by_id(review).keys()


@pytest.mark.parametrize("field,value,diagnostic", [
    ("visual_analysis", {"subject": "A person wearing red stands in the center."}, "submitted_claim_support"),
    ("speech_analysis", {"has_speech": True, "opening_line": "Here is the first step."}, "submitted_claim_support"),
    ("summary", "", "summary"),
    ("hook_analysis", {}, "hook"),
    ("replication", {}, "replication"),
    ("focused_analysis", [], "category_alignment"),
    ("confidence", None, "model_confidence"),
    ("timeline", [{"time": "20s", "description": "Outside the original duration."}], "time_bounds"),
    ("evidence_summary", {"visual_evidence": [{"claim": "A person stands in the center.",
                                               "evidence": "A single frame shows the person.",
                                               "confidence": "low"}]}, "evidence_confidence"),
])
def test_diagnostics_survive_normalization(report, field, value, diagnostic):
    report[field] = value
    review = auto._analysis_quality_review(report)
    assert not checks_by_id(review)[diagnostic]["passed"]
    assert diagnostic in {gap["id"] for gap in review["gaps"]}
    assert review["level"] != "strong"


@pytest.mark.parametrize("value,valid", [(0, True), (0.2, True), (1, True),
    (True, False), (None, False), (-0.1, False), (1.1, False), (float("nan"), False), (float("inf"), False)])
def test_confidence_contract(report, value, valid):
    report["confidence"] = value
    assert checks_by_id(auto._analysis_quality_review(report))["model_confidence"]["passed"] is valid


@pytest.mark.parametrize("normalized", [False, True])
def test_illegal_references_remain_review_gaps(report, normalized):
    report["focused_analysis"][0]["evidence"].append("frame_not_submitted.jpg")
    if normalized:
        report["focused_analysis"] = normalize_focused_analysis(
            report["focused_analysis"], report["request_evidence"]["valid_refs"])
    review = auto._analysis_quality_review(report)
    check = checks_by_id(review)["focused_evidence_refs"]
    assert check["weight"] == 0
    assert not check["passed"] and check["details"]
    assert check in review["gaps"]
    assert review["level"] != "strong"


def test_valid_references_and_explicit_uncertainty_are_allowed(report):
    report["focused_analysis"].append({**deepcopy(report["focused_analysis"][0]),
                                       "evidence": [], "uncertainty": "Only the title is available."})
    before = deepcopy(report)
    checks = checks_by_id(auto._analysis_quality_review(report))
    assert checks["focused_evidence_refs"]["passed"]
    assert checks["category_alignment"]["passed"]
    assert report == before
