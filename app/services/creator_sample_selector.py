from __future__ import annotations

import math
import re
import unicodedata
from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from statistics import median
from typing import Any


ALGORITHM_VERSION = "representative-v1"
DEFAULT_TARGET_COUNT = 6
MIN_TARGET_COUNT = 3
MAX_TARGET_COUNT = 10
MAX_INPUT_COUNT = 200


class RepresentativeRole(str, Enum):
    BREAKOUT_HIT = "BREAKOUT_HIT"
    COMMENT_MAGNET = "COMMENT_MAGNET"
    SAVE_SHARE_VALUE = "SAVE_SHARE_VALUE"
    RECENT_WINNER = "RECENT_WINNER"
    DIVERSITY_ANCHOR = "DIVERSITY_ANCHOR"
    BASELINE_TYPICAL = "BASELINE_TYPICAL"


ROLE_ORDER = tuple(RepresentativeRole)
ROLE_INDEX = {role: index for index, role in enumerate(ROLE_ORDER)}
METRIC_WEIGHTS = {
    "like_count": 0.40,
    "comment_count": 0.20,
    "collect_count": 0.20,
    "share_count": 0.20,
}
METRIC_PERCENTILE_KEYS = {
    "like_count": "like_percentile",
    "comment_count": "comment_percentile",
    "share_count": "share_percentile",
    "collect_count": "collect_percentile",
}
SAFE_SAMPLE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,160}$")
ASCII_TOKEN_RE = re.compile(r"[a-z0-9]+")
CJK_RUN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")


class RepresentativeSampleSelectorError(ValueError):
    pass


@dataclass(frozen=True)
class RepresentativeSampleRecommendation:
    sample_id: str
    rank: int
    score: int
    primary_role: str
    roles: tuple[str, ...]
    reasons: tuple[str, ...]
    metrics: dict[str, float | None]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "rank": self.rank,
            "score": self.score,
            "primary_role": self.primary_role,
            "roles": list(self.roles),
            "reasons": list(self.reasons),
            "metrics": dict(self.metrics),
        }


@dataclass(frozen=True)
class RepresentativeSampleSelection:
    target_count: int
    input_count: int
    available_count: int
    recommendations: tuple[RepresentativeSampleRecommendation, ...]
    coverage: dict[str, bool]
    warnings: tuple[str, ...] = ()
    algorithm_version: str = ALGORITHM_VERSION

    @property
    def recommended_count(self) -> int:
        return len(self.recommendations)

    @property
    def recommended_sample_ids(self) -> tuple[str, ...]:
        return tuple(item.sample_id for item in self.recommendations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_count": self.target_count,
            "input_count": self.input_count,
            "available_count": self.available_count,
            "recommended_count": self.recommended_count,
            "algorithm_version": self.algorithm_version,
            "recommendations": [item.to_dict() for item in self.recommendations],
            "recommended_sample_ids": list(self.recommended_sample_ids),
            "coverage": dict(self.coverage),
            "warnings": list(self.warnings),
        }


@dataclass
class _SampleRecord:
    sample_id: str
    title: str
    description: str
    media_type: str
    duration_seconds: float | None
    content_category: str
    tags: tuple[str, ...]
    created_timestamp: float | None
    metrics: dict[str, float | None]
    fingerprint: frozenset[str] = field(default_factory=frozenset)
    percentiles: dict[str, float | None] = field(default_factory=dict)
    relative_strengths: dict[str, float | None] = field(default_factory=dict)
    performance_score: float | None = None
    comment_intensity_percentile: float | None = None
    typicality_score: float = 0.0

    @property
    def information_score(self) -> float:
        meaningful = [token for token in self.fingerprint if not token.endswith(":unknown")]
        return min(1.0, len(meaningful) / 8.0)


