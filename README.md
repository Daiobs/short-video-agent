# short-video-agent

本项目是一个本地短视频爆款分析素材包生成器，不是抖音下载器。

当前目标是把已授权的本地视频或单条抖音作品整理成稳定、可复用、可扩展的自动拆解工作流：解析作品元数据、下载视频用于抽帧、生成素材包、调用大模型自动拆解，并输出选题/脚本/分镜所需的结构化结果。

## 合规和使用边界

- 本工具仅用于本地学习、复盘和内容分析。
- 用户需要自行确保拥有相关内容的分析、下载或使用权限。
- 不得用于批量搬运、盗链分发、绕过平台风控、绕过验证码、破解签名、非法抓取或商业化分发。
- 第一版不做公开 SaaS。
- 第一版不实现绕验证码、绕风控、破解签名、伪装真实用户行为等功能。
- 如果后续抖音接口被风控，系统应返回明确错误，并建议改用本地上传或已授权素材。
- 不要把 Cookie 写进日志、素材包或 Git 仓库。

## 当前功能

- FastAPI 本地 Web 页面。
- SQLite 本地数据库。
- 页面主入口：单作品链接 / aweme_id 导入。
- 本地视频上传后端接口仍保留，作为兜底能力和测试入口；当前首页暂不展示。
- 抖音 native mobile feed/share 优先解析，网页 detail 作为兜底；通常不需要 Cookie，当前不使用 KuKuTool。
- 清晰度偏好在页面设置区统一配置，主流程不展示候选直链。
- 同清晰度 CDN 候选会做轻量 Range 测速，默认选择响应更快的 host。
- 单作品主流程已串联为：解析候选 → 下载视频 → 自动生成素材包 → 自动调用大模型拆解。
- 素材包分析视图：`/cases/{case_id}` 可查看 contact sheet、关键帧时间线、分类分析镜头、AI 自动拆解报告、analysis_input，并可重跑 AI 拆解。
- 内容类型拆解：支持美拍/COS、鸡汤/情绪价值、教学/教程、剧情/反转、种草/带货、知识/观点、强视觉吸引/尺度边界和通用短视频。
- candidate_id 缓存：前端不接触真实下载 URL。
- 安全下载：下载前校验 HTTPS、allowlist host、Content-Type、Content-Length 和跳转 host。
- BackgroundTasks + SQLite Job 状态。
- ffprobe 生成视频技术参数。
- ffmpeg 抽取关键帧。
- contact sheet 关键帧总览图。
- 固定目录结构的素材包。
- `analysis_input.json`、按内容类型生成的 `prompt.md` 模板、AI 输出的 `analysis_result.json` 和 `analysis_report.md`。

当前不包含：

- 真实抖音主页扫描；
- ZIP 导出；
- TTS；
- 自动字幕；
- MP4 合成；
- 自动发布。

这些内容按后续阶段接入。

## 环境要求

- Python 3.10+
- ffmpeg
- ffprobe

macOS 可使用：

```bash
brew install ffmpeg
```

## 安装

