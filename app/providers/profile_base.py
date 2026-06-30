from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Protocol


VALID_PROFILE_SORTS = {"like_count", "comment_count", "share_count", "engagement_score", "create_time"}


def profile_engagement_score(like_count: int, comment_count: int, share_count: int) -> int:
    return int(like_count or 0) + int(comment_count or 0) * 5 + int(share_count or 0) * 8


@dataclass
class ProfileScanRequest:
    profile_url: str | None = None
    sec_user_id: str | None = None
    manual_links: str | None = None
    structured_items: str | None = None
    count: int = 20
    max_pages: int = 1
    sort_by: str = "like_count"


@dataclass
class ProfileVideoItem:
    aweme_id: str
    title: str = ""
    desc: str = ""
    author: str = ""
    sec_user_id: str = ""
    cover_url: str = ""
    create_time: str = ""
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    collect_count: int = 0
    view_count: int = 0
    duration: int = 0
    webpage_url: str = ""
    media_type: str = "unknown"
    source_provider: str = ""

    @property
    def engagement_score(self) -> int:
        return profile_engagement_score(self.like_count, self.comment_count, self.share_count)

    @property
    def can_build_case(self) -> bool:
        return self.media_type in {"video", "unknown"}

    def to_dict(self) -> dict:
        return {
            "aweme_id": self.aweme_id,
            "title": self.title,
            "desc": self.desc,
            "author": self.author,
            "sec_user_id": self.sec_user_id,
            "cover_url": self.cover_url,
            "create_time": self.create_time,
            "like_count": self.like_count,
            "comment_count": self.comment_count,
            "share_count": self.share_count,
            "collect_count": self.collect_count,
            "view_count": self.view_count,
            "duration": self.duration,
            "webpage_url": self.webpage_url or f"https://www.douyin.com/video/{self.aweme_id}",
            "media_type": self.media_type,
            "can_build_case": self.can_build_case,
            "engagement_score": self.engagement_score,
            "source_provider": self.source_provider,
        }


@dataclass
class ProfileScanSummary:
    profile_url: str = ""
    sec_user_id: str = ""
    nickname: str = ""
    signature: str = ""
    follower_count: int = 0
    following_count: int = 0
    total_favorited: int = 0
    video_count: int = 0
    scanned_count: int = 0
    top_items: list[dict] = field(default_factory=list)
    avg_like_count: float = 0
    avg_comment_count: float = 0
    avg_share_count: float = 0
    avg_engagement_score: float = 0
    median_engagement_score: float = 0
    max_engagement_score: int = 0
    content_keywords: list[str] = field(default_factory=list)
    publish_time_distribution: dict = field(default_factory=dict)
    content_category_distribution: dict = field(default_factory=dict)
    top_hooks_summary: list[str] = field(default_factory=list)
    common_visual_patterns: list[str] = field(default_factory=list)
    common_title_patterns: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "profile_url": self.profile_url,
            "sec_user_id": self.sec_user_id,
            "nickname": self.nickname,
            "signature": self.signature,
            "follower_count": self.follower_count,
            "following_count": self.following_count,
            "total_favorited": self.total_favorited,
            "video_count": self.video_count,
            "scanned_count": self.scanned_count,
            "top_items": self.top_items,
            "avg_like_count": self.avg_like_count,
            "avg_comment_count": self.avg_comment_count,
            "avg_share_count": self.avg_share_count,
            "avg_engagement_score": self.avg_engagement_score,
            "median_engagement_score": self.median_engagement_score,
            "max_engagement_score": self.max_engagement_score,
            "content_keywords": self.content_keywords,
            "publish_time_distribution": self.publish_time_distribution,
            "content_category_distribution": self.content_category_distribution,
            "top_hooks_summary": self.top_hooks_summary,
            "common_visual_patterns": self.common_visual_patterns,
            "common_title_patterns": self.common_title_patterns,
            "warnings": self.warnings,
        }