def recommend_representative_samples(
    samples: Iterable[Any],
    target_count: int = DEFAULT_TARGET_COUNT,
) -> RepresentativeSampleSelection:
    """Recommend a bounded, deterministic sample set without external side effects."""

    target = _validated_target_count(target_count)
    raw_samples = list(samples)
    if len(raw_samples) > MAX_INPUT_COUNT:
        raise RepresentativeSampleSelectorError(f"素材数量不能超过 {MAX_INPUT_COUNT} 条。")

    warnings: list[str] = []
    records: list[_SampleRecord] = []
    seen_ids: set[str] = set()
    invalid_count = 0
    duplicate_count = 0
    for raw in raw_samples:
        record = _record_from_sample(raw)
        if record is None:
            invalid_count += 1
            continue
        if record.sample_id in seen_ids:
            duplicate_count += 1
            continue
        seen_ids.add(record.sample_id)
        records.append(record)
    if invalid_count:
        warnings.append(f"已忽略 {invalid_count} 条缺少安全 sample_id 的记录。")
    if duplicate_count:
        warnings.append(f"已忽略 {duplicate_count} 条重复 sample_id。")

    coverage = {role.value: False for role in ROLE_ORDER}
    if not records:
        return RepresentativeSampleSelection(
            target_count=target,
            input_count=len(raw_samples),
            available_count=0,
            recommendations=(),
            coverage=coverage,
            warnings=tuple(warnings + ["没有可用于推荐的安全样本记录。"]),
        )

    _prepare_record_scores(records, warnings)
    desired_count = min(target, len(records))
    role_scores = _build_role_scores(records, warnings)
    selected_ids: list[str] = []
    assignments: dict[str, list[RepresentativeRole]] = {}
    selected_role_scores: dict[str, dict[RepresentativeRole, float]] = {}

    for role in ROLE_ORDER:
        if len(selected_ids) >= desired_count:
            break
        scores = role_scores.get(role) or {}
        if role == RepresentativeRole.DIVERSITY_ANCHOR:
            scores = _diversity_scores(records, selected_ids)
            role_scores[role] = scores
        candidate = _best_candidate(records, scores, excluded=set(selected_ids))
        if candidate is None:
            continue
        selected_ids.append(candidate.sample_id)
        assignments[candidate.sample_id] = [role]
        selected_role_scores[candidate.sample_id] = {role: scores[candidate.sample_id]}

    while len(selected_ids) < desired_count:
        remaining = [record for record in records if record.sample_id not in set(selected_ids)]
        if not remaining:
            break
        diversity = _diversity_scores(records, selected_ids)
        best_record: _SampleRecord | None = None
        best_role = RepresentativeRole.BASELINE_TYPICAL
        best_score = -1.0
        for record in remaining:
            candidate_scores = {
                role: scores.get(record.sample_id)
                for role, scores in role_scores.items()
                if scores.get(record.sample_id) is not None
            }
            if diversity.get(record.sample_id) is not None:
                candidate_scores[RepresentativeRole.DIVERSITY_ANCHOR] = diversity[record.sample_id]
            if candidate_scores:
                role, score = sorted(
                    candidate_scores.items(),
                    key=lambda item: (-item[1], ROLE_INDEX[item[0]]),
                )[0]
            else:
                role, score = RepresentativeRole.BASELINE_TYPICAL, 0.0
            composite = min(1.0, score * 0.8 + (record.performance_score or 0.0) * 0.1 + record.information_score * 0.1)
            if _record_is_better(record, composite, best_record, best_score):
                best_record = record
                best_role = role
                best_score = composite
        if best_record is None:
            break
        selected_ids.append(best_record.sample_id)
        assignments[best_record.sample_id] = [best_role]
        selected_role_scores[best_record.sample_id] = {best_role: max(0.0, best_score)}

    selected_records = [record for record in records if record.sample_id in set(selected_ids)]
    final_diversity_scores = _diversity_scores(records, selected_ids, compare_with_other_selected=True)
    role_scores[RepresentativeRole.DIVERSITY_ANCHOR] = final_diversity_scores

    # A selected work can carry a secondary role when the target is smaller than
    # the available role set or a role has no sensible unused candidate.
    for role in ROLE_ORDER:
        scores = role_scores.get(role) or {}
        if not scores or any(role in roles for roles in assignments.values()):
            continue
        candidate = _best_candidate(selected_records, scores, excluded=set())
        if candidate is None:
            continue
        assignments.setdefault(candidate.sample_id, []).append(role)
        selected_role_scores.setdefault(candidate.sample_id, {})[role] = scores[candidate.sample_id]

    for roles in assignments.values():
        roles.sort(key=lambda role: ROLE_INDEX[role])
        for role in roles:
            coverage[role.value] = True

    by_id = {record.sample_id: record for record in records}
    prepared: list[tuple[_SampleRecord, list[RepresentativeRole], int, list[str]]] = []
    for sample_id in selected_ids:
        record = by_id[sample_id]
        roles = assignments.get(sample_id) or [RepresentativeRole.BASELINE_TYPICAL]
        scores = selected_role_scores.get(sample_id) or {}
        primary_role = max(roles, key=lambda role: (scores.get(role, 0.0), -ROLE_INDEX[role]))
        representative_score = int(round(max(0.0, min(1.0, scores.get(primary_role, 0.0))) * 100))
        reasons = _recommendation_reasons(record, roles, role_scores, records)
        prepared.append((record, [primary_role, *[role for role in roles if role != primary_role]], representative_score, reasons))

    prepared.sort(
        key=lambda item: (
            -item[2],
            -(item[0].created_timestamp or 0.0),
            item[0].sample_id,
        )
    )
    recommendations = tuple(
        RepresentativeSampleRecommendation(
            sample_id=record.sample_id,
            rank=index,
            score=score,
            primary_role=roles[0].value,
            roles=tuple(role.value for role in roles),
            reasons=tuple(reasons[:3]),
            metrics={
                "like_percentile": _rounded_optional(record.percentiles.get("like_percentile")),
                "comment_percentile": _rounded_optional(record.percentiles.get("comment_percentile")),
                "share_percentile": _rounded_optional(record.percentiles.get("share_percentile")),
                "collect_percentile": _rounded_optional(record.percentiles.get("collect_percentile")),
                "recency_percentile": _rounded_optional(record.percentiles.get("recency_percentile")),
            },
        )
        for index, (record, roles, score, reasons) in enumerate(prepared, start=1)
    )

    for role in ROLE_ORDER:
        if not coverage[role.value] and not role_scores.get(role):
            warnings.append(_unavailable_role_warning(role))

    return RepresentativeSampleSelection(
        target_count=target,
        input_count=len(raw_samples),
        available_count=len(records),
        recommendations=recommendations,
        coverage=coverage,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _validated_target_count(value: int) -> int:
    try:
        target = int(value)
    except (TypeError, ValueError) as error:
        raise RepresentativeSampleSelectorError("推荐数量必须是整数。") from error
    if target < MIN_TARGET_COUNT or target > MAX_TARGET_COUNT:
        raise RepresentativeSampleSelectorError(
            f"推荐数量必须在 {MIN_TARGET_COUNT}–{MAX_TARGET_COUNT} 条之间。"
        )
    return target


def _record_from_sample(sample: Any) -> _SampleRecord | None:
    sample_id = _safe_sample_id(_value(sample, "sample_id", "id", "aweme_id", "platform_item_id"))
    if not sample_id:
        return None
    title = _text(_value(sample, "title"), 500)
    description = _text(_value(sample, "desc", "description"), 1000)
    media_type = _enum_text(_value(sample, "media_type", "media_kind"), "unknown")
    duration = _duration_seconds(_value(sample, "duration", "duration_seconds"))
    category = _text(_value(sample, "content_category", "category"), 120)
    tags_value = _value(sample, "tags")
    tags = tuple(_text(item, 80) for item in tags_value if _text(item, 80)) if isinstance(tags_value, (list, tuple, set)) else ()
    create_time = _value(sample, "create_time", "created_at", "publish_time")
    metrics = {
        key: _optional_non_negative_number(_metric_value(sample, key))
        for key in METRIC_WEIGHTS
    }
    record = _SampleRecord(
        sample_id=sample_id,
        title=title,
        description=description,
        media_type=media_type,
        duration_seconds=duration,
        content_category=category,
        tags=tags,
        created_timestamp=_timestamp(create_time),
        metrics=metrics,
    )
    record.fingerprint = _content_fingerprint(record)
    return record


def _prepare_record_scores(records: list[_SampleRecord], warnings: list[str]) -> None:
    percentile_maps: dict[str, dict[str, float | None]] = {}
    strength_maps: dict[str, dict[str, float | None]] = {}
    for metric_key, output_key in METRIC_PERCENTILE_KEYS.items():
        values = {record.sample_id: record.metrics.get(metric_key) for record in records}
        percentiles, informative = _percentiles(values)
        percentile_maps[output_key] = percentiles
        strength_maps[metric_key] = _relative_strengths(values) if informative else {
            sample_id: None for sample_id in values
        }
        if not informative:
            warnings.append(f"{_metric_label(metric_key)}数据全部缺失或为 0，已从表现权重中移除。")

    recency_values = {record.sample_id: record.created_timestamp for record in records}
    recency_percentiles, _ = _percentiles(recency_values, require_positive=False)
    percentile_maps["recency_percentile"] = recency_percentiles

    comment_ratios: dict[str, float | None] = {}
    for record in records:
        comments = record.metrics.get("comment_count")
        likes = record.metrics.get("like_count")
        comment_ratios[record.sample_id] = (
            comments / max(1.0, likes)
            if comments is not None and likes is not None
            else None
        )
    ratio_percentiles, _ = _percentiles(comment_ratios, require_positive=False)

    for record in records:
        record.percentiles = {
            output_key: values.get(record.sample_id)
            for output_key, values in percentile_maps.items()
        }
        record.relative_strengths = {
            key: values.get(record.sample_id)
            for key, values in strength_maps.items()
        }
        record.performance_score = _weighted_available(
            {
                key: record.percentiles.get(output_key)
                for key, output_key in METRIC_PERCENTILE_KEYS.items()
            },
            METRIC_WEIGHTS,
        )
        record.comment_intensity_percentile = ratio_percentiles.get(record.sample_id)

    fingerprints = {record.sample_id: record.fingerprint for record in records}
    for record in records:
        similarities = [
            _jaccard(record.fingerprint, other)
            for sample_id, other in fingerprints.items()
            if sample_id != record.sample_id and record.fingerprint and other
        ]
        record.typicality_score = sum(similarities) / len(similarities) if similarities else 0.0


def _build_role_scores(
    records: list[_SampleRecord],
    warnings: list[str],
) -> dict[RepresentativeRole, dict[str, float]]:
    scores: dict[RepresentativeRole, dict[str, float]] = {role: {} for role in ROLE_ORDER}
    performance_values = [record.performance_score for record in records if record.performance_score is not None]
    performance_median = median(performance_values) if performance_values else None

    for record in records:
        like = record.percentiles.get("like_percentile")
        comment = record.percentiles.get("comment_percentile")
        share = record.percentiles.get("share_percentile")
        collect = record.percentiles.get("collect_percentile")
        recency = record.percentiles.get("recency_percentile")
        performance = record.performance_score

        breakout = _weighted_available(
            {
                "performance": performance,
                "like": like,
                "like_strength": record.relative_strengths.get("like_count"),
                "share_strength": record.relative_strengths.get("share_count"),
                "collect_strength": record.relative_strengths.get("collect_count"),
            },
            {
                "performance": 0.35,
                "like": 0.15,
                "like_strength": 0.35,
                "share_strength": 0.075,
                "collect_strength": 0.075,
            },
        )
        if breakout is not None:
            scores[RepresentativeRole.BREAKOUT_HIT][record.sample_id] = breakout

        comment_score = _weighted_available(
            {"comment": comment, "intensity": record.comment_intensity_percentile},
            {"comment": 0.65, "intensity": 0.35},
        ) if comment is not None else None
        if comment_score is not None:
            scores[RepresentativeRole.COMMENT_MAGNET][record.sample_id] = comment_score

        save_share = _weighted_available(
            {"collect": collect, "share": share},
            {"collect": 0.5, "share": 0.5},
        )
        if save_share is not None:
            scores[RepresentativeRole.SAVE_SHARE_VALUE][record.sample_id] = save_share

        if recency is not None and performance is not None:
            recent_score = 0.5 * math.sqrt(max(0.0, recency * performance)) + 0.25 * recency + 0.25 * performance
            scores[RepresentativeRole.RECENT_WINNER][record.sample_id] = recent_score

        if len(records) >= 5:
            if performance_median is not None and performance is not None:
                median_closeness = max(0.0, 1.0 - abs(performance - performance_median))
                baseline_score = median_closeness * 0.72 + record.typicality_score * 0.28
            elif record.fingerprint:
                baseline_score = record.typicality_score
            else:
                baseline_score = 0.0
            scores[RepresentativeRole.BASELINE_TYPICAL][record.sample_id] = baseline_score

    if len(records) < 5:
        warnings.append("素材少于 5 条，普通基线角色暂不启用。")
    return scores


def _diversity_scores(
    records: list[_SampleRecord],
    selected_ids: list[str],
    *,
    compare_with_other_selected: bool = False,
) -> dict[str, float]:
    selected = set(selected_ids)
    fingerprints = {record.sample_id: record.fingerprint for record in records}
    scores: dict[str, float] = {}
    for record in records:
        if not record.fingerprint or record.information_score <= 0:
            continue
        comparison_ids = (
            [sample_id for sample_id in selected_ids if sample_id != record.sample_id]
            if compare_with_other_selected
            else list(selected_ids)
        )
        comparison_fingerprints = [fingerprints[sample_id] for sample_id in comparison_ids if fingerprints.get(sample_id)]
        if comparison_fingerprints:
            max_similarity = max(_jaccard(record.fingerprint, other) for other in comparison_fingerprints)
            novelty = 1.0 - max_similarity
        else:
            novelty = 0.5 + (1.0 - record.typicality_score) * 0.5
        score = novelty * 0.82 + record.information_score * 0.18
        if compare_with_other_selected or record.sample_id not in selected:
            scores[record.sample_id] = min(1.0, max(0.0, score))
    return scores


def _best_candidate(
    records: list[_SampleRecord],
    scores: dict[str, float],
    *,
    excluded: set[str],
) -> _SampleRecord | None:
    candidates = [record for record in records if record.sample_id not in excluded and record.sample_id in scores]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda record: (
            -scores[record.sample_id],
            -(record.created_timestamp or 0.0),
            record.sample_id,
        ),
    )[0]


