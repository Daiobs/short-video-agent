from __future__ import annotations

from dataclasses import dataclass


class ErrorCode:
    INVALID_PROFILE_URL = "INVALID_PROFILE_URL"
    INVALID_AWEME_URL = "INVALID_AWEME_URL"
    SEC_USER_ID_NOT_FOUND = "SEC_USER_ID_NOT_FOUND"
    AWEME_ID_NOT_FOUND = "AWEME_ID_NOT_FOUND"
    DOUYIN_RISK_CONTROL = "DOUYIN_RISK_CONTROL"
    COOKIE_REQUIRED = "COOKIE_REQUIRED"
    COOKIE_INVALID = "COOKIE_INVALID"
    EMPTY_AWEME_LIST = "EMPTY_AWEME_LIST"
    PROVIDER_FAILED = "PROVIDER_FAILED"
    QUALITY_NOT_FOUND = "QUALITY_NOT_FOUND"
    URL_EXPIRED = "URL_EXPIRED"
    HOST_NOT_ALLOWED = "HOST_NOT_ALLOWED"
    REDIRECT_HOST_NOT_ALLOWED = "REDIRECT_HOST_NOT_ALLOWED"
    CONTENT_TYPE_INVALID = "CONTENT_TYPE_INVALID"
    CONTENT_LENGTH_TOO_LARGE = "CONTENT_LENGTH_TOO_LARGE"
    DOWNLOAD_TIMEOUT = "DOWNLOAD_TIMEOUT"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    FFMPEG_NOT_FOUND = "FFMPEG_NOT_FOUND"
    FFPROBE_FAILED = "FFPROBE_FAILED"
    KEYFRAME_EXTRACT_FAILED = "KEYFRAME_EXTRACT_FAILED"
    CASE_BUILD_FAILED = "CASE_BUILD_FAILED"
    LOCAL_UPLOAD_FAILED = "LOCAL_UPLOAD_FAILED"
    INVALID_VIDEO_FILE = "INVALID_VIDEO_FILE"
    LLM_NOT_CONFIGURED = "LLM_NOT_CONFIGURED"
    LLM_REQUEST_FAILED = "LLM_REQUEST_FAILED"
    LLM_RESPONSE_INVALID = "LLM_RESPONSE_INVALID"
    AUTO_ANALYSIS_FAILED = "AUTO_ANALYSIS_FAILED"
    ENRICHMENT_FAILED = "ENRICHMENT_FAILED"
    COMMENTS_IMPORT_FAILED = "COMMENTS_IMPORT_FAILED"
    PROFILE_SCAN_FAILED = "PROFILE_SCAN_FAILED"
    PROFILE_SCAN_NEEDS_FALLBACK = "PROFILE_SCAN_NEEDS_FALLBACK"
    PROFILE_SCAN_API_NOT_CONFIGURED = "PROFILE_SCAN_API_NOT_CONFIGURED"
    PROFILE_SCAN_STRUCTURE_CHANGED = "PROFILE_SCAN_STRUCTURE_CHANGED"
    ASR_PROVIDER_NOT_CONFIGURED = "ASR_PROVIDER_NOT_CONFIGURED"
    ASR_FAILED = "ASR_FAILED"
    OCR_PROVIDER_NOT_CONFIGURED = "OCR_PROVIDER_NOT_CONFIGURED"
    OCR_FAILED = "OCR_FAILED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


