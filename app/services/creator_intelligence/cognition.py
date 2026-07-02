from __future__ import annotations

from collections import Counter
from typing import Any

from app.services.creator_intelligence.models import BehaviorRepresentation, CreatorProject, CreatorSample


def build_behavior_representation(project: CreatorProject) -> BehaviorRepresentation:
    selected = project.selected_samples or project.samples
    structures = content_structures(selected)
    return BehaviorRepresentation(
        project_id=project.project_id,
        profile=project.profile,
        sample_count=len(project.samples),
        selected_count=len(selected),
        evidence_matrix=evidence_matrix(selected),
        performance_segments=performance_segments(selected),
        media_mix=media_mix(selected),
        behavior_patterns=behavior_patterns(selected),
        content_structures=structures,
        structure_patterns=structures,
        hook_patterns=hook_patterns(selected),
        risk_patterns=risk_patterns(selected),
        evolution_signals=evolution_signals(project, selected),
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


def behavior_patterns(samples: tuple[CreatorSample, ...]) -> dict[str, Any]:
    return {
        "dominant_media": _dominant_media(samples),
        "metric_bias": _metric_bias(samples),
        "selection_basis": "selected_samples" if samples else "empty",
        "evidence_depth": _evidence_depth(samples),
    }


def content_structures(samples: tuple[CreatorSample, ...]) -> dict[str, Any]:
    title_tokens = _title_tokens(samples)
    return {
        "title_keywords": title_tokens[:20],
        "media_mix": media_mix(samples),
        "has_video_ratio": _ratio(sum(1 for sample in samples if sample.evidence.has_video), len(samples)),
        "has_case_ratio": _ratio(sum(1 for sample in samples if sample.case_id), len(samples)),
    }


def hook_patterns(samples: tuple[CreatorSample, ...]) -> dict[str, Any]:
    top_like = _top(list(samples), "like_count", 3)
    top_comment = _top(list(samples), "comment_count", 3)
    return {
        "high_like_titles": [sample.title for sample in top_like if sample.title],
        "high_comment_titles": [sample.title for sample in top_comment if sample.title],
        "hook_evidence": "frames_or_text" if any(sample.evidence.has_frames or sample.evidence.has_ocr for sample in samples) else "metadata_only",
    }


def risk_patterns(samples: tuple[CreatorSample, ...]) -> dict[str, Any]:
    metadata_only = sum(1 for sample in samples if sample.evidence.level.value == "metadata_only")
    unsupported = sum(1 for sample in samples if sample.media_kind.value in {"image", "text", "unknown"})
    return {
        "metadata_only_count": metadata_only,
        "unsupported_or_static_count": unsupported,
        "low_confidence": metadata_only >= max(1, len(samples) // 2) if samples else True,
    }


def evolution_signals(project: CreatorProject, samples: tuple[CreatorSample, ...]) -> dict[str, Any]:
    """Local evolution signals before the memory graph adds historical context."""
    selected_ids = {sample.sample_id for sample in samples}
    project_sample_ids = {sample.sample_id for sample in project.samples}
    selected_ratio = _ratio(len(selected_ids), len(project_sample_ids))
    titles = [sample.title for sample in samples if sample.title]
    return {
        "creator_id": project.profile.creator_id,
        "project_id": project.project_id,
        "selected_ratio": selected_ratio,
        "sample_count": len(project.samples),
        "selected_count": len(samples),
        "has_history": False,
        "new_sample_ids": sorted(selected_ids),
        "repeated_title_tokens": _repeated_tokens(titles),
        "evidence_depth": _evidence_depth(samples),
    }


def _top(samples: list[CreatorSample], key: str, limit: int) -> list[CreatorSample]:
    return sorted(samples, key=lambda sample: _metric(sample, key), reverse=True)[:limit]


def _metric(sample: CreatorSample, key: str) -> int:
    if key == "engagement_score":
        return sample.metrics.engagement_score
    return int(getattr(sample.metrics, key, 0) or 0)


def _dominant_media(samples: tuple[CreatorSample, ...]) -> str:
    counts = media_mix(samples)
    if not counts:
        return "unknown"
    return max(counts.items(), key=lambda item: item[1])[0]


def _metric_bias(samples: tuple[CreatorSample, ...]) -> str:
    totals = {
        "like": sum(sample.metrics.like_count for sample in samples),
        "comment": sum(sample.metrics.comment_count for sample in samples),
        "share": sum(sample.metrics.share_count for sample in samples),
        "collect": sum(sample.metrics.collect_count for sample in samples),
    }
    if not any(totals.values()):
        return "unknown"
    return max(totals.items(), key=lambda item: item[1])[0]


def _evidence_depth(samples: tuple[CreatorSample, ...]) -> str:
    if not samples:
        return "empty"
    full_or_partial = sum(1 for sample in samples if sample.evidence.level.value in {"full", "partial"})
    if full_or_partial == len(samples):
        return "rich"
    if full_or_partial:
        return "mixed"
    return "metadata_only"


def _title_tokens(samples: tuple[CreatorSample, ...]) -> list[str]:
    tokens: list[str] = []
    for sample in samples:
        for token in sample.title.replace("#", " ").replace("/", " ").split():
            token = token.strip("，。！？,.!?:：;；[]（）()")
            if len(token) >= 2 and token not in tokens:
                tokens.append(token)
    return tokens


def _repeated_tokens(titles: list[str], limit: int = 10) -> list[str]:
    counter: Counter[str] = Counter()
    for title in titles:
        for token in title.replace("#", " ").replace("/", " ").split():
            token = token.strip("，。！？,.!?:：;；[]（）()")
            if len(token) >= 2:
                counter[token] += 1
    return [token for token, count in counter.most_common(limit) if count >= 2]


def _ratio(value: int, total: int) -> float:
    return round(value / total, 3) if total else 0.0


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
