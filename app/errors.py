from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ErrorCode:
    INVALID_PROFILE_URL = "INVALID_PROFILE_URL"
    INVALID_AWEME_URL = "INVALID_AWEME_URL"
    SEC_USER_ID_NOT_FOUND = "SEC_USER_ID_NOT_FOUND"
    AWEME_ID_NOT_FOUND = "AWEME_ID_NOT_FOUND"
    DOUYIN_RISK_CONTROL = "DOUYIN_RISK_CONTROL"
    COOKIE_REQUIRED = "COOKIE_REQUIRED"
    COOKIE_INVALID = "COOKIE_INVALID"
    DOUYIN_COOKIE_INVALID = "DOUYIN_COOKIE_INVALID"
    DOUYIN_LOGIN_REQUIRED = "DOUYIN_LOGIN_REQUIRED"
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
    LLM_RATE_LIMITED = "LLM_RATE_LIMITED"
    LLM_AUTH_FAILED = "LLM_AUTH_FAILED"
    LLM_QUOTA_EXCEEDED = "LLM_QUOTA_EXCEEDED"
    LLM_UPSTREAM_UNAVAILABLE = "LLM_UPSTREAM_UNAVAILABLE"
    LLM_GATEWAY_TIMEOUT = "LLM_GATEWAY_TIMEOUT"
    LLM_RESPONSE_INVALID = "LLM_RESPONSE_INVALID"
    LLM_SETTINGS_INVALID = "LLM_SETTINGS_INVALID"
    AUTO_ANALYSIS_FAILED = "AUTO_ANALYSIS_FAILED"
    ENRICHMENT_FAILED = "ENRICHMENT_FAILED"
    COMMENTS_IMPORT_FAILED = "COMMENTS_IMPORT_FAILED"
    PROFILE_SCAN_FAILED = "PROFILE_SCAN_FAILED"
    PROFILE_SCAN_NEEDS_FALLBACK = "PROFILE_SCAN_NEEDS_FALLBACK"
    PROFILE_SCAN_API_NOT_CONFIGURED = "PROFILE_SCAN_API_NOT_CONFIGURED"
    PROFILE_SCAN_STRUCTURE_CHANGED = "PROFILE_SCAN_STRUCTURE_CHANGED"
    UNSUPPORTED_PROFILE_ITEM = "UNSUPPORTED_PROFILE_ITEM"
    PROFILE_BUILD_QUEUE_LIMIT = "PROFILE_BUILD_QUEUE_LIMIT"
    PROFILE_BUILD_ITEM_FAILED = "PROFILE_BUILD_ITEM_FAILED"
    ASR_PROVIDER_NOT_CONFIGURED = "ASR_PROVIDER_NOT_CONFIGURED"
    ASR_FAILED = "ASR_FAILED"
    OCR_PROVIDER_NOT_CONFIGURED = "OCR_PROVIDER_NOT_CONFIGURED"
    OCR_FAILED = "OCR_FAILED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    LOCAL_HELPER_FORBIDDEN = "LOCAL_HELPER_FORBIDDEN"
    LOCAL_HELPER_TOKEN_INVALID = "LOCAL_HELPER_TOKEN_INVALID"
    LOCAL_HELPER_CONFIRMATION_REQUIRED = "LOCAL_HELPER_CONFIRMATION_REQUIRED"
    HANDOFF_MANIFEST_INVALID = "HANDOFF_MANIFEST_INVALID"
    HANDOFF_TOKEN_INVALID = "HANDOFF_TOKEN_INVALID"
    LOCAL_CHROME_NOT_AVAILABLE = "LOCAL_CHROME_NOT_AVAILABLE"
    LOCAL_CHROME_TAB_NOT_FOUND = "LOCAL_CHROME_TAB_NOT_FOUND"
    LOCAL_CHROME_SCAN_FAILED = "LOCAL_CHROME_SCAN_FAILED"
    EXTENSION_ID_CONFIGURATION_REQUIRED = "EXTENSION_ID_CONFIGURATION_REQUIRED"
    LOCAL_LOGIN_STATE_EXTENSION_FORBIDDEN = "LOCAL_LOGIN_STATE_EXTENSION_FORBIDDEN"
    LOCAL_LOGIN_PAIR_CODE_INVALID = "LOCAL_LOGIN_PAIR_CODE_INVALID"
    LOCAL_LOGIN_PAIR_CODE_EXPIRED = "LOCAL_LOGIN_PAIR_CODE_EXPIRED"
    LOCAL_LOGIN_STATE_NOT_PAIRED = "LOCAL_LOGIN_STATE_NOT_PAIRED"
    LOCAL_LOGIN_STATE_AUTH_FAILED = "LOCAL_LOGIN_STATE_AUTH_FAILED"
    LOCAL_LOGIN_STATE_TIMESTAMP_INVALID = "LOCAL_LOGIN_STATE_TIMESTAMP_INVALID"
    LOCAL_LOGIN_STATE_REPLAY = "LOCAL_LOGIN_STATE_REPLAY"
    LOCAL_LOGIN_STATE_PAYLOAD_TOO_LARGE = "LOCAL_LOGIN_STATE_PAYLOAD_TOO_LARGE"
    LOCAL_LOGIN_STATE_INVALID = "LOCAL_LOGIN_STATE_INVALID"
    LOCAL_LOGIN_STATE_STORAGE_FAILED = "LOCAL_LOGIN_STATE_STORAGE_FAILED"
    LOCAL_LOGIN_STATE_VERSION_UNSUPPORTED = "LOCAL_LOGIN_STATE_VERSION_UNSUPPORTED"
    LEGACY_CREDENTIAL_MIGRATION_REQUIRED = "LEGACY_CREDENTIAL_MIGRATION_REQUIRED"
    CREATOR_REPORT_NOT_READY = "CREATOR_REPORT_NOT_READY"
    STRATEGY_PLAN_NOT_READY = "STRATEGY_PLAN_NOT_READY"
    EXECUTION_PACK_NOT_READY = "EXECUTION_PACK_NOT_READY"
    EXECUTION_TOPIC_INVALID = "EXECUTION_TOPIC_INVALID"
    EXECUTION_RECORD_NOT_READY = "EXECUTION_RECORD_NOT_READY"
    OUTCOME_NOT_READY = "OUTCOME_NOT_READY"
    EXECUTION_NOT_PUBLISHED = "EXECUTION_NOT_PUBLISHED"
    OUTCOME_SNAPSHOT_LIMIT_REACHED = "OUTCOME_SNAPSHOT_LIMIT_REACHED"
    OUTCOME_SNAPSHOT_NOT_FOUND = "OUTCOME_SNAPSHOT_NOT_FOUND"
    OUTCOME_STORAGE_LIMIT_REACHED = "OUTCOME_STORAGE_LIMIT_REACHED"