def _record_is_better(
    candidate: _SampleRecord,
    candidate_score: float,
    current: _SampleRecord | None,
    current_score: float,
) -> bool:
    if current is None or candidate_score > current_score:
        return True
    if candidate_score < current_score:
        return False
    return (
        -(candidate.created_timestamp or 0.0),
        candidate.sample_id,
    ) < (
        -(current.created_timestamp or 0.0),
        current.sample_id,
    )


def _recommendation_reasons(
    record: _SampleRecord,
    roles: list[RepresentativeRole],
    role_scores: dict[RepresentativeRole, dict[str, float]],
    records: list[_SampleRecord],
) -> list[str]:
    reasons: list[str] = []
    for role in roles:
        if role == RepresentativeRole.BREAKOUT_HIT:
            reasons.extend(_top_percentile_reasons(record, ("like", "collect", "share"), limit=2))
        elif role == RepresentativeRole.COMMENT_MAGNET:
            reasons.extend(_top_percentile_reasons(record, ("comment",), limit=1))
            if record.comment_intensity_percentile is not None:
                reasons.append(f"评论相对点赞强度位于账号 P{_percentile_label(record.comment_intensity_percentile)}")
        elif role == RepresentativeRole.SAVE_SHARE_VALUE:
            reasons.extend(_top_percentile_reasons(record, ("collect", "share"), limit=2))
        elif role == RepresentativeRole.RECENT_WINNER:
            recency = record.percentiles.get("recency_percentile")
            if recency is not None:
                reasons.append(f"发布时间位于近期 P{_percentile_label(recency)}")
            if record.performance_score is not None:
                reasons.append(f"账号内相对表现得分为 {round(record.performance_score * 100)}/100")
        elif role == RepresentativeRole.DIVERSITY_ANCHOR:
            score = role_scores.get(role, {}).get(record.sample_id, 0.0)
            novelty = max(0, min(100, round(score * 100)))
            reasons.append(f"本地内容差异指标为 {novelty}/100")
            if record.media_type not in {"", "unknown"}:
                reasons.append(f"素材类型为{_media_label(record.media_type)}，用于补充内容结构差异")
        elif role == RepresentativeRole.BASELINE_TYPICAL:
            performance_values = [item.performance_score for item in records if item.performance_score is not None]
            if performance_values and record.performance_score is not None:
                gap = abs(record.performance_score - median(performance_values))
                reasons.append(f"相对表现分与账号中位水平相差 {round(gap * 100)} 分")
            if record.fingerprint:
                reasons.append(f"内容特征与账号其它样本平均重合度约 {round(record.typicality_score * 100)}%")
    if not reasons:
        reasons.append("可区分指标不足，按发布时间与 sample_id 的稳定顺序补足样本")
    return list(dict.fromkeys(reasons))[:3]


