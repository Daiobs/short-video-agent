# short-video-agent

本项目是一个本地短视频爆款分析素材包生成器，不是抖音下载器。

当前目标是把已授权的本地视频或单条抖音作品整理成稳定、可复用、可扩展的分析输入包：解析作品元数据、下载视频用于抽帧、生成素材包；配置大模型后，可在 case 页面自动拆解并输出选题/脚本/分镜所需的结构化结果。

## 合规和使用边界

- 本工具仅用于本地学习、复盘和内容分析。
- 用户需要自行确保拥有相关内容的分析、下载或使用权限。
- 不得用于批量搬运、盗链分发、绕过平台风控、绕过验证码、破解签名、非法抓取或商业化分发。
- 第一版不做公开 SaaS。
- 第一版不实现绕验证码、绕风控、破解签名、伪装真实用户行为等功能。
- 如果后续抖音接口被风控，系统应返回明确错误，并建议改用本地上传或已授权素材。
- 不要把 Cookie 写进日志、素材包或 Git 仓库。

## 当前主路径

第一次使用时，只需要理解三件事：

1. 首页输入单条作品链接或 aweme_id，生成本地素材包。
2. 没有 API Key 也能生成 `video.mp4`、`contact_sheet.jpg`、`keyframes/`、`analysis_input.json` 和 `prompt.md`。
3. 配置大模型后，可以在 case 页面点击“开始 AI 自动拆解 / 重新分析”，生成 `analysis_result.json` 和 `analysis_report.md`。

## 业务模块规划

项目未来会拆成两个一级主功能：

1. 单作品解析：当前可用。围绕一条视频完成链接输入、解析、下载、生成素材包、AI 拆解和 case 查看。
2. 主页扫描：P2.0 当前可用。用于输入主页 URL / sec_user_id 或粘贴多条作品链接，整理作品列表、排序和账号概览，再复用“单作品解析”的素材包与 AI 拆解流程。

当前阶段的主页扫描是“作品列表获取壳”：默认不使用 Cookie、不登录、不绕风控；公开主页如果无法解析，会提示改用多作品链接粘贴或单作品解析。主页扫描不自动批量下载，也不自动批量 AI 拆解；后续下载、素材包和拆解都复用单作品流程。

主页扫描已知限制：

- 部分抖音主页即使 URL 有效，公开 HTTP 请求也只会返回浏览器校验脚本，例如包含 `_$jsvmprt`、`byted_acrawler`、`__ac_nonce` 或验证码标记。此时系统会返回 `DOUYIN_RISK_CONTROL`。
- `DOUYIN_RISK_CONTROL` 代表平台没有返回公开作品列表，不是主页 URL 格式错误，也不是图文/照片作品导致。
- 当前项目边界是不登录、不使用 Cookie、不绕风控；遇到该错误时，推荐改用“多作品链接粘贴”或“单作品解析”继续生成素材包。
- 后续如果确认要增强账号级扫描，可以单独评估 Cookie 模式、浏览器导出模式或授权数据源，但这会改变当前的合规和实现边界。

核心功能：

- FastAPI 本地 Web 页面。
- SQLite 本地数据库。
- 页面主入口：单作品解析。
- 抖音 native mobile feed/share 优先解析，网页 detail 作为兜底；通常不需要 Cookie，当前不使用 KuKuTool。
- 清晰度偏好在右上角设置弹窗中统一配置，主流程不展示候选直链。
- 同清晰度 CDN 候选会做轻量 Range 测速，默认选择响应更快的 host。
- 单作品主流程已收敛为一个“解析”按钮：解析候选 → 下载视频 → 自动生成素材包；配置大模型后可自动拆解。
- 主页扫描可整理作品列表，支持点赞、评论、分享、综合分和发布时间排序，并显示基础账号概览。
- 解析结果区会先展示本地拆解底稿：规则判断内容类型、命中原因、优先观察点、关键问题和内容占比，再继续展示 AI 摘要。
- 右上角设置弹窗可查看 AI 是否配置，并可测试连接。
- Case 页面默认展示创作者可读报告；素材包、`prompt.md`、`analysis_input.json`、人工验收、富化数据和质量校准功能收纳在“高级 / 后台材料”中。
- candidate_id 缓存：前端不接触真实下载 URL。
- 安全下载：下载前校验 HTTPS、allowlist host、Content-Type、Content-Length 和跳转 host。
- BackgroundTasks + SQLite Job 状态。
- ffprobe 生成视频技术参数。
- ffmpeg 抽取关键帧。
- contact sheet 关键帧总览图。
- 固定目录结构的素材包。

