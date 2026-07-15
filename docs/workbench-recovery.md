# Workbench Recovery

本文定义 Stage B 的任务恢复与失败诊断行为。恢复的含义是：读取真源、恢复页面上下文、跳到正确步骤并展示可用结果；它不等于自动重试，也不允许工作台自动修改任务状态。

## 1. 恢复原则

1. `resume_target` 是唯一结构化恢复入口；前端兼容读取 `target`，但不得产生另一套路由逻辑。
2. 恢复先加载 `resource_id` 指向的 Case 或 Creator sample set，再切换到 `stage`；不能只打开 `#profile` 让用户自己寻找。
3. `job_id` 只用于读取当前或最后一次任务状态；恢复页面不得因看到 Job 而自动创建新任务。
4. `observe` 只读观察，`manual` 等待人工确认，`result` 直接打开现有结果。
5. 已有下载、Case、素材池、选样、富化结果、Prompt、报告或 Strategy Plan 必须尽量保留和复用。
6. 恢复失败时显示用户可理解的说明，不显示本机路径、内部异常、Cookie、API Key 或签名 URL。
7. 恢复轮询只调用 `/api/workbench/jobs/{job_id}` 的安全状态接口；不得读取原始 `result_json`。安全接口返回精简队列后，页面从持久化 sample set / Case 再加载完整可视上下文。

## 2. 单作品恢复

### 2.1 导入与清晰度解析

适用任务：`resolve-qualities`，以及尚未形成 Case 的单作品上下文。

恢复目标：

```json
{
  "route": "single",
  "stage": "import",
  "resource_id": "aweme_id-or-local-id",
  "mode": "observe-or-manual"
}
```

- 新鲜的 `pending` / `running` 任务只恢复输入与状态，不能自动重新解析。
- 失败任务保留原作品标识，提示检查 Provider、URL 或数据源后由用户手动解析。
- 没有安全资源标识时只展示诊断，不生成不可用的恢复入口。

### 2.2 下载与 Case 构建

适用任务：`download`、`build-case`、`download-and-build-case`、`download-build-analyze-case`。

恢复目标使用 `route=single`、`stage=processing`。如结果中已有 `case_id`，同时提供允许的 `/cases/{case_id}`；如只有下载或本地视频结果，`available_results` 明确显示“已下载视频”，但不假装 Case 已完成。

- `running`：打开处理视图并只读显示 Job 状态。
- `stale`：显示最后更新时间、最后确认节点和已有结果；用户可重新打开处理步骤后自行决定是否重跑。
- `failed`：按错误码区分下载、Provider、ffmpeg/ffprobe、关键帧或 Case 构建问题；已有文件不自动删除，也不自动重复下载。
- `success`：如果 Case 已存在，优先进入 Case 结果，不重新执行构建。

### 2.3 Case、富化与单作品分析

适用任务：`analyze-case`、`enrich-case`、`asr-case`、`ocr-case`，以及已存在的 Case。

恢复目标使用 `route=single`、`stage=case`、`resource_id=case_id`、`open_url=/cases/{case_id}`。

- 已有 Case 但 AI 分析未完成时，Case 素材包、关键帧和分析输入仍可查看。
- ASR、OCR 或富化失败时，只提示检查本地依赖并人工重跑失败步骤；不重建整个 Case。
- LLM 失败时保留 Case 与证据，提示检查模型配置后人工重新分析。
- 已完成分析使用 `mode=result`，直接打开现有 Case 报告。

## 3. Creator 六步恢复

Creator 恢复必须先加载 `resource_id` 对应的 sample set / Runtime，再进入准确阶段。六步映射如下：