@dataclass
class ProfileScanResult:
    provider: str
    profile_url: str = ""
    sec_user_id: str = ""
    items: list[ProfileVideoItem] = field(default_factory=list)
    has_more: bool = False
    next_cursor: str = ""
    warnings: list[str] = field(default_factory=list)
    import_stats: dict = field(default_factory=dict)
    summary: ProfileScanSummary | None = None

    def to_dict(self) -> dict:
        summary = self.summary or build_profile_summary(self)
        return {
            "provider": self.provider,
            "profile_url": self.profile_url,
            "sec_user_id": self.sec_user_id,
            "items": [item.to_dict() for item in self.items],
            "has_more": self.has_more,
            "next_cursor": self.next_cursor,
            "warnings": self.warnings,
            "import_stats": self.import_stats,
            "summary": summary.to_dict(),
        }


class BaseProfileProvider(Protocol):
    name: str

    def scan(self, request: ProfileScanRequest) -> ProfileScanResult:
        ...


def sorted_profile_items(items: list[ProfileVideoItem], sort_by: str) -> list[ProfileVideoItem]:
    key = sort_by if sort_by in VALID_PROFILE_SORTS else "like_count"
    return sorted(
        items,
        key=lambda item: getattr(item, key) if key != "engagement_score" else item.engagement_score,
        reverse=True,
    )


def build_profile_summary(result: ProfileScanResult) -> ProfileScanSummary:
    items = result.items
    scanned_count = len(items)
    if not items:
        return ProfileScanSummary(
            profile_url=result.profile_url,
            sec_user_id=result.sec_user_id,
            scanned_count=0,
            warnings=list(result.warnings),
        )

    like_counts = [item.like_count for item in items]
    comment_counts = [item.comment_count for item in items]
    share_counts = [item.share_count for item in items]
    scores = [item.engagement_score for item in items]
    top_profile_items = sorted_profile_items(items, "engagement_score")[:3]
    top_items = [item.to_dict() for item in top_profile_items]
    keywords = _top_keywords(" ".join(f"{item.title} {item.desc}" for item in items))

    return ProfileScanSummary(
        profile_url=result.profile_url,
        sec_user_id=result.sec_user_id,
        scanned_count=scanned_count,
        video_count=sum(1 for item in items if item.media_type == "video"),
        top_items=top_items,
        avg_like_count=round(sum(like_counts) / scanned_count, 2),
        avg_comment_count=round(sum(comment_counts) / scanned_count, 2),
        avg_share_count=round(sum(share_counts) / scanned_count, 2),
        avg_engagement_score=round(sum(scores) / scanned_count, 2),
        median_engagement_score=float(median(scores)),
        max_engagement_score=max(scores),
        content_keywords=keywords,
        publish_time_distribution=_publish_time_distribution(items),
        content_category_distribution=_content_category_distribution(items),
        top_hooks_summary=[item.title or item.desc for item in top_profile_items if item.title or item.desc],
        common_visual_patterns=[],
        common_title_patterns=keywords[:5],
        warnings=list(result.warnings),
    )


def _top_keywords(text: str) -> list[str]:
    import re
    from collections import Counter

    words = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_#]{2,}", text or "")
    ignored = {"https", "http", "www", "com", "douyin"}
    counter = Counter(word.strip("#").lower() for word in words if word.lower() not in ignored)
    return [word for word, _ in counter.most_common(12)]


def _publish_time_distribution(items: list[ProfileVideoItem]) -> dict:
    distribution: dict[str, int] = {}
    for item in items:
        bucket = "unknown"
        if item.create_time:
            bucket = str(item.create_time)[:10]
        distribution[bucket] = distribution.get(bucket, 0) + 1
    return distribution


def _content_category_distribution(items: list[ProfileVideoItem]) -> dict:
    distribution: dict[str, int] = {}
    for item in items:
        text = f"{item.title} {item.desc}"
        category = "通用短视频"
        if any(keyword in text for keyword in ("cos", "COS", "妆", "穿搭", "写真", "美拍")):
            category = "美拍/COS"
        elif any(keyword in text for keyword in ("教程", "教学", "方法", "步骤")):
            category = "教学/教程"
        elif any(keyword in text for keyword in ("人生", "低谷", "情绪", "清醒", "文案")):
            category = "鸡汤/情绪价值"
        distribution[category] = distribution.get(category, 0) + 1
    return distribution
