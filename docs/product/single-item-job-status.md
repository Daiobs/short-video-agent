# SV-UX-01：单作品任务状态可视化

## 1. 文档目的

本文记录 `SV-UX-01` 实施前的真实入口、状态来源、展示映射、部分失败边界、安全约束与网络基线。它是前端展示改造的审计依据，不定义新的后端状态，也不改变任务执行语义。

本轮范围严格限定为单作品任务的状态可视化：

- 将已有 Job、Case 和前端请求状态归一为四个用户可理解的阶段；
- 在已有响应数据足够时展示成功、部分完成、失败与未知降级；
- 不新增请求、不自动重试、不触发新的 Provider 调用；
- 不实现结果动作条。结果动作条属于后续 `SV-UX-02`；
- EchoLens 只作为“长任务阶段可视化”和“部分结果仍可继续使用”的概念参考，不复制其文案、代码、图标、素材或交互细节。

## 2. 不变量与变更边界

| 层面 | 本轮约束 |
| --- | --- |
| API | 路径、方法、请求参数、响应结构均不变化 |
| 数据库 | 表、字段、迁移与持久化语义均不变化 |
| Provider | 不新增、不更换、不提前或重复调用 Provider |
| 状态机 | 不新增后端状态，不改变 Job/Case 状态迁移 |
| 网络 | 不新增 `fetch`、轮询、SSE、WebSocket、脚本资源或图片资源 |
| 重试 | 不自动刷新、不自动重新提交、不自动重试失败步骤 |
| 安全 | 不显示路径、异常原文、响应正文、凭据或用户敏感数据 |
| 结果动作 | 本轮不增加打开文件、复制路径、下载、分享或重跑按钮 |

四阶段视图只是现有事实的只读投影。任何无法由现有字段证明的阶段不得显示为完成。

## 3. 真实入口与现有数据链路

### 3.1 页面入口

- 首页由 `app/routes/pages.py` 的 `GET /` 返回。
- 单作品一级入口是 `app/templates/index.html` 中的 `data-home-route="single"` 导航项。
- 页面路由使用 `#single`，实际 DOM 面板是 `#home-single`，不是独立后端 URL；`app/static/app.js` 的 hash 路由负责在首页内切换。
- 当前状态展示和结果容器位于 `app/templates/index.html` 的单作品面板内；Job 卡片由前端放置到当前流程区域。

因此，本轮只能增强 `#single` 中现有任务的展示，不能把它改造成新的路由、工作台或任务系统。

### 3.2 请求与事实来源

| 来源 | 用途 | 本轮可使用的事实 | 约束 |
| --- | --- | --- | --- |
| 前端本地请求状态 | 表单提交到 Job 建立前的短暂状态 | 导入中、候选加载中、提交中、Case 加载中 | 只描述当前请求，不伪装成后端状态 |
| `POST /api/videos/import-single` | 解析并导入单作品 | 导入成功或错误码 | 不增加调用 |
| 清晰度候选请求 | 获取已有下载候选 | 候选是否已取得 | 不增加调用 |
| `POST /api/jobs/download-build-analyze-case` | 创建组合 Job | Job 已被接收、返回的 Job 标识 | 不改变请求体 |
| `GET /api/jobs/{job_id}` | 活跃任务轮询 | `status`、`result`、安全错误码 | 不显示原始 `message` |
| `GET /api/workbench/jobs/{job_id}` | 首页恢复历史任务 | 已净化的投影状态、Case 关联 | 不增加恢复轮询 |
| `GET /api/cases/{case_id}` | 加载结果 Case | 素材完整性、AI 状态、现有可展示结果 | Case 标识本身不等于结果可用 |
| Case 中已有资源 URL | 渲染关键帧总览等现有资源 | 资源成功显示可作为可用结果证据 | 不构造路径、不探测额外文件 |

### 3.3 现有代码中的状态生产者

