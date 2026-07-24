# short-video-agent

本项目是一个本地短视频爆款分析素材包生成器，不是抖音下载器。

当前目标是把已授权的本地视频、单条作品或一组对标素材整理成稳定、可复用、可扩展的分析输入包：解析作品元数据、下载视频用于抽帧、生成素材包；配置大模型后，可在 case 页面或 Creator Clone Lab 中自动拆解并输出选题/脚本/分镜/创作者克隆规则所需的结构化结果。

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
3. 配置大模型后，可以在 case 页面生成单条作品拆解，也可以在“创作者克隆实验室”中选择 N 条对标样本，蒸馏账号级创作者规律。

## 业务模块规划

项目当前拆成两个一级主功能：

1. 单作品解析：当前可用。围绕一条视频完成链接输入、解析、下载、生成素材包、AI 拆解和 case 查看。
2. 创作者克隆实验室：P3.0 当前推进中。用于导入一个创作者或账号的对标素材，自由选择 N 条样本，通过大模型蒸馏出选题规则、表达方式、爆款公式和 AI 创作者克隆规则。

当前阶段的创作者克隆实验室已经收敛为单主线 Wizard：导入素材 -> 构建素材池 -> 选择 N 条样本 -> 证据富化 -> 大模型蒸馏 -> 可视化输出。页面只保留一个主按钮 `Start Creator Analysis` 驱动下一步；主页扫描优先使用用户主动配置的 Douyin Cookie / Web API，多作品链接、公开扫描和本机 Chrome 辅助作为回退。系统不会自动下载全部作品，也不会自动发布；选中作品后才进入素材包或蒸馏流程。

## Creator Clone Lab / 创作者克隆实验室

它替代原“主页扫描”作为账号级分析入口。目标不是爬取主页，而是把 `creator-clone-lab` 的方法产品化：

```text
导入素材池 -> 自由选择 N 条样本 -> 生成/复用素材包证据 -> 大模型蒸馏 -> 可视化展示 Creator Clone
```

数据源由 `DataSourceManager` 统一调度：

- `cookie_api`：主页扫描主力数据源。用户主动配置 `DOUYIN_COOKIE`、`DOUYIN_USER_AGENT` 和 `DOUYIN_REFERER` 后，系统优先尝试抖音 Web API `/aweme/v1/web/user/post/`；失败再进入安全回退。
- `manual_links`：稳定回退。支持一行一个链接、整段分享文案、纯 aweme_id 和混合输入，会自动去重。
- `browser_dom`：高级备用采集。只读取本机 Chrome 当前页面可见作品列表和元数据，不读取 Cookie 或登录 token。
- `external_api`：预留授权数据源，不作为默认路径。
- JSON / CSV 导入：支持 `items`、`samples`、`aweme_list`、`awemeList`，兼容 `aweme_id / awemeId / id`、`title / desc`、`author / nickname`、`cover_url / cover`、`statistics.digg_count` 等字段。
- 已有 Case 导入：轻量版支持粘贴 `case_id`，把已有素材包作为更高理解度样本参与蒸馏。

Cookie 和大模型 API 可以在右上角设置弹窗中修改，保存到本机 `.local_settings.json`。该文件已加入 `.gitignore`，不会进入数据库、素材包、Prompt 或 Git；接口响应只显示是否配置和脱敏状态。`.env` 仍可作为默认配置，页面保存的本机运行时配置优先级更高。

Cookie 设置用于主页 Web API 扫描，不作为绕过平台验证的手段。安全边界固定为：

- Douyin Cookie 由用户主动配置，仅保存在本机。
- 已保存 Cookie 不回显原文。
- Cookie 不进入数据库、素材包、Prompt 或日志。
- 本机 Chrome 辅助不读取 Cookie。

环境变量示例：

```env
DOUYIN_COOKIE=
DOUYIN_USER_AGENT=
DOUYIN_REFERER=https://www.douyin.com/
```

样本选择：

- 可勾选任意 N 条素材。
- 支持选择全部可解析视频、综合分 Top 3、高评论样本和低表现样本。
- 蒸馏最多选择 20 条；少于 2 条会提示“样本过少，结果仅供参考”。
- 每条样本会显示理解状态：完整、部分、仅元数据。
- 点击主按钮“开始富化证据”后，系统会对选中视频逐条解析清晰度、下载、生成 Case、写入 enrichment 归档，并尝试运行 ASR / OCR。ASR 或 OCR 未配置时只记录 `provider_missing`，不会阻断素材包生成。
- 点击“大模型蒸馏”会创建后台 Job，页面轮询进度；LLM 未配置或请求失败时会降级生成 `distill_prompt.md`，素材池和富化证据不会丢失。

蒸馏输出：

