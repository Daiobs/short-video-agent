# Workbench Task Model

本文定义 Stage B 的稳定任务 DTO。它是工作台前端读取任务状态、展示诊断和精确恢复的公共合同，不是新的任务真源，也不改变任何后台任务的持久化状态。

## 1. 真源与派生层

任务状态必须从现有真源读取：

| 任务或结果 | 真源 | Workbench 的职责 |
| --- | --- | --- |
| 后台 Job | SQLite `jobs` 记录及其 `result_json` | 只读归一化状态、进度、时间、错误和可用结果 |
| 单作品 Case | Case 数据库记录与对应 Case 产物 | 判断 Case、素材包和分析结果是否可打开 |
| Creator 流程 | Creator Runtime、sample set 与既有产物 | 派生当前六步阶段、样本计数、报告和策略入口 |
| 报告与 Strategy Plan | 既有 Creator Report / Strategy 产物 | 提供只读结果入口和陈旧风险提示 |

`GET /api/workbench/overview` 是有界、只读的聚合视图。它不得成为第二真源，不得为了展示而写回 SQLite、Runtime 或产物文件，也不得触发扫描、下载、富化、ffmpeg 或 LLM。

恢复页面读取单个 Job 时使用 `GET /api/workbench/jobs/{job_id}`。该接口返回同一统一 DTO 和经过字段允许列表裁剪的 `result_json`：只保留恢复所需的安全资源 ID、计数、队列状态和净化说明；不返回原始 Job JSON、Prompt、请求头、源码 URL、签名 URL 或本机路径。既有 `/api/jobs/{job_id}` 仍服务原工作流，Workbench 恢复入口不得调用它。

## 2. 稳定 DTO

每个任务使用以下字段：

```json
{
  "task_id": "job_xxx",
  "task_type": "profile-build-cases",
  "task_group": "创作者",
  "title": "富化创作者样本",
  "status": "running",
  "stage": "证据富化",
  "progress": 42,
  "message": "正在处理第 8 条素材",
  "error_code": "",
  "created_at": "2026-07-15T01:00:00+00:00",
  "updated_at": "2026-07-15T01:03:00+00:00",
  "resume_target": {
    "route": "profile",
    "stage": "enrich",
    "resource_id": "clone_xxx",
    "job_id": "job_xxx",
    "task_type": "profile-build-cases",
    "mode": "observe",
    "open_url": ""
  },
  "target": {
    "route": "profile",
    "stage": "enrich",
    "resource_id": "clone_xxx",
    "job_id": "job_xxx",
    "task_type": "profile-build-cases",
    "mode": "observe",
    "open_url": ""
  },
  "recoverable": true,
  "recovery_hint": "",
  "last_completed_stage": "已选样本",
  "available_results": ["素材池", "已选样本"]
}
```

字段语义：

| 字段 | 合同 |
| --- | --- |
| `task_id` | 稳定的本机任务或资源标识；不能使用路径、URL 或敏感值 |
| `task_type` | 后端任务类型，用于选择阶段与恢复说明；不能作为前端执行命令 |
| `task_group` | 面向用户的任务域，当前为“单作品”“创作者”或“系统” |
| `title` | 面向用户的任务名称 |
| `status` | 仅允许本文定义的六种统一状态 |
| `stage` | 面向用户的当前阶段文案，不承担路由职责 |
| `progress` | `0` 至 `100` 的展示进度；不是判断任务是否完成的唯一依据 |
| `message` | 经净化的用户可读状态，不包含内部异常、凭据或本机路径 |
| `error_code` | 失败诊断的稳定错误码；非失败任务可为空 |
| `created_at` / `updated_at` | UTC ISO 8601 时间；`updated_at` 用于心跳新鲜度判断 |
| `resume_target` | 结构化导航合同，见下文 |
| `target` | Stage B 兼容别名，内容必须与 `resume_target` 完全相同 |
| `recoverable` | 表示存在安全的查看或人工恢复入口，不承诺重跑一定成功 |
| `recovery_hint` | 用户可执行的检查或人工重跑建议；不得暗示系统已自动修复 |
| `last_completed_stage` | 从已保存结果推导出的最后可确认节点，而不是仅由进度百分比猜测 |
| `available_results` | 仍可读取和复用的结果名称列表，不包含文件路径或签名 URL |

## 3. 状态语义

| 状态 | 语义 | 是否写回真源 | 默认交互 |
| --- | --- | --- | --- |
| `pending` | Job 已创建、尚未开始或等待执行，且 30 分钟心跳窗口内仍属新鲜 | 否 | 查看任务；进入页面时使用 `observe` |
| `running` | Job 正在执行，且 30 分钟心跳窗口内有更新 | 否 | 查看进度；只读打开对应步骤 |
| `success` | 真源明确记录任务成功，或结果真源明确存在 | 否 | 打开结果；不重复执行 |
| `failed` | 真源明确记录失败 | 否 | 展示错误、已完成阶段、可用结果和人工恢复建议 |
| `recoverable` | 没有活动 Job，但已有 Case、素材池、选择或报告可继续查看 | 否；仅为派生状态 | 精确恢复到相应页面与步骤 |
| `stale` | 原状态为 `pending` / `running`，但 `updated_at` 早于当前时间 30 分钟以上 | **绝不写回** | 查看状态、重新打开当前步骤、由用户决定是否手动重跑 |