实验 / 高级能力：

- 内容类型拆解：美拍/COS、鸡汤/情绪价值、教学/教程、剧情/反转、种草/带货、知识/观点、强视觉吸引/尺度边界和通用短视频。
- 富化层 enrichment：在同一个 case 目录下补齐评论导入、指标快照、结构化索引，并预留 ASR / OCR 标准目录。
- 可选本地 ASR：启用 `faster-whisper` 后，可为 case 生成 `audio.wav`、`transcript.json`、`transcript.srt` 和 `transcript.txt`。
- 可选本地 OCR：启用 `rapidocr` 后，可识别关键帧和底部字幕区文字，并生成 `frame_ocr.json`、`subtitle_ocr.json`、`cover_ocr.json`。
- 人工质量验收和质量校准样本库：用于后续调 prompt、调质量闸门和沉淀回归样本，不是第一步必须理解的主流程。

当前不包含：

- 批量下载主页全部作品；
- 账号级 AI 策略报告；
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

ASR 是可选重依赖，默认不安装。需要本地语音识别时再安装：

```bash
python -m pip install -r requirements-asr.txt
```

OCR 也是可选依赖，需要画面文字识别时再安装：

```bash
python -m pip install -r requirements-ocr.txt
```

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
ASR_PROVIDER=disabled
ASR_MODEL_SIZE=base
ASR_DEVICE=auto
ASR_COMPUTE_TYPE=default
ASR_LANGUAGE=zh
ASR_BEAM_SIZE=5
OCR_PROVIDER=disabled
OCR_LANGUAGE=ch
OCR_MAX_FRAMES=12
OCR_SUBTITLE_CROP_RATIO=0.35
```

单作品解析优先使用 native mobile feed/share，不需要 Cookie；网页 detail/page 兜底会在配置存在时附带 `DOUYIN_COOKIE`，但不会写入日志、数据库或素材包。如果所有路线都被限制，接口会返回明确错误。

`CANDIDATE_PROBE_*` 只在同一档清晰度存在多个 CDN host 时生效。它会用 Range 请求读取少量字节并排序，不会为了测速降低清晰度。

AI 自动拆解默认关闭。默认 `LLM_PROVIDER=disabled` 时，系统不会自动调用任何大模型；主流程只会生成素材包。官方 OpenAI API 建议使用 Responses API：

```env
LLM_PROVIDER=openai_responses
LLM_API_BASE=https://api.openai.com/v1
LLM_API_KEY=你的 OpenAI API Key
LLM_MODEL=gpt-5.5
```

如果使用 WinToken 或其他 OpenAI-compatible 中转站，并且它们只提供 `/chat/completions`：

```env
LLM_PROVIDER=openai_compatible
LLM_API_BASE=https://www.wintoken.dev/v1
LLM_API_KEY=中转站控制台生成的 API Key
LLM_MODEL=gpt-5.5
```

如果使用 WinToken 或其他 Anthropic Messages 协议中转站，并且它们提供 `/messages`：

```env
LLM_PROVIDER=anthropic_compatible
LLM_API_BASE=https://www.wintoken.dev
LLM_API_KEY=中转站控制台生成的 API Key
LLM_MODEL=claude-fable-5
```

兑换码额度不是 API Key。通常需要先在对应站点把兑换码充值到账户，再在控制台生成可调用的 API Key。
WinToken 已验证可通过 `https://www.wintoken.dev/v1/chat/completions` 或 `https://www.wintoken.dev/v1/messages` 调用，具体取决于模型所属协议；如果某个模型返回 `model_not_found`、401 或“无可用渠道”，请在控制台确认当前 Key 可调用的协议和模型名。

通用要求：

- `LLM_PROVIDER` 可选 `openai_responses` / `responses` / `openai_compatible` / `anthropic_compatible`
- `LLM_API_BASE` 填 API Base，例如 `https://api.openai.com/v1`
- `LLM_API_KEY` 填你的 API Key
- `LLM_MODEL` 填支持图片输入的多模态模型

当前支持官方 OpenAI Responses API、OpenAI-compatible `/chat/completions` 和 Anthropic-compatible `/messages`。AI 自动拆解会把 `contact_sheet.jpg` 和部分关键帧作为图片输入发送给模型，因此建议使用支持图片输入的多模态模型。如果模型不支持图片，可能只能分析标题、元数据和 Prompt，视觉拆解会不准确。