| 用户流程 | `stage` | 恢复内容 | 恢复后行为 |
| --- | --- | --- | --- |
| 1. 导入素材 | `import` | 原始主页、链接或导入来源的安全摘要 | 只恢复输入上下文，不自动扫描 |
| 2. 构建素材池 | `pool` | sample set、素材数量、可用指标 | 展示素材池，不自动选样 |
| 3. 选择代表样本 | `select` | sample set 与已保存的选择 | 恢复勾选和排序上下文，不自动提交选择 |
| 4. 证据富化 | `enrich` | 已选样本、富化队列、已完成 Case 与失败项 | 观察运行任务或人工重跑失败项 |
| 5. 大模型蒸馏 | `distill` | 已富化证据、Prompt、批次与已有中间结果 | 观察蒸馏或由用户手动重新执行 |
| 6. 蒸馏报告 | `export` | Creator Report、导出文件和 Strategy Plan | 只读打开结果，不重新蒸馏 |

### 3.1 素材池

`profile-scan` 成功或 Runtime 已有 sample set 时恢复到 `pool`。失败时展示数据源错误码，并提示改用已授权的作品链接、JSON / CSV、已有 Case 或本机 Chrome 辅助入口；工作台不自动重新扫描。

### 3.2 样本选择

有素材池和已保存选择时恢复到 `select`。`available_results` 至少区分“素材池”和“已选样本”，避免只依赖前端内存。恢复后允许用户调整选择，但不自动进入富化。

### 3.3 证据富化

`profile-build-cases` 对应 `enrich`：

- 新鲜任务使用 `mode=observe`，恢复队列并只读查询进度；GET 轮询属于观察，不是重试。
- stale 任务使用 `mode=manual`，展示已完成素材包数量、失败项和最后更新时间。
- 失败任务保留素材池、选样和已完成 Case；用户可以只重跑失败项，已有素材优先复用。
- 打开恢复目标不得自动再次下载、ASR、OCR 或创建新 Job。
- 即使页面中“富化完成后自动蒸馏”的旧偏好仍为勾选状态，Workbench 恢复路径也必须强制关闭自动衔接；该偏好只适用于用户刚刚主动启动的正常富化流程。

### 3.4 大模型蒸馏

`creator-clone-distill` 与 `creator-clone-batch-distill` 对应 `distill`：

- 运行中只展示任务状态、批次或已有中间结果。
- LLM 失败时展示 `error_code`，保留素材池、富化证据、批次摘要和 Prompt，并提示检查 API Base、Key、网络、余额和模型后人工重跑。
- stale 只说明心跳停止更新，不判定模型请求必然失败。
- 不自动缩短、重发或切换模型，不自动改变任务状态。

### 3.5 报告

Creator Report 已存在时恢复到 `export`，使用 `mode=result`。页面加载 sample set 和报告真源后立即显示已有报告；恢复入口不触发重新蒸馏。报告文件缺失时明确显示缺失状态，不使用本地简化结果伪装成 LLM 报告。

### 3.6 Strategy Plan

Strategy Plan 属于 Creator 结果阶段，恢复到 `profile/export` 并打开既有策略入口。若其修改时间明显早于 Creator Report，可显示 `stale` 风险，但这只表示派生结果可能需要更新：

- 不自动重新生成 Strategy Plan。
- 不把对应 Creator 任务改为失败。
- 用户可以先查看旧方案，再从报告页面明确发起新的方案生成。

## 4. Stale 行为

stale 心跳窗口固定为 30 分钟。Overview 读取时，原始状态为 `pending` 或 `running` 且 `updated_at` 早于窗口的任务进入 `stale_tasks`；完整数量写入 `capabilities.stale_task_count`。

stale 卡片必须展示：

- “任务可能已停止更新”；
- 最后更新时间和原任务阶段；
- `last_completed_stage`；
- `available_results`；
- `recovery_hint`；
- “查看状态”和安全的“重新打开当前步骤”入口。

严格禁止：

- 把 stale 回写成 `failed`、`success` 或其他状态；
- 因页面刷新延长或重置任务心跳；
- 自动重试、自动创建替代 Job、自动删除旧任务；
- 把 stale 当作任务一定停止的结论。

用户人工重跑时应创建新的、可追踪的执行记录；旧任务保留用于诊断。是否提供取消或归档属于后续独立设计，不在 Stage B 范围内。

