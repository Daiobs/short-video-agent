from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VideoQualityCandidateDTO:
    candidate_id: str
    aweme_id: str
    quality_label: str
    url: str
    size_bytes: int
    bitrate: int
    host: str
    object_key: str
    expires_at: int
    source: str


class BaseVideoProvider(Protocol):
    def resolve(self, aweme_id: str) -> list[VideoQualityCandidateDTO]:
        raise NotImplementedError