- `outputs/creator_clones/{set_id}/samples.json`
- `outputs/creator_clones/{set_id}/distill_prompt.md`
- `outputs/creator_clones/{set_id}/creator_clone_result.json`
- `outputs/creator_clones/{set_id}/creator_clone.md`

页面会把结果渲染成可读模块，而不是只显示 JSON：

- 顶部总览与蒸馏置信度；
- 样本分层；
- 选题桶；
- 表达模式；
- 可复用公式；
- AI Creator Clone 规则；
- 候选选题；
- 证据缺口与下一步建议。

未配置 LLM 时仍会生成 `distill_prompt.md`，页面提供“复制蒸馏 Prompt”用于手动给外部大模型分析。

主页扫描已知限制：

- 部分抖音主页即使 URL 有效，公开 HTTP 请求也只会返回浏览器校验脚本，例如包含 `_$jsvmprt`、`byted_acrawler`、`__ac_nonce` 或验证码标记。此时系统会返回 `DOUYIN_RISK_CONTROL`。
- `DOUYIN_RISK_CONTROL` 代表平台没有返回公开作品列表，不是主页 URL 格式错误，也不是图文/照片作品导致。
- 当前项目边界是不绕验证码、不绕风控、不做签名破解；Cookie API 是主页扫描的主力数据源，但遇到风控、结构不可解析或 Cookie 失效时，推荐改用“多作品链接粘贴”“浏览器辅助采集”“JSON / CSV 导入”或“已有 Case 导入”继续整理素材池。
- 多作品粘贴是当前账号级分析的稳定入口；支持一行一个作品链接、整段分享文案、纯 aweme_id 和混合输入，并会显示识别、去重、忽略无效内容的统计。
- 作品池富化队列默认一次最多处理 150 条可下载视频，可通过 `PROFILE_BUILD_MAX_ITEMS` 调整。每条作品会逐条复用单作品解析、下载、素材包生成、enrichment 归档、可选 ASR/OCR 和可选 AI 拆解流程；某条失败不影响后续条目。大模型蒸馏仍默认最多选择 20 条代表样本，避免上下文过长。
- 后续如果确认要继续增强账号级扫描，应优先完善授权数据源和浏览器可见信息交接，不做 A_Bogus / X_Bogus、验证码绕过或隐式登录态依赖。
- 后续再继续做更多平台适配器、浏览器辅助的本地版采集、评论导入联动和更完整的案例库策略层。

核心功能：

- FastAPI 本地 Web 页面。
- SQLite 本地数据库。
- 页面主入口：单作品解析。
- 抖音 native mobile feed/share 优先解析，网页 detail 作为兜底；通常不需要 Cookie，当前不使用 KuKuTool。
- 清晰度偏好在右上角设置弹窗中统一配置，主流程不展示候选直链。
- 同清晰度 CDN 候选会做轻量 Range 测速，默认选择响应更快的 host。
- 单作品主流程已收敛为一个“解析”按钮：解析候选 → 下载视频 → 自动生成素材包；配置大模型后可自动拆解。
- 创作者克隆实验室可整理素材池，支持点赞、评论、分享、综合分和发布时间排序，并显示基础素材概览。
- 素材池可全选、取消选择、推荐组合、高赞 Top 3、高评 Top 3、高分享 Top 3、最新 Top 3 和低表现样本；“富化选中样本”默认最多 150 条可下载视频，蒸馏最多选择 20 条代表样本。
- 需要汇总 20 条以上样本时，使用“分批蒸馏已选样本”：系统会按每批最多 20 条逐批蒸馏，再把所有批次摘要做最终 Reduce，输出账号级总报告。批次产物保存在 `outputs/creator_clones/{set_id}/batch_distill/`。
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
- 自动爬取和批量下载完整主页；
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
git clone git@github.com:Daiobs/short-video-agent.git
cd short-video-agent
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

`requirements.txt` 包含网页服务、SQLite、Chrome DevTools websocket、基础素材包处理和 `yt-dlp`。其中 yt-dlp 用于后续公开视频解析 / 下载能力；如果预检显示缺失，请重新执行上面的安装命令。

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

## 自用版本机 Chrome 辅助采集

Creator Clone Lab 首页只保留一个主动作：`Start Creator Analysis`。主页输入会优先使用用户主动配置的 Douyin Cookie / Web API；Cookie 未配置、失效或接口受限时，可使用多作品链接、公开扫描，或展开高级工具使用“本机 Chrome 辅助采集”作为自用兜底。

默认模式使用专用本地 profile：`outputs/local_chrome_profile/`。这样不会碰你的日常 Chrome 登录态，但第一次使用时需要在这个 Chrome 窗口里自行登录或过验证。可以手动执行：

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --remote-allow-origins=http://127.0.0.1:8765,http://127.0.0.1:9222 \
  --user-data-dir="$(pwd)/outputs/local_chrome_profile" \
  --no-first-run \
  --no-default-browser-check \
  https://www.douyin.com/