ERROR_MESSAGES = {
    ErrorCode.INVALID_PROFILE_URL: "主页 URL 无效。",
    ErrorCode.INVALID_AWEME_URL: "作品链接或 aweme_id 无效。",
    ErrorCode.SEC_USER_ID_NOT_FOUND: "无法从主页 URL 提取 sec_user_id。",
    ErrorCode.AWEME_ID_NOT_FOUND: "无法从作品链接提取 aweme_id。",
    ErrorCode.DOUYIN_RISK_CONTROL: "主页扫描失败：疑似被抖音风控。可以配置 DOUYIN_COOKIE，或改用单作品链接/本地视频上传模式。",
    ErrorCode.COOKIE_REQUIRED: "当前请求可能需要 Cookie。请在 .env 中配置 DOUYIN_COOKIE，或使用本地视频上传模式。",
    ErrorCode.COOKIE_INVALID: "Cookie 缺失或失效。请更新 .env 中的 DOUYIN_COOKIE，或使用本地视频上传模式。",
    ErrorCode.DOUYIN_COOKIE_INVALID: "Douyin Cookie 格式无效，已拒绝保存。",
    ErrorCode.DOUYIN_LOGIN_REQUIRED: "Douyin Cookie 缺少有效登录态字段。",
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
    ErrorCode.LLM_RATE_LIMITED: "大模型网关限流，任务已停止；没有继续重试。",
    ErrorCode.LLM_AUTH_FAILED: "大模型鉴权失败。请检查 API Key、API Base 和模型访问权限。",
    ErrorCode.LLM_QUOTA_EXCEEDED: "大模型账户额度或余额不足。请补充额度后再试。",
    ErrorCode.LLM_UPSTREAM_UNAVAILABLE: "大模型上游暂时不可用。已停止当前请求，可稍后人工重试。",
    ErrorCode.LLM_GATEWAY_TIMEOUT: "大模型网关请求超时。已停止当前请求，可稍后人工重试。",
    ErrorCode.LLM_RESPONSE_INVALID: "大模型没有返回合法 JSON。可以降低 LLM_TEMPERATURE，或换用更稳定的多模态模型。",
    ErrorCode.LLM_SETTINGS_INVALID: "大模型时间配置无效。请检查各项范围和总预算约束。",
    ErrorCode.AUTO_ANALYSIS_FAILED: "自动拆解失败。请检查 contact_sheet.jpg 和 keyframes/ 是否已经生成。",
    ErrorCode.ENRICHMENT_FAILED: "素材富化归档失败。请检查素材包文件是否完整。",
    ErrorCode.COMMENTS_IMPORT_FAILED: "评论导入失败。请检查评论文本或 JSON 格式。",
    ErrorCode.PROFILE_SCAN_FAILED: "主页扫描失败。请检查主页 URL / sec_user_id，或改用多作品链接粘贴。",
    ErrorCode.PROFILE_SCAN_NEEDS_FALLBACK: "公开主页未包含可解析作品列表。当前不登录、不使用 Cookie、不绕风控，请改用多作品链接粘贴或单作品解析。",
    ErrorCode.PROFILE_SCAN_API_NOT_CONFIGURED: "已选择 external_api 主页扫描，但 PROFILE_SCAN_API_BASE 未配置。",
    ErrorCode.PROFILE_SCAN_STRUCTURE_CHANGED: "主页返回结构无法归一化，可能是平台页面结构变化。请改用多作品链接粘贴或单作品解析。",
    ErrorCode.UNSUPPORTED_PROFILE_ITEM: "图文 / 照片作品暂不支持生成视频素材包。请先保留在作品池，或改用视频作品生成素材包。",
    ErrorCode.PROFILE_BUILD_QUEUE_LIMIT: "已超过当前作品池富化队列上限。请减少选择数量后重试。",
    ErrorCode.PROFILE_BUILD_ITEM_FAILED: "单条作品生成素材包失败。队列会继续处理后续作品。",
    ErrorCode.ASR_PROVIDER_NOT_CONFIGURED: "ASR provider 尚未配置。后续可接入 faster-whisper、whisper.cpp 或 API ASR。",
    ErrorCode.ASR_FAILED: "语音识别失败。请检查视频音轨、ffmpeg 输出和 ASR 模型配置。",
    ErrorCode.OCR_PROVIDER_NOT_CONFIGURED: "OCR provider 尚未配置。后续可接入 PaddleOCR 或 rapidocr-onnxruntime。",
    ErrorCode.OCR_FAILED: "画面文字识别失败。请检查关键帧是否存在，以及 OCR provider 配置是否正确。",
    ErrorCode.NOT_IMPLEMENTED: "该功能将在后续版本接入，当前版本未启用。",
    ErrorCode.LOCAL_HELPER_FORBIDDEN: "本地助手接口只允许 127.0.0.1 / localhost 调用。",
    ErrorCode.LOCAL_HELPER_TOKEN_INVALID: "本地助手扫描确认已过期或无效，请重新点击按钮确认。",
    ErrorCode.LOCAL_HELPER_CONFIRMATION_REQUIRED: "本地助手动作需要页面确认。请通过页面按钮重新确认后再执行。",
    ErrorCode.HANDOFF_MANIFEST_INVALID: "安全交接包无效。公开网站只接收已声明不含 Cookie、登录 token 和签名 URL 的净化元数据。",
    ErrorCode.HANDOFF_TOKEN_INVALID: "安全交接包导入确认已过期或无效，请重新点击导入交接包。",
    ErrorCode.LOCAL_CHROME_NOT_AVAILABLE: "未检测到本机 Chrome DevTools。请用 remote debugging 模式打开 Chrome 后重试。",
    ErrorCode.LOCAL_CHROME_TAB_NOT_FOUND: "没有找到已打开的抖音主页标签页。请先在 Chrome 中打开目标主页并登录/过验证。",
    ErrorCode.LOCAL_CHROME_SCAN_FAILED: "本机 Chrome 辅助扫描失败。请确认页面已加载作品列表，并且 Chrome DevTools 可连接。",
    ErrorCode.EXTENSION_ID_CONFIGURATION_REQUIRED: "尚未配置允许的 Douyin Login 扩展 ID。请先设置 DOUYIN_LOGIN_EXTENSION_IDS。",
    ErrorCode.LOCAL_LOGIN_STATE_EXTENSION_FORBIDDEN: "当前浏览器扩展未获准访问本机登录状态接口。",
    ErrorCode.LOCAL_LOGIN_PAIR_CODE_INVALID: "配对码无效或已被使用。",
    ErrorCode.LOCAL_LOGIN_PAIR_CODE_EXPIRED: "配对码已过期，请重新生成。",
    ErrorCode.LOCAL_LOGIN_STATE_NOT_PAIRED: "Douyin Login 扩展尚未与本机服务配对。",
    ErrorCode.LOCAL_LOGIN_STATE_AUTH_FAILED: "本机登录状态请求认证失败。",
    ErrorCode.LOCAL_LOGIN_STATE_TIMESTAMP_INVALID: "本机登录状态请求时间戳已失效。",
    ErrorCode.LOCAL_LOGIN_STATE_REPLAY: "检测到重复的本机登录状态请求，已拒绝处理。",
    ErrorCode.LOCAL_LOGIN_STATE_PAYLOAD_TOO_LARGE: "本机登录状态请求超过大小限制。",
    ErrorCode.LOCAL_LOGIN_STATE_INVALID: "本机登录状态数据格式无效。",
    ErrorCode.LOCAL_LOGIN_STATE_STORAGE_FAILED: "本机安全凭据存储不可用。",
    ErrorCode.LOCAL_LOGIN_STATE_VERSION_UNSUPPORTED: "Douyin Login 扩展协议版本不受支持。",
    ErrorCode.LEGACY_CREDENTIAL_MIGRATION_REQUIRED: "检测到旧版明文 Cookie，但无法安全迁移。该 Cookie 已停止使用，请检查本机凭据目录后重试。",
    ErrorCode.CREATOR_REPORT_NOT_READY: "请先完成创作者蒸馏报告。",
    ErrorCode.STRATEGY_PLAN_NOT_READY: "请先生成 Creator Strategy Plan，再选择一个选题生成执行方案。",
    ErrorCode.EXECUTION_PACK_NOT_READY: "当前还没有可用的 Creator Execution Pack。",
    ErrorCode.EXECUTION_TOPIC_INVALID: "选题不存在或已失效，请重新从 Strategy Plan 选择。",
    ErrorCode.EXECUTION_RECORD_NOT_READY: "当前还没有执行记录，请先在 Execution Pack 中点击开始执行。",
    ErrorCode.OUTCOME_NOT_READY: "当前还没有发布结果，请先保存发布信息。",
    ErrorCode.EXECUTION_NOT_PUBLISHED: "请先将执行记录中的“发布”标记为已完成，再记录发布结果。",
    ErrorCode.OUTCOME_SNAPSHOT_LIMIT_REACHED: "当前发布结果已达到 64 条快照上限。",
    ErrorCode.OUTCOME_SNAPSHOT_NOT_FOUND: "没有找到需要修正的数据快照。",
    ErrorCode.OUTCOME_STORAGE_LIMIT_REACHED: "发布结果文件已达到本地存储上限。",
}