- Job 原始状态由 `app/routes/jobs.py` 创建和更新。
- 首页恢复使用的投影状态由 `app/services/workbench_overview.py` 生成；其允许集合定义在 `app/services/workbench_tasks.py`。
- Case 主流程状态由 `app/routes/cases.py` 的 `primary_workflow` 计算。
- ASR、OCR 等富化状态来自 Case 已有载荷；本轮只在字段已经存在时使用。
- 当前错误码集合在 `app/errors.py`；错误文本可能含操作性细节，但状态摘要只允许按错误码做稳定分类。

## 4. 完整状态枚举

### 4.1 后端与投影状态

| 对象/字段 | 已观察状态 | 性质 |
| --- | --- | --- |
| 原始 `job.status` | `pending`、`running`、`success`、`failed` | Job 的权威执行状态 |
| Workbench 投影 `status` | `pending`、`running`、`success`、`failed`、`recoverable`、`stale` | 首页恢复使用的净化投影；Overview 可派生 `stale`，现有前端观察流程也会在既定 30 分钟边界停止继续观察，但状态组件本身不增加计时判断 |
| `job.result.analysis_status` | `pending`、`success`、`skipped`、`failed` | 组合 Job 内 AI 分析子结果；当前 `skipped` 可由 `LLM_NOT_CONFIGURED` 产生 |
| `case.primary_workflow.analysis_status` | `artifact_incomplete`、`completed`、`not_configured`、`not_analyzed` | Case 对素材包和 AI 结果的归一化状态 |
| CaseArtifact 持久化 `status` | 当前默认值可见为 `success`；未见数据库枚举约束 | 不能把任意新字符串当作已支持状态；非已知值走未知降级 |

### 4.2 可选富化状态

以下值只在 Case 已有载荷中出现时作为补充说明，不能反向驱动 Job，也不能单独证明整个任务完成：

- ASR：`success`、`no_speech`、`pending`、`missing`、`provider_missing`、`not_configured`、`failed`；
- OCR：`success`、`no_text`、`pending`、`missing`、`provider_missing`、`disabled`、`not_configured`、`failed`；
- manifest 中的评论、指标和索引：`pending`、`success`；只有已知的 `failed`，以及明确尝试 Provider 后得到的 `provider_missing`，可作为补充失败证据；可选项的 `missing`、`disabled`、`not_configured`、`skipped` 和 `not_required` 保持中性；
- 其他未识别值：统一作为 `unknown` 处理，不直接显示原值。

### 4.3 前端瞬时状态

前端还存在尚未形成 Job 的瞬时事实：

- 未提交；
- 导入请求进行中；
- 作品已导入、清晰度候选请求进行中；
- Job 创建请求进行中；
- Job 轮询进行中；
- Case 获取进行中或失败。

这些只用于避免界面空白，不写回后端，也不得创造诸如 `downloading`、`analyzing`、`completed_with_errors` 的新协议状态。

## 5. 四阶段展示模型

固定阶段名称：

1. 已接收
2. 获取素材
3. 生成分析
4. 完成

固定展示状态：

| 展示状态 | 用户含义 | 证据要求 |
| --- | --- | --- |
| `pending` | 尚未到达或尚无证据 | 默认状态，不表示错误 |
| `active` | 当前有请求或 Job 正在推进 | 前端正在进行的现有请求，或已知 Job 处于 `pending`/`running` |
| `completed` | 该阶段已有明确成功证据 | 已有响应字段、Case 字段或已成功渲染的结果 |
| `partial` | 已保留可用结果，但该阶段有已知缺失、跳过或中断 | 可用结果证据和降级/失败证据必须同时存在 |
| `failed` | 已有终态失败证据，且没有该阶段可用结果 | 已知失败状态或安全错误码；不能仅因等待较久而判失败 |

展示状态不是后端状态，不出现在 API 或数据库中。

## 6. 现有状态到四阶段的确定性映射

下表按“最具体证据优先”应用。Case 中的实际产物证据优先于较粗粒度的 Job 状态；未知字段不能覆盖已确认的可用结果。

