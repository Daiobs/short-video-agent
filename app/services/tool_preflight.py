from __future__ import annotations

import importlib.util
import shutil
import sys

from app.config import settings
from app.services.llm_settings import llm_status_payload
from app.services.local_chrome import chrome_helper_diagnostics, local_helper_security_contract


def _binary_status(name: str) -> dict:
    path = shutil.which(name)
    return {
        "id": name,
        "label": name,
        "configured": bool(path),
        "available": bool(path),
        "status": "ready" if path else "missing",
        "message": f"已检测到 {path}" if path else f"未检测到 {name}，素材包抽帧或媒体处理可能失败。",
        "path": path or "",
    }


def _command_or_module_status(
    command_name: str,
    module_name: str,
    *,
    label: str = "",
    install_hint: str = "",
) -> dict:
    path = shutil.which(command_name)
    module = importlib.util.find_spec(module_name)
    if path:
        return {
            "id": command_name,
            "label": label or command_name,
            "configured": True,
            "available": True,
            "status": "ready",
            "message": f"已检测到 {path}",
            "path": path,
            "module": module_name if module else "",
            "run_hint": command_name,
        }
    if module:
        return {
            "id": command_name,
            "label": label or command_name,
            "configured": True,
            "available": True,
            "status": "ready",
            "message": f"已检测到 Python 模块 {module_name}，命令行入口不在 PATH；可使用 {sys.executable} -m {module_name}。",
            "path": "",
            "module": module_name,
            "run_hint": f"{sys.executable} -m {module_name}",
        }
    return {
        "id": command_name,
        "label": label or command_name,
        "configured": False,
        "available": False,
        "status": "missing",
        "message": install_hint or f"未检测到 {command_name} 或 Python 模块 {module_name}。",
        "path": "",
        "module": "",
        "action_hint": install_hint,
    }


def _module_status(
    module_names: list[str],
    *,
    provider: str,
    label: str,
    install_hint: str,
    enable_hint: str = "",
    env_snippet: str = "",
) -> dict:
    disabled = provider in {"", "disabled", "none", "off"}
    found_module = next((name for name in module_names if importlib.util.find_spec(name)), "")
    if disabled:
        return {
            "id": label.lower(),
            "label": label,
            "configured": False,
            "available": bool(found_module),
            "status": "disabled",
            "message": f"{label} 当前关闭。需要自动富化时在 .env 中配置 provider。",
            "provider": provider or "disabled",
            "module": found_module,
            "action_hint": enable_hint,
            "env_snippet": env_snippet,
        }
    if found_module:
        return {
            "id": label.lower(),
            "label": label,
            "configured": True,
            "available": True,
            "status": "ready",
            "message": f"{label} 已配置，检测到 Python 模块 {found_module}。",
            "provider": provider,
            "module": found_module,
        }
    return {
        "id": label.lower(),
        "label": label,
        "configured": True,
        "available": False,
        "status": "missing",
        "message": install_hint,
        "provider": provider,
        "module": "",
        "action_hint": install_hint,
        "env_snippet": env_snippet,
    }


def _required_module_status(module_name: str, *, label: str, install_hint: str) -> dict:
    found = bool(importlib.util.find_spec(module_name))
    return {
        "id": module_name.replace("-", "_"),
        "label": label,
        "configured": True,
        "available": found,
        "status": "ready" if found else "missing",
        "message": f"已检测到 Python 模块 {module_name}。" if found else install_hint,
        "module": module_name if found else "",
        "action_hint": "" if found else install_hint,
    }