@dataclass
class AppError(Exception):
    code: str
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.message:
            self.message = ERROR_MESSAGES.get(self.code, "操作失败。")

    def public_details(self) -> dict[str, Any]:
        allowed = {
            "status_code",
            "content_type",
            "redirected",
            "page_count",
            "item_count",
            "duplicate_count",
            "invalid_item_count",
            "partial",
            "truncated_reason",
            "retry_count",
            "provider",
            "retryable",
            "phase",
            "attempt_index",
            "http_attempt_index",
            "http_attempt_count",
            "response_format_fallback_used",
        }
        payload: dict[str, Any] = {}
        for key in allowed:
            value = self.details.get(key)
            if isinstance(value, bool):
                payload[key] = value
            elif isinstance(value, int):
                payload[key] = value
            elif isinstance(value, str):
                payload[key] = value[:160]
            elif value is None and key in self.details:
                payload[key] = None
        return payload

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"error_code": self.code, "message": self.message}
        diagnostics = self.public_details()
        if diagnostics:
            payload["diagnostics"] = diagnostics
        return payload


def error_message(code: str) -> str:
    return ERROR_MESSAGES.get(code, "操作失败。")


RETRYABLE_LLM_ERROR_CODES = frozenset(
    {
        ErrorCode.LLM_GATEWAY_TIMEOUT,
        ErrorCode.LLM_UPSTREAM_UNAVAILABLE,
        ErrorCode.LLM_RESPONSE_INVALID,
    }
)

NON_RETRYABLE_LLM_ERROR_CODES = frozenset(
    {
        ErrorCode.LLM_NOT_CONFIGURED,
        ErrorCode.LLM_RATE_LIMITED,
        ErrorCode.LLM_AUTH_FAILED,
        ErrorCode.LLM_QUOTA_EXCEEDED,
    }
)

PROMPT_RECOVERY_LLM_ERROR_CODES = frozenset(
    {
        ErrorCode.LLM_NOT_CONFIGURED,
        ErrorCode.LLM_REQUEST_FAILED,
        ErrorCode.LLM_RATE_LIMITED,
        ErrorCode.LLM_AUTH_FAILED,
        ErrorCode.LLM_QUOTA_EXCEEDED,
        ErrorCode.LLM_UPSTREAM_UNAVAILABLE,
        ErrorCode.LLM_GATEWAY_TIMEOUT,
        ErrorCode.LLM_RESPONSE_INVALID,
    }
)


def is_retryable_llm_error(code: str) -> bool:
    return str(code or "") in RETRYABLE_LLM_ERROR_CODES