| 现有状态 / 可见证据 | 四阶段 | 展示状态 | 映射依据 |
| --- | --- | --- | --- |
| 无本地请求、无 Job、无 Case | 已接收 / 获取素材 / 生成分析 / 完成 | 全部 `pending` | 用户尚未开始，不能推断任何进度 |
| 导入或 Job 创建的现有请求正在进行，尚无 Job | 已接收；其余阶段 | `active`；其余 `pending` | 仅能确认请求已由页面接收 |
| 导入成功，正在获取候选或提交 Job | 已接收；获取素材；其余阶段 | `completed`；`active`；其余 `pending` | 导入响应证明输入已接收，素材流程已开始 |
| Job 为 `pending`，尚无下载/Case 证据 | 已接收；获取素材；生成分析；完成 | `completed`；`active`；`pending`；`pending` | Job 已建立，但尚无素材完成证据 |
| Job 为 `running`，尚无下载/Case 证据 | 已接收；获取素材；生成分析；完成 | `completed`；`active`；`pending`；`pending` | 组合任务正在运行，最早未证实阶段为素材获取 |
| Job 为 `running`，结果中已有明确素材成功证据、无 Case | 已接收；获取素材；生成分析；完成 | `completed`；`completed`；`active`；`pending` | 已有素材证据，下一阶段为 Case/分析生成 |
| Job 为 `running`，已有 `case_id`，Case 尚未加载或分析为 `pending`/`not_analyzed` | 已接收；获取素材；生成分析；完成 | `completed`；`completed`；`active`；`pending` | Case 关联证明素材阶段已过；最终结果尚未完成 |
| Job 为 `success` 且响应中有实际分析 payload/report，或 Case 为 `artifact_ready=true` 且 `analysis_status=completed` | 四阶段 | 全部 `completed` | 素材包与分析结果均有明确成功证据；只有 `analysis_status=success` 字符串但没有结果载荷时仍需等待 Case 复核 |
| Job 为 `success`，Case 可用，但 AI 为 `failed`、`skipped` 或 `not_configured` | 已接收；获取素材；生成分析；完成 | `completed`；`completed`；`partial`；`partial` | 基础结果可用，AI 子结果失败、跳过或未配置；不能宣称完全成功 |
| Job 为 `success`，Case 可用，AI 为 `not_analyzed` | 已接收；获取素材；生成分析；完成 | `completed`；`completed`；`partial`；`partial` | 任务已经终止但分析未生成；保留基础产物并明确缺口，不在本轮自动补跑 |
| Job 为 `failed`，无素材、Case 或其他可用结果证据 | 已接收；获取素材；生成分析；完成 | `completed`；`failed`；`pending`；`failed` | 最早失败发生在素材阶段；最终失败，后续阶段未执行 |
| Job 为 `failed`，已有素材成功证据但无可用 Case | 已接收；获取素材；生成分析；完成 | `completed`；`completed`；`failed`；`failed` | 素材已取得，Case/分析阶段失败且无可用结果 |
| Job 为 `failed` 或 `recoverable`，但成功加载的同一 Case 中已有可用产物 | 已接收；获取素材；生成分析；完成 | 依已证实阶段为 `completed`；发生中断的阶段为 `partial`；完成为 `partial` | 已保留产物不得被粗粒度 Job 失败覆盖；Job 的 Case 尚未复核、Case ID 不一致或只有 `available_results` 提示时先显示未知，不提前宣称部分完成 |
| Workbench 为 `stale`，但已有阶段证据或可用产物 | 已证实阶段；最早未确认阶段；完成 | 已证实阶段保持 `completed`；最早未确认阶段为 `active`；完成保持 `pending`，完整结果只把“完成”标为待确认 | `stale` 只证明状态需要确认，不证明某项结果失败；整体文案为“状态更新中” |
| Workbench 为 `stale`，无 Case 或可用结果 | 已接收；获取素材；生成分析；完成 | `completed`；`active`；`pending`；`pending` | Job 已存在，但最早未确认的素材阶段只能保守显示进行中；不显示部分成功，不触发自动重试 |
| 仅恢复到 Case，`artifact_ready=true` 且有分析报告 | 四阶段 | 全部 `completed` | Case 自身提供完整证据，无需依赖已丢失的活跃 Job |
| 仅恢复到 Case，`artifact_ready=true`，AI 为 `not_configured`/`not_analyzed` | 已接收；获取素材；生成分析；完成 | `completed`；`completed`；`partial`；`partial` | 素材包可用，分析缺失 |
| Case 为 `artifact_incomplete`，但至少一个允许展示的产物可用 | 已接收；获取素材；生成分析；完成 | `completed`；`partial`；`pending` 或 `partial`；`partial` | 素材包不完整但已有可用结果；分析状态按独立证据决定 |
| Case 为 `artifact_incomplete`，且没有允许展示的产物 | 已接收；获取素材；生成分析；完成 | `completed`；`failed`；`pending`；`failed` | 缺少可用结果，不能使用“部分完成”弱化失败 |
| 任一对象出现未知状态值，且没有可用产物 | 已接收；最早未确认阶段；其余阶段 | 已有事实保持；最早未确认阶段 `active`；其余 `pending` | 显示“状态更新中”，不崩溃、不全绿、不暴露原值 |
| 任一对象出现未知状态值，但已有可用产物 | 已证实阶段；最早未确认阶段；完成 | 已证实阶段 `completed`；未确认阶段 `active`；完成保持 `pending`，仅在另有明确失败证据时为 `partial` | 保留已知事实，同时不把“未知”伪装成已确认的部分失败 |