def _top_percentile_reasons(record: _SampleRecord, metrics: tuple[str, ...], *, limit: int) -> list[str]:
    candidates: list[tuple[float, str]] = []
    for metric in metrics:
        value = record.percentiles.get(f"{metric}_percentile")
        if value is not None:
            candidates.append((value, f"{_metric_label(metric + '_count')}位于账号 P{_percentile_label(value)}"))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [reason for _, reason in candidates[:limit]]


def _percentiles(
    values_by_id: dict[str, float | None],
    *,
    require_positive: bool = True,
) -> tuple[dict[str, float | None], bool]:
    values = [value for value in values_by_id.values() if value is not None]
    informative = bool(values) and (not require_positive or any(value > 0 for value in values))
    if not informative:
        return {sample_id: None for sample_id in values_by_id}, False
    ordered = sorted(values)
    denominator = max(1, len(ordered) - 1)
    result: dict[str, float | None] = {}
    for sample_id, value in values_by_id.items():
        if value is None:
            result[sample_id] = None
            continue
        if len(ordered) == 1:
            result[sample_id] = 1.0
            continue
        lower = bisect_left(ordered, value)
        upper = bisect_right(ordered, value) - 1
        result[sample_id] = ((lower + upper) / 2.0) / denominator
    return result, True