def _chrome_status() -> dict:
    diagnostics = chrome_helper_diagnostics()
    launch_hint = diagnostics.get("launch_hint", "")
    if diagnostics.get("ready_for_profile_scan"):
        status = "ready"
        message = diagnostics.get("status_message") or "已检测到可扫描的抖音标签页。"
        action_hint = "可以回到创作者克隆实验室，确认安全边界后点击“本机 Chrome 辅助入口”。"
    elif diagnostics.get("chrome_available"):
        status = "partial"
        message = diagnostics.get("status_message") or "Chrome DevTools 可用，但还没有抖音主页标签页。"
        action_hint = "请在调试 Chrome 中手动打开目标抖音主页；状态检查只匿名统计标签页，读取作品列表仍需回到页面点击“本机 Chrome 辅助入口”确认。"
    else:
        status = "missing"
        message = diagnostics.get("status_message") or "未检测到 Chrome DevTools。"
        action_hint = "请复制下方命令手动启动带 DevTools 的 Chrome；状态检查不会读取作品数据，扫描仍需页面确认。"
    profile_note = diagnostics.get("profile_note") or ""
    return {
        "id": "chrome",
        "label": "本机 Chrome 助手",
        "configured": True,
        "available": bool(diagnostics.get("chrome_available")),
        "status": status,
        "message": f"{message} {profile_note}".strip(),
        "ready_for_profile_scan": bool(diagnostics.get("ready_for_profile_scan")),
        "launch_hint": launch_hint,
        "action_hint": action_hint,
        "env_snippet": launch_hint if launch_hint else "",
        "profile_mode": diagnostics.get("profile_mode", "dedicated"),
        "user_data_dir": diagnostics.get("user_data_dir", ""),
    }


def _local_access_guard_status() -> dict:
    return {
        "id": "local_access_guard",
        "label": "本机访问防护",
        "configured": True,
        "available": True,
        "status": "ready",
        "message": "应用层会拒绝非 loopback 客户端、非本机 Host，以及非本机 Origin / Referer 写操作。",
    }


def _dev_server_binding_status() -> dict:
    dev_server_path = settings.project_root / "scripts" / "dev_server.py"
    try:
        dev_server = dev_server_path.read_text(encoding="utf-8")
    except OSError:
        dev_server = ""
    ready = 'host="127.0.0.1"' in dev_server or "host='127.0.0.1'" in dev_server
    return {
        "id": "dev_server_binding",
        "label": "开发服务监听地址",
        "configured": ready,
        "available": ready,
        "status": "ready" if ready else "missing",
        "message": "开发启动脚本固定监听 127.0.0.1。" if ready else "开发启动脚本没有明确绑定 127.0.0.1，请避免监听 0.0.0.0。",
        "action_hint": "推荐始终使用 python scripts/dev_server.py 启动自用版；不要用 0.0.0.0 暴露本地助手接口。",
    }


def _local_helper_confirmation_status() -> dict:
    return {
        "id": "local_helper_confirmation",
        "label": "助手确认门槛",
        "configured": True,
        "available": True,
        "status": "ready",
        "message": "启动 Chrome、打开主页、扫描主页和清理辅助 profile 都需要一次性 token 和页面确认字段。",
    }


def _handoff_bridge_status() -> dict:
    return {
        "id": "handoff_bridge",
        "label": "安全交接包",
        "configured": True,
        "available": True,
        "status": "ready",
        "message": "handoff_manifest 导入需要一次性 token；公开网站只接收净化后的作品列表和元数据，不接收 Cookie、登录 token、签名 URL 或原始请求头。",
        "action_hint": "本机助手扫描后下载 handoff_manifest.json，再在网页的 handoff_manifest 安全交接包导入区粘贴。",
    }


def _public_bridge_boundary_status() -> dict:
    contract = local_helper_security_contract()
    ready = (
        contract.get("loopback_only") is True
        and contract.get("public_site_cookie_free") is True
        and contract.get("requests_from_user_machine") is True
        and contract.get("cookie_read") is False
        and contract.get("cookie_returned") is False
        and contract.get("cookie_logged") is False
        and contract.get("login_token_returned") is False
        and contract.get("signed_media_url_returned") is False
        and contract.get("raw_headers_returned") is False
        and contract.get("dom_visible_metadata_only") is True
        and contract.get("sensitive_fields_redacted") is True
    )
    return {
        "id": "public_bridge_boundary",
        "label": "公开站 / 本机助手边界",
        "configured": ready,
        "available": ready,
        "status": "ready" if ready else "missing",
        "message": "公开网站只接收净化后的账号素材清单；Cookie、登录 token、签名媒体 URL 和原始请求头不会进入交接包。",
        "action_hint": "用户本机插件/助手使用本机 Chrome 登录态和本机 IP 请求平台，再把安全交接包交给网页继续分析。",
        "contract_summary": [
            "请求由用户本机 Chrome / 本机 IP 发起",
            "本地服务只允许 127.0.0.1 / localhost",
            "每次启动、打开主页、扫描和清理辅助 profile 都需要页面确认 + 一次性 token",
            "公开站只接收作品列表、可见互动指标和净化后的来源链接",
            "不读取、不返回、不记录 Cookie / 登录 token / 签名媒体 URL / 原始请求头",
        ],
    }