状态组件本身不得依赖浏览器计时猜测，也不新增任何时间阈值。它可以消费 Workbench 已提供的 `stale` 投影；现有观察流程达到既定 30 分钟保护边界时会停止继续观察并显示待确认，但本轮不改变该既有行为，更不会把它改判为失败。

## 7. 部分失败与计数边界

### 7.1 “可用结果”的最低证明

只有已在现有 DTO 中返回、且现有页面可以安全呈现的逻辑产物才算可用结果，例如：

- 成功加载的 Case 基础信息或素材包摘要；
- 已由现有 UI 成功渲染的关键帧总览；
- 已存在的 AI 拆解报告；
- 现有响应中已经直接提供、且当前 UI 已支持展示的其他净化结果。

以下内容不能单独算作可用结果：

- 仅有 `case_id`，但 Case 获取失败或内容未确认；
- 本地绝对路径、对象存储签名 URL、临时下载 URL；
- Job 的 `success` 字符串，没有对应结果字段；
- `local_video_id` 等内部标识，但当前界面没有安全可用的展示能力；
- 仅从错误消息、日志或响应原文猜测某文件可能存在。

### 7.2 判为 `partial` 的条件

至少满足以下两项：

1. 存在一个按上一节证明的可用结果；
2. 存在一个独立的缺失、失败、跳过、中断或未配置证据。

典型情况包括：

- Case 已保留，但 AI `failed`、`skipped`、`not_configured` 或 `not_analyzed`；
- Case 的 `missing_artifacts` 非空，但仍有允许展示的产物；
- Job `failed` 或 `recoverable`，且成功加载并核对为同一任务的 Case 中已有结果；`stale` 仍表示状态待确认，不单独触发 `partial`；
- ASR/OCR 等非关键富化失败，而基础 Case 与核心结果仍可使用。

若没有可用结果，则终态失败必须显示 `failed`，不能显示 `partial`。

### 7.3 计数口径

部分结果摘要采用“用户可理解的逻辑结果组”计数，不按文件数、帧数、Provider 尝试次数或轮询次数计数。

- 成功项：按已存在并可展示的逻辑组去重，例如“素材包”“关键帧总览”“AI 拆解报告”；
- 失败/缺失项：按独立能力组去重，例如“AI 分析”“字幕识别”“画面文字识别”“素材包完整性”；
- 同一能力的状态码、错误码和缺失字段同时出现时，只计一次；
- `missing_artifacts` 只能映射到预定义的安全中文类别，不能直接显示后端标签、文件名或路径；
- 计数只覆盖当前响应中可以证明的项目，不把“未知”算作失败；
- 可选产物的普通 `missing`/未配置状态不计失败；只有显式执行失败，或已尝试但 Provider 不可用，才进入失败计数；
- 摘要应使用“已保留 X 项结果，Y 项未完成”一类事实性文案，不宣称任务全部成功。