def _weighted_available(values: dict[str, float | None], weights: dict[str, float]) -> float | None:
    available = [(key, value) for key, value in values.items() if value is not None and key in weights]
    total_weight = sum(weights[key] for key, _ in available)
    if not available or total_weight <= 0:
        return None
    return sum(value * weights[key] for key, value in available) / total_weight


def _relative_strengths(values_by_id: dict[str, float | None]) -> dict[str, float | None]:
    positive = sorted(value for value in values_by_id.values() if value is not None and value > 0)
    if not positive:
        return {sample_id: None for sample_id in values_by_id}
    baseline = max(1.0, float(median(positive)))
    maximum = max(positive)
    denominator = math.log1p(maximum / baseline)
    if denominator <= 0:
        return {sample_id: 1.0 if value is not None else None for sample_id, value in values_by_id.items()}
    return {
        sample_id: (
            min(1.0, math.log1p(max(0.0, value) / baseline) / denominator)
            if value is not None
            else None
        )
        for sample_id, value in values_by_id.items()
    }


def _content_fingerprint(record: _SampleRecord) -> frozenset[str]:
    tokens = _text_tokens(f"{record.title} {record.description}")
    if record.media_type not in {"", "unknown"}:
        tokens.add(f"media:{record.media_type}")
    if record.duration_seconds is not None:
        tokens.add(f"duration:{_duration_bucket(record.duration_seconds)}")
    if record.content_category:
        tokens.add(f"category:{unicodedata.normalize('NFKC', record.content_category).lower()}")
    for tag in record.tags[:20]:
        normalized = unicodedata.normalize("NFKC", tag).strip().lower()
        if normalized:
            tokens.add(f"tag:{normalized}")
    return frozenset(sorted(tokens))


