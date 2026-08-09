from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _tuple_env(name: str) -> tuple[str, ...]:
    return tuple(
        value.strip().lower()
        for value in os.getenv(name, "").split(",")
        if value.strip()
    )


class Settings:
    project_root: Path = PROJECT_ROOT
    output_dir: Path = PROJECT_ROOT / os.getenv("OUTPUT_DIR", "outputs")
    uploads_dir: Path = output_dir / "uploads"
    cases_dir: Path = output_dir / "cases"
    downloads_dir: Path = output_dir / "downloads"
    calibration_dir: Path = output_dir / "calibration"
    creator_clones_dir: Path = output_dir / "creator_clones"
    creator_state_dir: Path = output_dir / "creator_state"
    database_url: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(PROJECT_ROOT / 'short_video_agent.db').as_posix()}",
    )
    douyin_cookie: str = os.getenv("DOUYIN_COOKIE", "")
    douyin_user_agent: str = os.getenv("DOUYIN_USER_AGENT", "").strip()
    douyin_referer: str = os.getenv("DOUYIN_REFERER", "https://www.douyin.com/").strip()
    douyin_login_extension_ids: tuple[str, ...] = _tuple_env("DOUYIN_LOGIN_EXTENSION_IDS")
    max_video_size_mb: int = _int_env("MAX_VIDEO_SIZE_MB", 500)
    allowed_cdn_hosts: tuple[str, ...] = tuple(
        host.strip().lower()
        for host in os.getenv(
            "ALLOWED_CDN_HOSTS",
            "365yg.com,douyinvod.com,snssdk.com,zjcdn.com,douyin.com",
        ).split(",")
        if host.strip()
    )
    download_timeout_seconds: float = _float_env("DOWNLOAD_TIMEOUT_SECONDS", 60.0)
    quality_cache_ttl_seconds: int = _int_env("QUALITY_CACHE_TTL_SECONDS", 1800)
    candidate_probe_enabled: bool = os.getenv("CANDIDATE_PROBE_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    candidate_probe_timeout_seconds: float = _float_env("CANDIDATE_PROBE_TIMEOUT_SECONDS", 1.2)
    candidate_probe_max_candidates: int = _int_env("CANDIDATE_PROBE_MAX_CANDIDATES", 3)
    profile_scan_provider: str = os.getenv("PROFILE_SCAN_PROVIDER", "public").strip().lower()
    profile_scan_api_base: str = os.getenv("PROFILE_SCAN_API_BASE", "").rstrip("/")
    profile_scan_max_pages: int = _int_env("PROFILE_SCAN_MAX_PAGES", 1)
    profile_scan_count_per_page: int = _int_env("PROFILE_SCAN_COUNT_PER_PAGE", 20)
    profile_build_max_items: int = _int_env("PROFILE_BUILD_MAX_ITEMS", 150)
    keyframe_max_count: int = _int_env("KEYFRAME_MAX_COUNT", 30)
    keyframe_interval_seconds: float = _float_env("KEYFRAME_INTERVAL_SECONDS", 1.0)
    llm_provider: str = os.getenv("LLM_PROVIDER", "disabled").strip().lower()
    llm_api_base: str = os.getenv("LLM_API_BASE", "https://api.openai.com/v1").rstrip("/")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "")
    llm_timeout_seconds: float = _float_env("LLM_TIMEOUT_SECONDS", 90.0)
    llm_creator_distill_request_timeout_seconds: float = _float_env(
        "LLM_CREATOR_DISTILL_REQUEST_TIMEOUT_SECONDS",
        180.0,
    )
    llm_final_reduce_timeout_seconds: float = _float_env("LLM_FINAL_REDUCE_TIMEOUT_SECONDS", 600.0)
    llm_quick_distill_budget_seconds: float = _float_env("LLM_QUICK_DISTILL_BUDGET_SECONDS", 240.0)
    llm_deep_distill_budget_seconds: float = _float_env("LLM_DEEP_DISTILL_BUDGET_SECONDS", 600.0)
    llm_batch_job_budget_seconds: float = _float_env("LLM_BATCH_JOB_BUDGET_SECONDS", 600.0)
    llm_final_reduce_min_reserve_seconds: float = _float_env("LLM_FINAL_REDUCE_MIN_RESERVE_SECONDS", 120.0)
    llm_compact_retry_min_remaining_seconds: float = _float_env(
        "LLM_COMPACT_RETRY_MIN_REMAINING_SECONDS",
        60.0,
    )
    llm_temperature: float = _float_env("LLM_TEMPERATURE", 0.2)
    llm_max_keyframes: int = _int_env("LLM_MAX_KEYFRAMES", 6)
    llm_max_output_tokens: int = _int_env("LLM_MAX_OUTPUT_TOKENS", 1200)
    llm_final_reduce_max_output_tokens: int = _int_env("LLM_FINAL_REDUCE_MAX_OUTPUT_TOKENS", 4000)
    llm_image_max_width: int = _int_env("LLM_IMAGE_MAX_WIDTH", 1280)
    llm_image_jpeg_quality: int = _int_env("LLM_IMAGE_JPEG_QUALITY", 72)
    asr_provider: str = os.getenv("ASR_PROVIDER", "disabled").strip().lower()
    asr_model_size: str = os.getenv("ASR_MODEL_SIZE", "base").strip()
    asr_device: str = os.getenv("ASR_DEVICE", "auto").strip()
    asr_compute_type: str = os.getenv("ASR_COMPUTE_TYPE", "default").strip()
    asr_language: str = os.getenv("ASR_LANGUAGE", "zh").strip()
    asr_beam_size: int = _int_env("ASR_BEAM_SIZE", 5)
    ocr_provider: str = os.getenv("OCR_PROVIDER", "disabled").strip().lower()
    ocr_language: str = os.getenv("OCR_LANGUAGE", "ch").strip()
    ocr_max_frames: int = _int_env("OCR_MAX_FRAMES", 12)
    ocr_subtitle_crop_ratio: float = _float_env("OCR_SUBTITLE_CROP_RATIO", 0.35)
    local_chrome_profile_mode: str = os.getenv("LOCAL_CHROME_PROFILE_MODE", "dedicated").strip().lower()
    local_chrome_user_data_dir: str = os.getenv("LOCAL_CHROME_USER_DATA_DIR", "").strip()

    def ensure_directories(self) -> None:
        for directory in (
            self.output_dir,
            self.uploads_dir,
            self.cases_dir,
            self.downloads_dir,
            self.calibration_dir,
            self.creator_clones_dir,
            self.creator_state_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


settings = Settings()