## 8. 未知状态降级

未知状态必须满足以下行为：

- 页面继续可用，四阶段组件不抛异常；
- 不把未知状态渲染成 `completed` 或 `failed`；
- 用户文案统一为“状态更新中”或“当前状态暂不可确认”；
- 已有可用结果继续展示，最终状态最多为 `partial`；
- 没有可用结果时，后续阶段保持 `pending`；
- 不因未知状态自动刷新页面、加快轮询、重新提交或重跑；
- 如需开发日志，只记录经过长度限制的状态名/任务类型等非敏感标量，不记录完整对象、ID、消息、Header 或响应正文。

Workbench 投影会把无法识别的旧状态净化为 `failed`，且不会保留原始值。因此，恢复入口中的 `failed` 只有在同时存在可稳定分类的错误码或结构化失败证据时才按失败展示；错误码为空或属于未来未知分类时，前端保守显示“状态更新中”。原始 `/api/jobs/{job_id}` 返回的 `failed` 不受这条兼容规则影响。

轮询中的短暂冲突同样按未知处理：运行中或 `stale` 的 Case 快照即使暂时缺文件，也不提前显示终态失败；Workbench 终态投影只有状态字符串、而同一 Case 仍待现有请求复核时，也不先显示完成或部分失败。组合 Job 即使已经带回分析载荷，也会等待主流程本来就会执行的 Case 读取完成后再宣布终态，避免“完成 → 部分完成”的闪烁；这不会新增 Case 请求。新 Case 到达后再依据实际产物收敛到 `completed`、`partial` 或 `failed`。切换任务时必须清空上一任务的瞬时 Flow 和 Case；Job 与 Case ID 不一致时不得合并两者证据。

700 ms 主流程与 900 ms Workbench 观察器共享一个只存在于前端内存的观察代次和活动 Job ID。开始新任务或打开新的恢复目标时递增代次；旧请求返回后若代次或 Job ID 已不匹配，结果会被忽略且不再递归。相同 Job 已到 `success`/`failed` 后也拒绝回退到 `pending`/`running`/`stale`。这只是阻止过期响应覆盖当前界面，不改变后端 Job/Case 状态机，也不增加轮询、取消请求或自动重试。

## 9. 错误脱敏规则

### 9.1 可显示来源

状态摘要只根据稳定错误码和结构化状态分类。活跃 `GET /api/jobs/{job_id}` 中的原始 `message` 可能来自异常文本；即使后端做过截断，前端仍不得将其直接写入状态组件。

| 安全分类 | 可归入的错误码示例 | 用户摘要 |
| --- | --- | --- |
| 输入、来源与候选 | `INVALID_AWEME_URL`、`AWEME_ID_NOT_FOUND`、`PROVIDER_FAILED`、`QUALITY_NOT_FOUND`、`URL_EXPIRED`、`INVALID_VIDEO_FILE` | 素材获取未完成 |
| 下载与校验 | `HOST_NOT_ALLOWED`、`REDIRECT_HOST_NOT_ALLOWED`、`CONTENT_TYPE_INVALID`、`CONTENT_LENGTH_TOO_LARGE`、`DOWNLOAD_TIMEOUT`、`DOWNLOAD_FAILED` | 素材获取未完成 |
| 素材处理 | `FFMPEG_NOT_FOUND`、`FFPROBE_FAILED`、`KEYFRAME_EXTRACT_FAILED`、`CASE_BUILD_FAILED` | 素材包未完整 |
| AI 分析 | `LLM_NOT_CONFIGURED`、`LLM_REQUEST_FAILED`、`LLM_RESPONSE_INVALID`、`AUTO_ANALYSIS_FAILED` | 自动拆解未生成 |
| 富化 | `ASR_PROVIDER_NOT_CONFIGURED`、`ASR_FAILED` | 语音文本不可用 |
| 富化 | `OCR_PROVIDER_NOT_CONFIGURED`、`OCR_FAILED` | 画面文字不可用 |
| 富化 | `ENRICHMENT_FAILED`、`COMMENTS_IMPORT_FAILED` | 证据补充未完成 |
| 保存/归档 | 名称中明确含 `SAVE`、`WRITE` 或 `PERSIST` 的稳定错误码 | 结果保存未完成 |
| 未知或未列入允许表 | 任意其他值 | 状态暂时不可确认 |