## 5. 失败任务行为

失败任务至少展示：

| 字段 | 用户价值 |
| --- | --- |
| `error_code` | 可搜索、可归类的稳定失败原因 |
| `message` | 经净化的人类可读说明 |
| `last_completed_stage` | 确认失败前已完成到哪里 |
| `available_results` | 哪些 Case、素材池、证据、Prompt 或报告仍可用 |
| `recovery_hint` | 检查什么、返回哪一步、如何人工重跑 |
| `resume_target` | 精确打开正确页面和阶段 |

常见恢复类别：

- `LLM_*` / `AUTO_ANALYSIS_FAILED`：保留素材包和证据，检查模型配置后人工重跑分析或蒸馏。
- `PROFILE_BUILD*`：保留素材池、选样和已完成素材包，只人工重跑失败富化项。
- `ASR_*` / `OCR_*` / `ENRICHMENT_*`：打开 Case，检查本地依赖后只重跑对应富化步骤。
- `DOWNLOAD_*` / `QUALITY_*` / `PROVIDER_*` / `URL_*`：返回原任务页面重新解析或下载；已有 Case 或下载结果继续可用。
- `PROFILE_SCAN*` / `DOUYIN_*` / `COOKIE_*`：返回 Creator 导入，检查数据源或改用其他已授权入口。
- `CASE_BUILD*` / `FFMPEG_*` / `FFPROBE_*` / `KEYFRAME_*`：检查本地媒体工具，保留已有下载文件后人工构建。

恢复提示不能声称失败已被修复，也不能把 `recoverable=true` 解释为自动恢复成功。

## 6. 只读查看与人工重跑边界

工作台可以自动执行的动作仅限：

- GET Overview 或 Job 状态；
- 加载现有 Case、sample set、Runtime、报告与 Strategy Plan；
- 切换到 `resume_target.stage`；
- 渲染诊断、已有结果和安全入口。

工作台不得因恢复操作自动执行：

- 主页扫描、Provider 解析或下载；
- Case 构建、ASR、OCR、证据富化；
- LLM 分析、批量蒸馏或 Strategy 生成；
- Job 重试、状态修正、删除或归档。

现有 Case 详情 GET 在加载时可能刷新 `analysis_input`、worksheet、质量诊断和 rerun plan 等可重建派生产物；Stage B 沿用该既有 Case 行为，但不会因此创建 Job、重跑 Provider/LLM 或修改任务状态。把 Case 详情路由进一步拆成严格只读读取与显式派生刷新，属于后续独立技术债，不在本阶段扩展。

人工重跑必须由用户在恢复后的页面明确点击，并沿用既有写操作 Origin / Referer 校验与本机安全边界。页面可以说明将复用哪些已有结果，但不能在点击前预先执行。

## 7. Stage B 验收矩阵

以下结果已完成最终验证：

- 单作品任务能恢复到 `import`、`processing` 或 `case`，已有 Case 可直接打开。
- Creator 素材池、选择、富化、蒸馏、报告和 Strategy 均恢复到正确步骤。
- stale 任务进入独立列表，总数准确，数据库原状态不变。
- 失败任务展示错误码、最后完成阶段、可用结果和可执行提示。
- 刷新只读取状态，不自动重试、不自动修改任务状态。
- Overview 与页面不泄露凭据、签名 URL、本机路径或内部异常。
- Workbench 恢复只调用安全 Job 接口；安全响应后从持久化 sample set / Case 恢复上下文，不使用精简队列覆盖完整数据。
- 只有 `samples.json`、尚未建立 Runtime 会话的素材池仍可恢复到素材池或选样步骤。
- `pytest -q` 为 `368 passed, 1 warning`；相关 JavaScript `node --check`、Python `compileall` 与 `git diff --check` 完整通过。

手动开发冒烟必须使用临时或明确可清理的数据目录，避免污染默认 job、Case、Creator Runtime 和最近报告。Stage B 完成后只创建 Draft PR，等待人工审查；不合并，也不进入 Stage C。