```bash
cd /Users/xingkong/Documents/code/short-video-agent
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

如果本机默认 `python3` 低于 3.10，请改用 PyCharm 或其他 Python 3.10+ 解释器。

## 运行

```bash
python scripts/dev_server.py
```

打开：

```text
http://127.0.0.1:8765/
```

开发启动脚本默认开启 `reload=True`，并监听 `app/` 目录。修改 Python 路由、服务、模型等模块后，Uvicorn 会自动重启进程；如果只改静态文件或模板，刷新浏览器即可。

## 配置

`.env.example`:

```text
DOUYIN_COOKIE=
MAX_VIDEO_SIZE_MB=500
ALLOWED_CDN_HOSTS=365yg.com,douyinvod.com,snssdk.com,zjcdn.com,douyin.com
OUTPUT_DIR=outputs
DOWNLOAD_TIMEOUT_SECONDS=60
QUALITY_CACHE_TTL_SECONDS=1800
CANDIDATE_PROBE_ENABLED=true
CANDIDATE_PROBE_TIMEOUT_SECONDS=1.2
CANDIDATE_PROBE_MAX_CANDIDATES=3
KEYFRAME_MAX_COUNT=30
KEYFRAME_INTERVAL_SECONDS=1
LLM_PROVIDER=disabled
LLM_API_BASE=https://api.openai.com/v1
LLM_API_KEY=
LLM_MODEL=
LLM_TIMEOUT_SECONDS=90
LLM_TEMPERATURE=0.2
LLM_MAX_KEYFRAMES=6
```

单作品解析优先使用 native mobile feed/share，不需要 Cookie；网页 detail/page 兜底会在配置存在时附带 `DOUYIN_COOKIE`，但不会写入日志、数据库或素材包。如果所有路线都被限制，接口会返回明确错误。

`CANDIDATE_PROBE_*` 只在同一档清晰度存在多个 CDN host 时生效。它会用 Range 请求读取少量字节并排序，不会为了测速降低清晰度。

AI 自动拆解默认关闭。配置大模型时：

- `LLM_PROVIDER=openai_compatible`
- `LLM_API_BASE` 填兼容 `/chat/completions` 的 API 地址
- `LLM_API_KEY` 填你的 API Key
- `LLM_MODEL` 填支持图片输入的多模态模型

未配置时，主流程仍会完成下载和素材包生成，并在 case 页面提示“大模型 API 未配置”。配置后可以在 case 页面点击“开始 AI 自动拆解”，也可以重新跑单作品主流程自动生成 `analysis_result.json` 和 `analysis_report.md`。

## 素材包结构

每个素材包生成在：

```text
outputs/cases/{case_id}/
```

目录内容：

```text
video.mp4
metadata.json
qualities.json
ffprobe.json
analysis_input.json
prompt.md
analysis_result.json
analysis_report.md
worksheet.json
analysis_brief.md
README.md
contact_sheet.jpg
keyframes/
```

`analysis_input.json` 是交给大模型的结构化输入；`prompt.md` 是按内容类型生成的爆款案例拆解模板。

`analysis_result.json` 是大模型自动拆解后的结构化结果；`analysis_report.md` 是对应的可读报告。它们是自动 workflow 的核心产物。

`worksheet.json` 是本地人工拆解工作表，用于记录你对前 3 秒钩子、内容结构、类型判断和复刻方案的人工判断。`analysis_brief.md` 是工作表的 Markdown 版本，适合直接复制给 LLM、沉淀到笔记，或在后续 Agent 工作流中作为输入。

生成素材包后，可以打开：

```text
http://127.0.0.1:8765/cases/{case_id}
```

分析视图会展示关键帧总览图、基础信息、内容类型、分析镜头、关键问题、内容占比、AI 自动拆解报告、人工修正工作表、`prompt.md`、`analysis_report.md`、`analysis_brief.md` 和 `analysis_input.json`。

推荐使用方式：

1. 在 `.env` 配置支持图片输入的大模型 API。
2. 输入单条作品链接，点击“按设置下载并自动拆解”。
3. 系统自动生成素材包，并调用大模型生成 `analysis_result.json` 和 `analysis_report.md`。
4. 打开 case 页面查看 AI 自动拆解结果。
5. 如需修正，再填写“我的拆解工作表”，保存成人工修正版 `analysis_brief.md`。

如果自动推断的内容类型不合适，可以在分析页手动切换，例如：

- 美拍 / COS / 颜值向：优先看第一眼吸引、妆造、姿态、光线和人设。
- 鸡汤 / 情绪价值：优先看情绪痛点、金句密度、情绪路径和评论触发。
- 教学 / 教程：优先看痛点承诺、步骤清晰度、结果证明和收藏理由。
- 剧情 / 反转：优先看冲突、悬念、信息差和结尾反转。
- 种草 / 带货：优先看需求场景、卖点证明、信任证据和转化路径。
- 知识 / 观点：优先看观点强度、论证结构、例子和讨论性。
- 强视觉吸引 / 尺度边界：优先看视觉吸引点、平台风险和可替代表达。

下载视频只用于本地抽帧、ffprobe 和 contact sheet；标题、作者、点赞、评论、分享、发布时间等作品信息以链接解析到的平台元数据为准。若平台响应缺失这些字段，页面会保留为空或 0，后续可人工补充。

## API

当前可用接口：

- `GET /`
- `POST /api/import/local-video`
- `POST /api/jobs/build-case`
- `GET /api/jobs/{job_id}`
- `POST /api/cases/build`
- `GET /cases/{case_id}`
- `GET /api/cases/{case_id}`
- `POST /api/cases/{case_id}/analysis-category`
- `POST /api/cases/{case_id}/worksheet`
- `GET /api/cases/{case_id}/contact-sheet`
- `POST /api/videos/import-single`
- `POST /api/videos/qualities`
- `POST /api/downloads`
- `POST /api/jobs/resolve-qualities`
- `POST /api/jobs/download`
- `POST /api/jobs/download-and-build-case`
- `POST /api/jobs/download-build-analyze-case`
- `POST /api/jobs/analyze-case`

占位接口：

- `POST /api/profile/scan`
- `POST /api/jobs/profile-scan`

占位接口会返回 `NOT_IMPLEMENTED`，不假装成功。

## 错误码

已接入：

- `LOCAL_UPLOAD_FAILED`
- `INVALID_VIDEO_FILE`
- `FFMPEG_NOT_FOUND`
- `FFPROBE_FAILED`
- `KEYFRAME_EXTRACT_FAILED`
- `CASE_BUILD_FAILED`
- `NOT_IMPLEMENTED`
- `AWEME_ID_NOT_FOUND`
- `DOUYIN_RISK_CONTROL`
- `COOKIE_REQUIRED`
- `QUALITY_NOT_FOUND`
- `URL_EXPIRED`
- `HOST_NOT_ALLOWED`
- `REDIRECT_HOST_NOT_ALLOWED`
- `CONTENT_TYPE_INVALID`
- `CONTENT_LENGTH_TOO_LARGE`
- `DOWNLOAD_TIMEOUT`
- `DOWNLOAD_FAILED`
- `LLM_NOT_CONFIGURED`
- `LLM_REQUEST_FAILED`
- `LLM_RESPONSE_INVALID`
- `AUTO_ANALYSIS_FAILED`

下载、主页扫描、Provider 相关错误码已集中定义在 `app/errors.py`，后续接入真实功能时复用。

## 测试

```bash
pytest -q
```

测试不依赖真实抖音接口，也不调用 KuKuTool。

## 后续路线

- P2：抖音主页 HTTP 扫描、Top N 点赞排序、作品表格、排序切换。
- P3：ZIP 导出、完整错误提示、README 扩展、下载安全测试补齐。