def _text_tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", value or "").lower()[:1500]
    tokens = {f"word:{token}" for token in ASCII_TOKEN_RE.findall(normalized) if len(token) > 1}
    for run in CJK_RUN_RE.findall(normalized):
        if len(run) == 1:
            tokens.add(f"cjk:{run}")
        else:
            tokens.update(f"cjk:{run[index:index + 2]}" for index in range(len(run) - 1))
    return tokens


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _value(sample: Any, *keys: str) -> Any:
    if isinstance(sample, Mapping):
        for key in keys:
            if key in sample:
                return sample.get(key)
        raw = sample.get("raw") if isinstance(sample.get("raw"), Mapping) else {}
        for key in keys:
            if key in raw:
                return raw.get(key)
        return None
    for key in keys:
        if hasattr(sample, key):
            return getattr(sample, key)
    raw = getattr(sample, "raw", None)
    if isinstance(raw, Mapping):
        for key in keys:
            if key in raw:
                return raw.get(key)
    return None


def _metric_value(sample: Any, key: str) -> Any:
    if isinstance(sample, Mapping):
        if key in sample:
            return sample.get(key)
        metrics = sample.get("metrics") if isinstance(sample.get("metrics"), Mapping) else {}
        return metrics.get(key) if key in metrics else None
    if hasattr(sample, key):
        return getattr(sample, key)
    metrics = getattr(sample, "metrics", None)
    return getattr(metrics, key, None) if metrics is not None else None