### 9.2 永不显示的内容

- Cookie、Authorization、Token、CSRF 值、API Key；
- 完整请求/响应正文或 Header；
- 邮箱、用户标识、签名 URL 与查询参数；
- 本地绝对路径、对象存储内部路径、数据库或 SQL 细节；
- Python/JavaScript 堆栈、异常类名、第三方 Provider 原始错误；
- 后端原始 `message`，即使它看起来像普通中文提示。

所有动态文本必须通过安全 DOM 文本属性或现有转义工具输出，不得拼接为未转义 HTML。

## 10. 网络基线与零新增请求门禁

### 10.1 首页基线

冷启动首页的代码确定基线为：

- 4 个自动 API 请求：`/api/settings/llm`、`/api/settings/data-sources`、`/api/settings/preflight`、`/api/workbench/overview`；
- 1 个文档、1 个 CSS、5 个 JavaScript，加上上述 4 个 API，共 11 个同源请求；
- 浏览器自行决定的 favicon 等请求不纳入代码确定基线；
- 切换到 `#single` 本身不应产生新请求。

### 10.2 单任务基线

现有单作品主流程的请求预算为：

```text
3 + N + 2C
```

其中：

- `3`：导入、清晰度候选、创建组合 Job 三个固定请求；
- `N`：现有 `GET /api/jobs/{job_id}` 轮询次数；当前活跃轮询在每次处理后约 700 ms 再继续；
- `C`：Case 加载次数；成功返回且含现有 contact sheet 时，每次对应一个 Case JSON 和一个图片请求，因此记为 `2C`。若没有可渲染图片，则图片请求自然不存在，但不得为状态组件补发探测请求。

Workbench 恢复流程已有约 900 ms 的观察周期及其既有 Case/图片加载行为。本轮不调整该机制。

### 10.3 验收门禁

- 状态视图只能消费已有内存中的 Job/Case/请求状态；
- 不新增 `fetch` 调用，不新增 `setInterval`，不新增轮询分支；
- 不新增脚本、图标或状态图片资源请求；
- 不为了确认文件是否存在而发送 `HEAD`/`GET`；
- 不为了未知或失败状态自动重试；
- 用请求 spy 或浏览器 Performance 记录对比修改前后的 endpoint 多重集合与主流程公式。

源码中 `fetch(` 的文本出现次数只是结构性检查，不等于页面运行时请求数，也可能包含非首页路径。本任务以以上可复现的页面与流程预算为网络回归门禁；实施前后应使用同一统计命令补充对比，但不能用静态文本计数替代运行时验证。

## 11. 不自动重试的理由

- 状态组件是事实投影，不是任务编排器；
- 自动重试会改变外部状态，可能重复下载、建 Case 或产生付费模型调用；
- 用户无法区分原任务结果与重试结果，破坏可追溯性；
- `stale`、`recoverable` 和未知状态不一定意味着可安全重跑；
- 本项目北极星要求人工确认、可验证和可回滚。

因此，本轮只呈现“已保留结果”和“未完成能力”，不增加刷新、重跑或恢复按钮。

## 12. 为什么动作条延期到 SV-UX-02

“打开结果目录”“复制路径”“下载”“重新分析”等动作涉及本地路径暴露、签名 URL、剪贴板、重复 Provider 调用和用户确认，需要单独做能力、权限与安全审计。`SV-UX-01` 不实现任何动作条；状态摘要中也不伪造当前并不存在的可执行能力。