`stale` 是展示层判断，不代表任务必然死亡，也不等同于 `failed`。边界以 Overview 读取时刻计算：`updated_at < now - 30 minutes` 才归入 stale；数据库中的原始 `pending` / `running` 状态保持不变。

Overview 单独返回：

```json
{
  "stale_tasks": [],
  "capabilities": {
    "stale_task_count": 0
  }
}
```

列表可以有界截断，`stale_task_count` 表示真源查询得到的总数。运行任务同理使用完整 `running_task_count`，不能用首页最多显示的 5 条代替总数。

## 4. `resume_target`

`resume_target` 只描述“打开哪里、恢复什么上下文”，不描述“执行哪个动作”。固定字段如下：

| 字段 | 允许值与用途 |
| --- | --- |
| `route` | `single` 或 `profile` |
| `stage` | `import`、`processing`、`case`、`pool`、`select`、`enrich`、`distill`、`export` |
| `resource_id` | Case、aweme、本地视频或 Creator sample set 的安全标识 |
| `job_id` | 需要读取状态时使用的安全 Job 标识 |
| `task_type` | 原任务类型，供页面选择恢复说明或只读状态组件 |
| `mode` | `observe`、`manual` 或 `result` |
| `open_url` | 经过服务端和前端双重允许列表校验的同源结果路径，可为空 |

模式语义：

- `observe`：任务仍为新鲜的 `pending` / `running`，页面只读取和展示状态。
- `manual`：任务失败、stale 或存在可继续中间结果；页面恢复上下文后等待用户明确操作。
- `result`：结果已存在，直接打开 Case、报告或策略视图，不重新运行任务。

前端必须优先读取 `resume_target`。Stage B 为 Stage A 消费者保留 `target` 别名；两者必须序列化为同一个对象，禁止出现不同路由或不同资源标识。后续移除别名前必须另行版本化并完成所有消费者迁移。

`open_url` 只能是同源允许路径，例如 `/cases/{case_id}` 或既有 Creator Report 安全文件路由；不得携带 query、hash、外部域名、本机绝对路径或签名媒体 URL。即使存在 `open_url`，页面也不能因此自动发起写请求。

## 5. 状态与恢复的不变量

1. DTO 归一化不更新 Job、Case、Runtime、sample set、报告或 Strategy Plan。
2. 打开恢复目标不等于重试；只有用户在对应工作流中明确点击执行，才可以创建新 Job。
3. `progress=100` 不能替代 `status=success`，`progress<100` 也不能覆盖真源的明确成功结果。
4. `recoverable=true` 只表示有安全入口；没有足够 `resource_id` 或允许的 `open_url` 时不得伪造恢复按钮。
5. `last_completed_stage` 和 `available_results` 必须从已持久化结果推导，不能仅根据任务类型或页面内存推测。
6. 刷新 Overview 应产生一致的派生状态；除时间跨过 stale 窗口外，重复读取不应改变任何真源。

## 6. 安全与性能边界

安全边界：

- 公开文本必须净化 Cookie、Authorization、API Key、Bearer/JWT、登录 token、外部 URL 和本机绝对路径。
- `resource_id`、`job_id` 和 `open_url` 必须通过格式与同源允许列表校验；不能通过字符串 contains 判断安全性。
- DTO 不返回 Cookie 原文或掩码字段、签名媒体 URL、完整请求头、数据库位置、产物绝对路径或内部异常堆栈。
- Overview 只读；不得绕验证码、绕风控、抓取隐式登录态或修改平台状态。

性能边界：

- SQLite 使用只读、有超时和查询步数上限的连接；列表查询和每类响应数量必须有界。
- Job 的完整 `result_json` 最多解析 2 MiB；对 2–8 MiB 的大样本队列只由 SQLite 提取 `sample_set_id`、Case/作品标识和计数等小型恢复字段，不把大 JSON 载入 Overview 响应；超过 8 MiB 时安全降级。
- Runtime / sample set JSON 设文件大小与候选数量上限；来源截断通过 `meta.partial` 与 `meta.truncated_sources` 明示。
- 未进入 Runtime `sessions.json`、但已持久化 `samples.json` 的新素材池通过有界目录扫描补入恢复索引；扫描最多检查 5,000 个目录、候选最多 50 个，超限时标记 `creator_sample_sets` 部分结果，不递归扫描媒体文件。扫描目录清单使用 5 秒、最多 8 个根目录的可重建进程内缓存；Creator 根目录新增/删除条目时由目录 mtime 提前失效，不建立持久化第二真源。
- Overview 不递归读取媒体文件，不打开视频或图片，不调用 ffmpeg、LLM、Provider 或外部平台。
- 首页任务列表最多展示少量条目，但总数使用 `capabilities.running_task_count` 与 `stale_task_count`。

## 7. Stage B 验证状态

Stage B 候选实现已完成本机验证：`368 passed, 1 warning`；三个前端文件均通过 Node `--check`，Python 模块通过 `compileall`，`git diff --check` 无输出。warning 为既存 Starlette TestClient 的 httpx2 迁移提示。手动开发冒烟仍应使用临时或明确可清理的数据目录，避免污染默认 job、Case、Creator Runtime 和最近报告。
