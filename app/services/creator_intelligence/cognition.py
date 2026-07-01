from __future__ import annotations

from collections import Counter
from typing import Any

from app.services.creator_intelligence.models import BehaviorRepresentation, CreatorProject, CreatorSample


def build_behavior_representation(project: CreatorProject) -> BehaviorRepresentation:
    selected = project.selected_samples or project.samples
    return BehaviorRepresentation(
        project_id=project.project_id,
        profile=project.profile,
        sample_count=len(project.samples),
        selected_count=len(selected),
        evidence_matrix=evidence_matrix(selected),
        performance_segments=performance_segments(selected),
        media_mix=media_mix(selected),
        constraints=tuple(evidence_constraints(selected)),
    )


def media_mix(samples: tuple[CreatorSample, ...]) -> dict[str, int]:
    counts = Counter(sample.media_kind.value for sample in samples)
    return dict(sorted(counts.items()))


def evidence_matrix(samples: tuple[CreatorSample, ...]) -> dict[str, Any]:
    total = len(samples)
    matrix = {
        "selected_count": total,
        "with_case": sum(1 for sample in samples if sample.case_id),
        "with_video": sum(1 for sample in samples if sample.evidence.has_video),
        "with_keyframes": sum(1 for sample in samples if sample.evidence.has_frames),
        "with_asr_text": sum(1 for sample in samples if sample.evidence.has_asr),
        "with_ocr_text": sum(1 for sample in samples if sample.evidence.has_ocr),
        "with_comments": sum(1 for sample in samples if sample.evidence.has_comments),
        "with_ai_report": sum(1 for sample in samples if sample.evidence.analysis_status == "success"),
        "metadata_only": sum(1 for sample in samples if sample.evidence.level.value == "metadata_only"),
        "partial": sum(1 for sample in samples if sample.evidence.level.value == "partial"),
        "full": sum(1 for sample in samples if sample.evidence.level.value == "full"),
    }
    matrix["coverage"] = {
        key: round(value / total, 3) if total else 0
        for key, value in matrix.items()
        if key.startswith("with_")
    }
    return matrix


def performance_segments(samples: tuple[CreatorSample, ...], limit: int = 5) -> dict[str, list[dict[str, Any]]]:
    rows = list(samples)
    by_engagement = sorted(rows, key=lambda sample: sample.metrics.engagement_score)
    weak = [sample for sample in by_engagement if sample.metrics.engagement_score <= max(1, by_engagement[0].metrics.engagement_score if by_engagement else 1)]
    return {
        "highest_like_samples": [_segment_payload(sample, "like_count") for sample in _top(rows, "like_count", limit)],
        "highest_comment_samples": [_segment_payload(sample, "comment_count") for sample in _top(rows, "comment_count", limit)],
        "highest_share_samples": [_segment_payload(sample, "share_count") for sample in _top(rows, "share_count", limit)],
        "highest_collect_samples": [_segment_payload(sample, "collect_count") for sample in _top(rows, "collect_count", limit)],
        "weak_or_reference_samples": [_segment_payload(sample, "engagement_score") for sample in weak[:limit]],
    }


def evidence_constraints(samples: tuple[CreatorSample, ...]) -> list[str]:
    matrix = evidence_matrix(samples)
    total = matrix["selected_count"]
    if not total:
        return ["No selected samples; creator behavior cannot be modeled."]
    constraints: list[str] = []
    if matrix["metadata_only"] >= max(1, total // 2):
        constraints.append("Most samples are metadata-only; visual rhythm, spoken hooks, and comment motives are low-confidence.")
    if matrix["with_keyframes"] < max(1, total // 2):
        constraints.append("Keyframe coverage is incomplete; visual style conclusions need caution.")
    if matrix["with_asr_text"] == 0:
        constraints.append("No ASR evidence; spoken script and voice rhythm cannot be asserted.")
    if matrix["with_ocr_text"] == 0:
        constraints.append("No OCR evidence; on-screen subtitle and cover text patterns cannot be asserted.")
    if matrix["with_comments"] == 0:
        constraints.append("No comment evidence; audience motives are hypotheses.")
    return constraints


def _top(samples: list[CreatorSample], key: str, limit: int) -> list[CreatorSample]:
    return sorted(samples, key=lambda sample: _metric(sample, key), reverse=True)[:limit]


def _metric(sample: CreatorSample, key: str) -> int:
    if key == "engagement_score":
        return sample.metrics.engagement_score
    return int(getattr(sample.metrics, key, 0) or 0)


def _segment_payload(sample: CreatorSample, metric: str) -> dict[str, Any]:
    return {
        "sample_id": sample.sample_id,
        "platform_item_id": sample.platform_item_id,
        "title": sample.title,
        "media_kind": sample.media_kind.value,
        "metric": metric,
        "metric_value": _metric(sample, metric),
        "metrics": sample.metrics.to_dict(),
        "evidence_level": sample.evidence.level.value,
    }