def _safe_sample_id(value: Any) -> str:
    raw = str(value or "").strip()
    return raw if SAFE_SAMPLE_ID_RE.fullmatch(raw) else ""


def _text(value: Any, limit: int) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()[:limit]


def _enum_text(value: Any, default: str) -> str:
    raw = getattr(value, "value", value)
    text = str(raw or default).strip().lower()
    return text or default


def _optional_non_negative_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return max(0.0, number)


def _duration_seconds(value: Any) -> float | None:
    duration = _optional_non_negative_number(value)
    if not duration:
        return None
    if duration > 3600:
        duration /= 1000.0
    return duration if duration > 0 else None


def _duration_bucket(duration: float) -> str:
    if duration < 15:
        return "short"
    if duration < 60:
        return "medium"
    return "long"


def _timestamp(value: Any) -> float | None:
    if value is None or value == "":
        return None
    raw = str(value).strip()
    try:
        numeric = float(raw)
    except ValueError:
        numeric = None
    if numeric is not None and math.isfinite(numeric):
        if numeric > 10_000_000_000:
            numeric /= 1000.0
        return numeric if numeric > 0 else None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _metric_label(metric_key: str) -> str:
    return {
        "like_count": "点赞",
        "comment_count": "评论",
        "share_count": "分享",
        "collect_count": "收藏",
    }.get(metric_key, metric_key)


def _media_label(media_type: str) -> str:
    return {"video": "视频", "image": "图文", "text": "文字", "mixed": "混合"}.get(media_type, media_type)


def _percentile_label(value: float) -> int:
    return max(0, min(100, int(round(value * 100))))


def _rounded_optional(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def _unavailable_role_warning(role: RepresentativeRole) -> str:
    return {
        RepresentativeRole.BREAKOUT_HIT: "互动指标不足，爆款代表暂不可判断。",
        RepresentativeRole.COMMENT_MAGNET: "评论数据不足，高讨论代表暂不可判断。",
        RepresentativeRole.SAVE_SHARE_VALUE: "收藏与分享数据不足，收藏/转发代表暂不可判断。",
        RepresentativeRole.RECENT_WINNER: "发布时间或表现数据不足，近期高表现代表暂不可判断。",
        RepresentativeRole.DIVERSITY_ANCHOR: "内容文本、类型与时长信息不足，内容差异代表暂不可判断。",
        RepresentativeRole.BASELINE_TYPICAL: "样本量或典型性信息不足，普通基线代表暂不可判断。",
    }[role]