API Key 只放在本地 `.env`，不要提交到 Git；`.env` 已在 `.gitignore` 中排除。接口和页面只显示 API Key 是否存在或脱敏值，不会返回完整 Key。

修改 `.env` 后需要重启本地服务，运行中的 FastAPI 进程才会重新读取配置。

如果浏览器能访问 API 但页面“测试连接”失败，请检查本机代理；当前后端请求可能不会读取系统代理环境变量。

本地 ASR 默认关闭。安装 `requirements-asr.txt` 后，可以启用：

```env
ASR_PROVIDER=faster_whisper
ASR_MODEL_SIZE=base
ASR_DEVICE=auto
ASR_COMPUTE_TYPE=default
ASR_LANGUAGE=zh
```

首次运行 faster-whisper 可能需要下载模型，耗时取决于网络和模型大小。未安装依赖或未启用时，ASR 接口会返回 `ASR_PROVIDER_NOT_CONFIGURED`，但不会影响下载、抽帧、富化归档和 AI 拆解。

本地 OCR 默认关闭。安装 `requirements-ocr.txt` 后，可以启用：

```env
OCR_PROVIDER=rapidocr
OCR_LANGUAGE=ch
OCR_MAX_FRAMES=12
OCR_SUBTITLE_CROP_RATIO=0.35
```

OCR 会优先识别关键帧全图和底部字幕区。`OCR_MAX_FRAMES` 控制最多识别多少张关键帧，避免长视频一次处理过慢。未安装依赖或未启用时，OCR 接口会返回 `OCR_PROVIDER_NOT_CONFIGURED`。

未配置时，主流程仍会完成下载和素材包生成，并在首页与 case 页面提示“AI 自动拆解未配置”。配置后可以：

1. 在右上角设置弹窗点击“测试连接”，确认模型能返回合法 JSON。
2. 在 case 页面点击“开始 AI 自动拆解 / 重新分析”。
3. 在 case 页面重新分析，生成 `analysis_result.json` 和 `analysis_report.md`。

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
enrichment/
  manifest.json
  asr/
  ocr/
  comments/
  metrics/
  indexes/