```

如果你希望复用日常 Chrome 里已经登录的抖音账号，可以在 `.env` 中显式打开高级模式：

```env
LOCAL_CHROME_PROFILE_MODE=existing
# 可选：不填时 macOS 默认使用 ~/Library/Application Support/Google/Chrome
LOCAL_CHROME_USER_DATA_DIR=
```

然后请先完全退出普通 Chrome，再按页面“本地工作流预检”里给出的命令启动带 DevTools 的 Chrome。否则 Chrome 可能复用已运行进程并忽略 `remote-debugging-port`，页面仍然检测不到调试端口。这个模式适合自用机，风险更高：调试端口能访问当前 Chrome 页面，所以仍然只允许 `127.0.0.1`，并且扫描必须经过页面确认和一次性 token。

然后：

1. 在这个 Chrome 中打开目标抖音主页，必要时自行登录或完成平台验证。
2. 回到 `http://127.0.0.1:8765/` 的“创作者克隆实验室”。
3. 输入主页 URL / sec_user_id。
4. 勾选本机辅助采集确认。
5. 点击“本机 Chrome 辅助入口”。
6. 页面会弹出确认框；确认后系统会申请一次性 token，连接 `127.0.0.1:9222`，在当前标签页内进行几轮受控滚动，读取 DOM 中可见的作品列表和元数据，生成素材池。

安全边界：

- 后端自用版会拒绝非本机来源请求，只允许 `127.0.0.1` / `localhost`。
- 即使误把服务绑定到 `0.0.0.0`，应用层也会拒绝非 loopback 客户端、非 loopback Host，以及非本机 Origin / Referer 发起的写操作。
- 本机助手接口每次启动 Chrome、打开主页、扫描或清理辅助 profile 都需要一次性 token；首页主流程只暴露“本机 Chrome 辅助入口”，调试动作保留为设置预检提示、内部 API 或手动命令。
- 启动 Chrome、打开主页、扫描主页和清理辅助 profile 除了 token 之外还需要页面确认；直接调接口但没有确认字段会被拒绝。
- Chrome 辅助采集不读取 Cookie、不返回 Cookie、不写 Cookie 日志。
- 返回前会过滤敏感字段，并移除作品链接、封面链接和标签页 URL 中的 query / fragment，避免泄露签名参数或临时 token。
- 启动 Chrome 的子进程使用最小环境变量，不继承 Django 的 API Key、数据库地址或其他敏感配置。
- 专用 Chrome profile 位于 `outputs/local_chrome_profile/`，已加入 `.gitignore`，不要提交该目录；需要清理时可删除该目录，或调用 `POST /api/local-helper/chrome/clear-profile`。该接口同样需要一次性 token 和页面确认，且只清理专用 profile，不影响普通 Chrome 用户资料。
- 采集结果只保留账号资料、作品链接、标题、封面、可见点赞/评论/分享/收藏等元数据。
- 请求由你的本机 Chrome 和本机 IP 发起；公开网站版不应该接收用户 Cookie。
- 公开网站 / 本机助手模式的目标边界是：用户本机插件或助手读取本机 Chrome 登录态，用用户本机 IP 请求平台；公开网站只接收净化后的 `handoff_manifest.json`，继续做素材池筛选、富化和大模型蒸馏。
- `handoff_manifest.json` 必须带有安全契约声明；缺少声明，或声明包含 Cookie、登录 token、签名媒体 URL、原始请求头等风险字段时，导入接口会拒绝。
- 如果页面没有加载作品列表，或 Chrome 未以 remote debugging 模式启动，接口会返回明确错误。
- 每次成功采集会在 `outputs/creator_clones/{set_id}/capture_audit.json` 记录最近一次采集审计，并追加到 `capture_audits.jsonl`。审计只包含采集方式、滚动轮数、样本数、安全声明和已过滤的标签页信息，不包含 Cookie、签名 URL 或登录 token。
- `outputs/creator_clones/` 和 `samples/` 都属于本地采集 / 蒸馏运行时产物，默认已加入 `.gitignore`。这些文件可能包含账号素材清单、标题、可见互动数据、Prompt 或本地研究样本，不建议提交到 Git。

## 本地工作流预检

设置弹窗中的“本地工作流预检”会只读检查当前机器是否具备完整工作流能力：