这是单个实施 PR 的范围拆分，不改变 EchoLens 研究 PR 中“证据产物就地动作条为 `ADOPT-NOW / P0`”的真实结论。该能力保留为后续独立任务 `SV-UX-02`，本轮不启动。

## 13. 实施与验证清单

### 13.1 计划中的前端改动面

仅允许在现有首页资源中做最小展示变更，并补充测试：

- `app/templates/index.html`：四阶段与部分结果摘要的语义结构；
- `app/static/app.css`：状态样式及移动端单列适配；
- `app/static/app.js`：纯映射/渲染函数，复用现有 Job/Case 数据；
- `tests/`：状态映射、脱敏、未知降级和零新增请求回归；
- 本文档：审计与映射依据。

若实现要求改 API、数据库、Provider、状态机或新增请求，应停止并重新评审，而不是扩展本任务范围。

### 13.2 必测场景

1. 未开始任务：四阶段均为等待态；
2. 导入中：仅“已接收”为进行中；
3. 导入完成、候选加载中；
4. Job `pending`；
5. Job `running` 且尚无素材证据；
6. Job `running` 且已有素材、正在建 Case/分析；
7. Job 与 AI 完整成功；
8. Job 成功但 AI `skipped`/`not_configured`；
9. AI 失败但 Case 保留，显示部分完成与可用结果；
10. 下载失败且无可用结果，显示失败而非部分完成；
11. Case `artifact_incomplete`，分别覆盖有/无可用产物；
12. Workbench `stale`/`recoverable` 恢复；
13. 未知 Job、Case、ASR/OCR 状态不崩溃、不全绿；
14. 恶意或敏感 `message`、路径、Token 样式字符串不进入 DOM；
15. 桌面与移动端均能读清四阶段，窄屏为单列；
16. 原有 Case 结果、Job 卡片与表单流程无回归；
17. 首页仍为 4 个自动 API / 11 个代码确定同源请求；
18. 单任务仍满足 `3 + N + 2C` 的既有流程预算，没有状态视图请求。

## 14. 实施结论与验证

`SV-UX-01` 可以在不修改后端协议的前提下实施：现有 Job、Workbench 投影、Case `primary_workflow` 与前端瞬时请求状态足以形成保守的四阶段视图。最大的正确性边界是：Job 终态不能覆盖 Case 中已经存在的可用结果，Case 标识也不能被误当成结果可用；最大的安全边界是绝不渲染原始错误消息和路径；最大的回归门禁是状态组件不得新增任何网络请求或自动重试。

EchoLens 对本任务的价值仅在于验证“长任务阶段化”和“部分结果仍可行动”的产品概念。short-video-agent 的最终实现必须继续遵守本地优先、人工确认、证据可追溯和零隐式外部动作的项目边界。

本轮实现后的验证结果：

- 状态映射、冲突证据优先级、错误脱敏、可访问结构和网络静态门禁测试通过；
- 仓库全量测试为 `421 passed`，仅保留既有 Starlette/httpx2 弃用警告；
- 本地页面冷启动实测仍为 11 个代码确定同源请求：文档、CSS、5 个 JavaScript 与 4 个既有 API；
- 390 × 844 移动视口为单列四阶段，1280 px 桌面视口为四列，均无文档级或状态项横向溢出；
- 状态变化只通过一个原子 live region 播报；阶段名称或安全失败类别发生变化时更新，相同轮询文案不会重复播报；
- 700 ms 单作品轮询与 900 ms Workbench/Profile 观察均受页面与任务代次约束；迟到响应不能倒退终态、抢占共用任务卡或跨任务写入错误文案；
- 部分失败夹具输出 `completed / completed / partial / partial`，只显示有限中文类别，不包含原始 Cookie、Authorization、Token 或本地路径；
- 验证未提交作品、未创建 Job、未调用 Provider，也未保存页面截图到仓库。