ERROR_MESSAGES = {
    ErrorCode.INVALID_PROFILE_URL: "主页 URL 无效。",
    ErrorCode.INVALID_AWEME_URL: "作品链接或 aweme_id 无效。",
    ErrorCode.SEC_USER_ID_NOT_FOUND: "无法从主页 URL 提取 sec_user_id。",
    ErrorCode.AWEME_ID_NOT_FOUND: "无法从作品链接提取 aweme_id。",
    ErrorCode.DOUYIN_RISK_CONTROL: "主页扫描失败：疑似被抖音风控。可以配置 DOUYIN_COOKIE，或改用单作品链接/本地视频上传模式。",
    ErrorCode.COOKIE_REQUIRED: "当前请求可能需要 Cookie。请在 .env 中配置 DOUYIN_COOKIE，或使用本地视频上传模式。",
    ErrorCode.COOKIE_INVALID: "Cookie 缺失或失效。请更新 .env 中的 DOUYIN_COOKIE，或使用本地视频上传模式。",
    ErrorCode.EMPTY_AWEME_LIST: "作品列表为空。",
    ErrorCode.PROVIDER_FAILED: "清晰度 Provider 调用失败。",
    ErrorCode.QUALITY_NOT_FOUND: "未找到可用清晰度候选。",
    ErrorCode.URL_EXPIRED: "下载链接已过期，需要重新解析。",
    ErrorCode.HOST_NOT_ALLOWED: "下载链接 host 不在允许列表中，已拒绝下载。",
    ErrorCode.REDIRECT_HOST_NOT_ALLOWED: "下载跳转后的 host 不在允许列表中，已拒绝下载。",
    ErrorCode.CONTENT_TYPE_INVALID: "下载响应不是视频文件，可能是 HTML 风控页或错误页，已拒绝保存。",
    ErrorCode.CONTENT_LENGTH_TOO_LARGE: "视频文件超过允许大小，已拒绝下载。",
    ErrorCode.DOWNLOAD_TIMEOUT: "下载超时。",
    ErrorCode.DOWNLOAD_FAILED: "下载失败。",
    ErrorCode.FFMPEG_NOT_FOUND: "未检测到 ffmpeg，请先安装 ffmpeg 并确保命令行可用。",
    ErrorCode.FFPROBE_FAILED: "ffprobe 读取视频信息失败。",
    ErrorCode.KEYFRAME_EXTRACT_FAILED: "关键帧抽取失败。",
    ErrorCode.CASE_BUILD_FAILED: "素材包生成失败。",
    ErrorCode.LOCAL_UPLOAD_FAILED: "本地视频上传失败。",
    ErrorCode.INVALID_VIDEO_FILE: "上传文件不是有效视频，或文件为空。",
    ErrorCode.LLM_NOT_CONFIGURED: "大模型 API 未配置。请在 .env 中配置 LLM_PROVIDER、LLM_API_BASE、LLM_API_KEY 和 LLM_MODEL。",
    ErrorCode.LLM_REQUEST_FAILED: "大模型 API 请求失败。请检查 API Base、Key、网络、余额和模型名。",
    ErrorCode.LLM_RESPONSE_INVALID: "大模型没有返回合法 JSON。可以降低 LLM_TEMPERATURE，或换用更稳定的多模态模型。",
    ErrorCode.AUTO_ANALYSIS_FAILED: "自动拆解失败。请检查 contact_sheet.jpg 和 keyframes/ 是否已经生成。",
    ErrorCode.ENRICHMENT_FAILED: "素材富化归档失败。请检查素材包文件是否完整。",
    ErrorCode.COMMENTS_IMPORT_FAILED: "评论导入失败。请检查评论文本或 JSON 格式。",
    ErrorCode.PROFILE_SCAN_FAILED: "主页扫描失败。请检查主页 URL / sec_user_id，或改用多作品链接粘贴。",
    ErrorCode.PROFILE_SCAN_NEEDS_FALLBACK: "公开主页未包含可解析作品列表。当前不登录、不使用 Cookie、不绕风控，请改用多作品链接粘贴或单作品解析。",
    ErrorCode.PROFILE_SCAN_API_NOT_CONFIGURED: "已选择 external_api 主页扫描，但 PROFILE_SCAN_API_BASE 未配置。",
    ErrorCode.PROFILE_SCAN_STRUCTURE_CHANGED: "主页返回结构无法归一化，可能是平台页面结构变化。请改用多作品链接粘贴或单作品解析。",
    ErrorCode.ASR_PROVIDER_NOT_CONFIGURED: "ASR provider 尚未配置。后续可接入 faster-whisper、whisper.cpp 或 API ASR。",
    ErrorCode.ASR_FAILED: "语音识别失败。请检查视频音轨、ffmpeg 输出和 ASR 模型配置。",
    ErrorCode.OCR_PROVIDER_NOT_CONFIGURED: "OCR provider 尚未配置。后续可接入 PaddleOCR 或 rapidocr-onnxruntime。",
    ErrorCode.OCR_FAILED: "画面文字识别失败。请检查关键帧是否存在，以及 OCR provider 配置是否正确。",
    ErrorCode.NOT_IMPLEMENTED: "该功能将在后续版本接入，当前版本未启用。",
}


@dataclass
class AppError(Exception):
    code: str
    message: str = ""

    def __post_init__(self) -> None:
        if not self.message:
            self.message = ERROR_MESSAGES.get(self.code, "操作失败。")

    def as_dict(self) -> dict[str, str]:
        return {"error_code": self.code, "message": self.message}


def error_message(code: str) -> str:
    return ERROR_MESSAGES.get(code, "操作失败。")