- 本机 Chrome 助手：是否可连接 `127.0.0.1:9222`，是否已打开抖音主页标签页；状态检查只返回匿名标签页数量和就绪状态，不返回标签页标题、URL 或作品数据。
- Chrome DevTools websocket：本机浏览器辅助采集是否能连接到已打开的 Chrome。
- `yt-dlp`：公开视频解析 / 下载能力是否可用。
- `ffmpeg` / `ffprobe`：素材包抽帧、音频提取和媒体信息读取是否可用。
- ASR：根据 `.env` 中的 `ASR_PROVIDER` 判断是否启用，并检查 `faster-whisper` 模块是否可用。
- OCR：根据 `.env` 中的 `OCR_PROVIDER` 判断是否启用，并检查 `rapidocr-onnxruntime` / `rapidocr` 模块是否可用。
- 大模型：复用 LLM 配置状态，只显示是否配置，不返回 API Key。
- 本机访问防护：确认应用层启用 loopback / Host / Origin / Referer 防护。
- 开发服务监听地址：确认 `scripts/dev_server.py` 固定监听 `127.0.0.1`，避免用 `0.0.0.0` 暴露自用版接口。
- 助手确认门槛：确认 Chrome 启动、打开主页、扫描主页和清理辅助 profile 都需要一次性 token 和页面确认。
- 公开站 / 本机助手边界：确认公开网站只接收净化后的账号素材清单，本机请求由用户 Chrome / 本机 IP 发起，Cookie、登录 token、签名媒体 URL 和原始请求头不会进入交接包。
- 运行产物忽略：确认 `outputs/creator_clones/`、`outputs/local_chrome_profile/`、`samples/` 已被 `.gitignore` 排除。

预检接口不会读取 Cookie，不会发起平台扫描，也不会调用大模型；它只用于告诉用户当前本机环境能跑到哪一步。真正读取当前 Chrome 页面 DOM 中可见作品列表，必须走一次性 token + 页面确认后的“本机 Chrome 辅助入口”。

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
LLM_FINAL_REDUCE_TIMEOUT_SECONDS=600
LLM_QUICK_DISTILL_BUDGET_SECONDS=180
LLM_DEEP_DISTILL_BUDGET_SECONDS=300
LLM_BATCH_JOB_BUDGET_SECONDS=600
LLM_FINAL_REDUCE_MIN_RESERVE_SECONDS=120
LLM_COMPACT_RETRY_MIN_REMAINING_SECONDS=30
LLM_TEMPERATURE=0.2
LLM_MAX_KEYFRAMES=6
LLM_MAX_OUTPUT_TOKENS=1200
LLM_FINAL_REDUCE_MAX_OUTPUT_TOKENS=4000
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

`LLM_TIMEOUT_SECONDS` 和 `LLM_FINAL_REDUCE_TIMEOUT_SECONDS` 是单次请求上限；完整任务还受墙钟总预算约束。快速蒸馏默认 180 秒，深度蒸馏默认 300 秒，Batch Job 默认 600 秒并至少为 Final Reduce 预留 120 秒。Prompt、样本数和视频时长只进入诊断，不会自动把总预算扩展到几十分钟。网关限流、鉴权失败和额度不足不会自动重试；timeout、502/503/504 和无效 JSON 仅在剩余预算不少于 30 秒时允许一次精简 Prompt 重试。

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
- `GET /api/settings/preflight`
- `POST /api/videos/import-single`
- `POST /api/videos/qualities`
- `POST /api/profile/scan`
- `POST /api/creator-clone/import`
- `GET /api/creator-clone/sets/{set_id}`
- `POST /api/creator-clone/distill`
- `GET /api/creator-clone/sets/{set_id}/files/{filename}`
- `GET /api/local-helper/chrome/status`
- `POST /api/local-helper/chrome/scan-token`
- `POST /api/local-helper/chrome/launch`
- `POST /api/local-helper/chrome/open-profile`
- `POST /api/local-helper/chrome/scan-profile`
- `POST /api/local-helper/chrome/clear-profile`
- `POST /api/downloads`
- `POST /api/jobs/profile-scan`
- `POST /api/jobs/resolve-qualities`
- `POST /api/jobs/download`
- `POST /api/jobs/download-and-build-case`
- `POST /api/jobs/creator-clone-distill`
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
- `UNSUPPORTED_PROFILE_ITEM`
- `PROFILE_BUILD_QUEUE_LIMIT`
- `PROFILE_BUILD_ITEM_FAILED`
- `ASR_PROVIDER_NOT_CONFIGURED`
- `ASR_FAILED`
- `OCR_PROVIDER_NOT_CONFIGURED`
- `OCR_FAILED`

下载、素材池导入、主页扫描、Provider 相关错误码已集中定义在 `app/errors.py`，后续接入真实功能时复用。

## 测试

```bash
pytest -q
```

测试不依赖真实抖音接口，也不调用 KuKuTool。

## 后续路线

- P3.1：把已有 Case 列表做成可视化导入器，减少手动粘贴 `case_id`。
- P3.2：把 ASR / OCR / 评论富化摘要自动并入 Creator Clone 蒸馏输入。
- P3.3：补更多平台 adapter 和本地研究模式，不把公开主页扫描作为唯一入口。