def _runtime_outputs_gitignore_status() -> dict:
    gitignore_path = settings.project_root / ".gitignore"
    try:
        gitignore = gitignore_path.read_text(encoding="utf-8")
    except OSError:
        gitignore = ""
    required = [
        "outputs/creator_clones/*",
        "outputs/local_chrome_profile/*",
        "samples/",
    ]
    missing = [item for item in required if item not in gitignore]
    ready = not missing
    return {
        "id": "runtime_outputs_gitignore",
        "label": "运行产物忽略",
        "configured": ready,
        "available": ready,
        "status": "ready" if ready else "missing",
        "message": "本地采集 / 蒸馏产物已加入 .gitignore。" if ready else f".gitignore 缺少：{', '.join(missing)}",
        "missing": missing,
    }


def preflight_status_payload() -> dict:
    llm = llm_status_payload()
    checks = [
        _chrome_status(),
        _required_module_status(
            "websocket",
            label="Chrome DevTools websocket",
            install_hint="缺少 websocket-client，本机 Chrome 辅助扫描无法连接 DevTools。请运行 python -m pip install -r requirements.txt。",
        ),
        _command_or_module_status(
            "yt-dlp",
            "yt_dlp",
            label="yt-dlp",
            install_hint="未检测到 yt-dlp。请运行 python -m pip install -r requirements.txt；它用于后续公开视频解析 / 下载能力。",
        ),
        _binary_status("ffmpeg"),
        _binary_status("ffprobe"),
        _module_status(
            ["faster_whisper"],
            provider=settings.asr_provider,
            label="ASR",
            install_hint="ASR 已配置但未安装 faster-whisper。请安装 requirements-asr.txt，或将 ASR_PROVIDER 设为 disabled。",
            enable_hint="已安装 faster-whisper 时，可在 .env 中设置 ASR_PROVIDER=auto 后重启服务。首次运行可能下载 Whisper 模型。",
            env_snippet="ASR_PROVIDER=auto\nASR_MODEL_SIZE=base\nASR_LANGUAGE=zh",
        ),
        _module_status(
            ["rapidocr_onnxruntime", "rapidocr"],
            provider=settings.ocr_provider,
            label="OCR",
            install_hint="OCR 已配置但未安装 rapidocr-onnxruntime。请安装 requirements-ocr.txt，或将 OCR_PROVIDER 设为 disabled。",
            enable_hint="已安装 rapidocr-onnxruntime 时，可在 .env 中设置 OCR_PROVIDER=auto 后重启服务。",
            env_snippet="OCR_PROVIDER=auto\nOCR_LANGUAGE=ch\nOCR_MAX_FRAMES=12",
        ),
        {
            "id": "llm",
            "label": "大模型拆解",
            "configured": bool(llm.get("configured")),
            "available": bool(llm.get("configured")),
            "status": "ready" if llm.get("configured") else "disabled",
            "message": llm.get("status_message") or "未配置 LLM，仍可生成素材包和手动 prompt。",
            "provider": llm.get("provider", ""),
            "model": llm.get("model", ""),
        },
        _local_access_guard_status(),
        _dev_server_binding_status(),
        _local_helper_confirmation_status(),
        _public_bridge_boundary_status(),
        _handoff_bridge_status(),
        _runtime_outputs_gitignore_status(),
    ]
    ready_count = sum(1 for item in checks if item["status"] == "ready")
    missing_count = sum(1 for item in checks if item["status"] == "missing")
    disabled_count = sum(1 for item in checks if item["status"] == "disabled")
    return {
        "checks": checks,
        "summary": {
            "ready_count": ready_count,
            "missing_count": missing_count,
            "disabled_count": disabled_count,
            "total_count": len(checks),
        },
    }