```

文件作用：

- `video.mp4`：下载或导入后的本地视频副本，用于抽帧和视觉复盘。
- `metadata.json`：标题、作者、来源链接、互动数据和导入备注等基础信息。
- `qualities.json`：视频清晰度候选记录；本地上传模式会标记为 `local`。
- `ffprobe.json`：ffprobe 读取到的视频参数，包括时长、分辨率、编码、码率和文件大小。
- `contact_sheet.jpg`：关键帧总览图，用于快速查看视频节奏和画面变化。
- `keyframes/`：按时间抽取的关键帧图片，适合交给多模态模型做视觉拆解。
- `analysis_input.json`：交给大模型的结构化输入，聚合元数据、视频参数、关键帧路径、分析重点和 `analysis_enrichment` 富化摘要。
- `prompt.md`：可复制给 ChatGPT / Claude / Gemini 的人工分析 Prompt。
- `worksheet.json`：用户手动拆解工作表，保存人工观察和二次判断。
- `analysis_brief.md`：人工工作表生成的简洁 Markdown 摘要。
- `analysis_result.json`：大模型返回的结构化拆解结果。
- `analysis_report.md`：大模型拆解结果渲染后的可读 Markdown 报告。
- `enrichment/manifest.json`：富化层总清单，记录 ASR、OCR、评论、指标和索引状态。
- `enrichment/comments/comments_raw.jsonl`：用户导入的原始评论记录，便于追加和追溯。
- `enrichment/comments/comments_clean.jsonl`：清洗后的评论 JSONL。
- `enrichment/comments/comment_summary.json`：评论高频词、用户需求和评论区钩子摘要。
- `enrichment/metrics/snapshots.jsonl`：点赞、评论、分享等指标快照。
- `enrichment/indexes/case_index.json`：给检索、批处理和后续 Agent 使用的结构化索引。
- `enrichment/asr/`：语音识别目录。未配置时只写入 provider 状态；启用后可生成以下文件。
- `enrichment/asr/audio.wav`：从 `video.mp4` 抽出的 16k 单声道音频。
- `enrichment/asr/transcript.json`：带时间戳的结构化转写结果。
- `enrichment/asr/transcript.srt`：用于回看和剪辑对齐的字幕文件。
- `enrichment/asr/transcript.txt`：纯文本转写内容，适合进入后续 LLM 分析。
- `enrichment/ocr/`：画面文字识别目录。未配置时只写入 provider 状态；启用后可生成以下文件。
- `enrichment/ocr/frame_ocr.json`：关键帧全图 OCR 结果。
- `enrichment/ocr/subtitle_ocr.json`：关键帧底部字幕区 OCR 结果。
- `enrichment/ocr/cover_ocr.json`：封面替代帧 OCR 结果；当前使用第一张关键帧作为封面代理。
- `enrichment/ocr/crops/`：底部字幕区裁剪图，便于回看 OCR 来源。

## 进阶用法：单条作品拆解质量闭环

质量校准、ASR、OCR、评论和指标快照属于实验 / 高级能力，不是第一次使用项目必须理解的主路径。当前阶段重点不是批量生产，而是把一条作品拆准、拆透、可复盘。需要做深度校准时，推荐按以下顺序使用：

1. 输入单条作品链接，先生成素材包。
2. 打开 `/cases/{case_id}`，默认先看上方创作者可读报告。需要深度调试时，展开“高级 / 后台材料”。
3. 在高级区的“质量校准：诊断 / rerun_plan / 样本库”中查看“拆解诊断”，确认这份拆解当前能不能用、阻塞在哪里、下一步最该做什么。诊断卡会把最合适的推荐动作放在第一位；安全动作会直接执行，例如开始 AI 拆解、保存反馈并重跑、保存校准样本，需要人工填写的动作只会定位到对应输入区。
4. 再看“拆解准备度”，确认基础素材、ASR、OCR、评论、指标和拆解产出是否齐全。
5. 查看“拆解质量校准”，它会合并 AI 自检、人工验收、准备度缺口和下一步动作。
6. 在“人工验收与工作表”中的“人工质量验收”里标记这份报告是否可信：
   - 总结是否符合视频；
   - 证据是否足够；
   - 可复刻点是否有用；
   - 分镜表是否可执行；
   - 发布包是否可用。
7. 如果结论是 `需要修正` 或 `不通过`，填写具体原因和下一步处理，例如“评论证据不足”“分镜表凭空扩展”“发布包不可直接执行”。
8. 点击“保存并重新拆解”或“重新 AI 自动拆解”。系统会把 `quality_acceptance.json` 中的人工反馈带入下一次 prompt，避免重复输出已经被人工指出的问题。
9. 点击“保存校准样本”，生成 `quality_calibration_record.json`，并更新 `outputs/calibration/quality_calibration_index.json`。
10. 打开 `/calibration` 查看校准样本库，按校准状态、人工结论、内容类型和关键词筛选样本。
11. 在校准样本库中查看“常见质量问题”，判断问题是否集中在 ASR/OCR/评论缺失、AI 自检缺口、人工阻塞项或下一步动作。
12. 使用“复制对比报告”或“下载对比报告”导出当前筛选结果的 Markdown，用于复盘一批样本的系统性问题。

质量相关文件：

- `quality_acceptance.json`：人工质量验收表，记录真实样例下 AI 拆解是否可信。
- `quality_calibration_record.json`：单条作品校准样本，汇总 AI 自检、人工验收、准备度、顶部诊断快照和下一步修正建议。
- `rerun_plan.json`：下一轮拆解任务单，汇总当前诊断、人工反馈、缺失证据、重跑约束和推荐动作，可直接交给外部模型或人工复盘。
- `rerun_plan.md`：`rerun_plan.json` 的人类可读版本，包含执行闸门、阻塞原因、下一步首选动作和证据计划。
- `analysis_result.json.manual_review_context.rerun_strategy`：带反馈重跑策略，把人工验收阻塞项、禁止重复的问题、必须核对的 ASR/OCR/评论证据和输出要求整理成下一次 AI 拆解的硬约束。
- `analysis_result.json.enrichment_coverage`：核对 ASR、OCR、评论是否真正进入对应拆解模块，区分“已使用”“可用未使用”“有洞察无证据”“已检测为空”等状态。
- `/api/cases/{case_id}.case_diagnosis`：页面顶部诊断卡的数据来源，聚合质量分、准备度、富化阻塞、人工阻塞、关键问题和下一步动作。
- `outputs/calibration/quality_calibration_index.json`：跨 case 的本地校准样本索引。该目录属于运行时产物，已被 `.gitignore` 忽略。

质量状态含义：

- `needs_ai_analysis`：素材包已生成，但还没有 AI 自动拆解报告。
- `awaiting_review`：AI 已拆解，但还没有人工验收。
- `needs_rerun`：人工验收指出问题，需要带反馈重跑。
- `accepted`：人工验收通过，可以作为正样本沉淀。

这套闭环的目标是让每条作品都留下“AI 怎么拆、人工怎么看、下一次怎么修”的证据链。后续调 prompt、调质量闸门或换模型时，可以用校准样本库做回归基准。

生成素材包后，可以打开：

```text
http://127.0.0.1:8765/cases/{case_id}
```

首页会在任务完成后直接展示关键帧总览、基础信息和 case 入口，不强制跳转。配置大模型并运行 AI 自动拆解后，完整分析视图会展示 `analysis_report.md`；高级区域还包含内容类型、分析镜头、关键问题、内容占比、人工修正工作表、`analysis_brief.md` 等进阶信息。

即使不配置 API，也可以在 case 页面复制 `prompt.md`，下载 `analysis_input.json`，再手动把它们交给 ChatGPT / Claude / Gemini 分析。`analysis_input.json` 会在读取时刷新 `analysis_enrichment`，把 ASR 转写、OCR 文字、评论摘要和指标快照合并为紧凑输入。

推荐使用方式：

1. 在 `.env` 配置支持图片输入的大模型 API。
2. 输入单条作品链接，点击“解析”。
3. 系统自动解析候选、下载视频并生成素材包；需要自动拆解时，在 case 页面点击“开始 AI 自动拆解”。
4. 打开 case 页面查看 AI 自动拆解结果。页面会把报告拆成钩子、视觉、文案、口播、OCR、评论、复刻方案、发布包等卡片，便于直接复盘和执行。
5. 如需修正，再填写“我的拆解工作表”，保存成人工修正版 `analysis_brief.md`。

如果已运行 ASR / OCR / 评论导入，AI 自动拆解会优先结合：

- `asr.full_text` 和带时间戳 segments：判断口播钩子、金句、脚本结构。
- `ocr.frame_text` / `ocr.subtitle_text` / `ocr.cover_text`：判断封面承诺、画面字幕和文字节奏。
- `comments.top_needs` / `comment_hooks` / `top_comments`：判断用户真实反馈、互动钩子和可复刻评论区设计。
- `metrics.latest_snapshot`：记录当前互动指标来源，避免把缺失数据误判成真实表现。

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
- `GET /calibration`
- `POST /api/import/local-video`
- `POST /api/jobs/build-case`
- `GET /api/jobs/{job_id}`
- `POST /api/cases/build`
- `GET /cases/{case_id}`
- `GET /api/cases/{case_id}`
- `POST /api/cases/{case_id}/analysis-category`
- `POST /api/cases/{case_id}/worksheet`
- `POST /api/cases/{case_id}/quality-acceptance`
- `POST /api/cases/{case_id}/quality-calibration/record`
- `GET /api/cases/quality-calibration/records`
- `GET /api/cases/quality-calibration/report`
- `GET /api/cases/{case_id}/contact-sheet`
- `GET /api/cases/{case_id}/analysis-input`
- `GET /api/cases/{case_id}/enrichment`
- `POST /api/cases/{case_id}/archive/enrich`
- `POST /api/cases/{case_id}/comments/import`
- `POST /api/cases/{case_id}/metrics/snapshot`
- `POST /api/cases/{case_id}/asr`
- `POST /api/cases/{case_id}/ocr`
- `GET /api/settings/llm`
- `POST /api/settings/llm/test`
- `POST /api/videos/import-single`
- `POST /api/videos/qualities`
- `POST /api/profile/scan`
- `POST /api/downloads`
- `POST /api/jobs/profile-scan`
- `POST /api/jobs/resolve-qualities`
- `POST /api/jobs/download`
- `POST /api/jobs/download-and-build-case`
- `POST /api/jobs/download-build-analyze-case`
- `POST /api/jobs/analyze-case`
- `POST /api/jobs/enrich-case`
- `POST /api/jobs/asr-case`
- `POST /api/jobs/ocr-case`

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
- `ENRICHMENT_FAILED`
- `COMMENTS_IMPORT_FAILED`
- `ASR_PROVIDER_NOT_CONFIGURED`
- `ASR_FAILED`
- `OCR_PROVIDER_NOT_CONFIGURED`
- `OCR_FAILED`

下载、主页扫描、Provider 相关错误码已集中定义在 `app/errors.py`，后续接入真实功能时复用。

## 测试

```bash
pytest -q
```

测试不依赖真实抖音接口，也不调用 KuKuTool。

## 后续路线

- P2：抖音主页 HTTP 扫描、Top N 点赞排序、作品表格、排序切换。
- P3：ZIP 导出、完整错误提示、README 扩展、下载安全测试补齐。
