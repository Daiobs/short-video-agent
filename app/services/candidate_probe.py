from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from time import monotonic
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.providers.base import VideoQualityCandidateDTO


_HOST_LATENCY_SECONDS: dict[str, float] = {}


def _host_allowed(host: str) -> bool:
    host = (host or "").lower()
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in settings.allowed_cdn_hosts)


def _group_key(candidate: VideoQualityCandidateDTO) -> tuple[str, str, int, int]:
    return (
        candidate.source,
        candidate.quality_label,
        candidate.size_bytes,
        candidate.bitrate,
    )


def get_cached_host_latency(host: str) -> float | None:
    return _HOST_LATENCY_SECONDS.get((host or "").lower())


def _probe_candidate_latency(candidate: VideoQualityCandidateDTO) -> float | None:
    parsed = urlparse(candidate.url)
    if parsed.scheme != "https" or not _host_allowed(parsed.hostname or ""):
        return None

    headers = {
        "Accept": "*/*",
        "Range": "bytes=0-0",
        "Referer": "https://www.douyin.com/",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    start = monotonic()
    try:
        with httpx.Client(
            timeout=settings.candidate_probe_timeout_seconds,
            follow_redirects=True,
            trust_env=False,
            headers=headers,
        ) as client:
            with client.stream("GET", candidate.url) as response:
                final_host = (urlparse(str(response.url)).hostname or "").lower()
                if not _host_allowed(final_host):
                    return None
                if response.status_code >= 400:
                    return None
                content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
                if content_type and not (
                    content_type.startswith("video/") or content_type == "application/octet-stream"
                ):
                    return None
                for chunk in response.iter_bytes():
                    if chunk:
                        break
    except httpx.HTTPError:
        return None
    return monotonic() - start


def rank_fastest_equivalent_candidates(
    candidates: list[VideoQualityCandidateDTO],
) -> list[VideoQualityCandidateDTO]:
    if not settings.candidate_probe_enabled or len(candidates) < 2:
        return candidates

    first_key = _group_key(candidates[0])
    equivalent = [candidate for candidate in candidates if _group_key(candidate) == first_key]
    if len(equivalent) < 2:
        return candidates

    max_candidates = max(1, settings.candidate_probe_max_candidates)
    probe_group = equivalent[:max_candidates]
    probe_ids = {candidate.candidate_id for candidate in probe_group}
    original_index = {candidate.candidate_id: index for index, candidate in enumerate(candidates)}
    latencies: dict[str, float] = {}

    with ThreadPoolExecutor(max_workers=min(len(probe_group), max_candidates)) as executor:
        future_map = {executor.submit(_probe_candidate_latency, candidate): candidate for candidate in probe_group}
        for future in as_completed(future_map):
            candidate = future_map[future]
            latency = future.result()
            if latency is None:
                continue
            latencies[candidate.candidate_id] = latency
            _HOST_LATENCY_SECONDS[candidate.host.lower()] = latency

    if not latencies:
        return candidates

    def sort_key(candidate: VideoQualityCandidateDTO) -> tuple[float, int]:
        cached_latency = get_cached_host_latency(candidate.host)
        latency = latencies.get(candidate.candidate_id, cached_latency)
        return (latency if latency is not None else float("inf"), original_index[candidate.candidate_id])

    ranked_group = sorted(probe_group, key=sort_key)
    untouched_probe_equivalent = [candidate for candidate in equivalent if candidate.candidate_id not in probe_ids]
    rest = [candidate for candidate in candidates if _group_key(candidate) != first_key]
    return ranked_group + untouched_probe_equivalent + rest
