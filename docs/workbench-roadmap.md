# Workbench Roadmap

本文记录“任务驱动的短视频拆解工作台”的长期阶段、阶段边界和验收状态。Stage A-D 已完成审查并合并；Stage E 已明确取消，不启动。后续维护仍必须从最新 `main` 创建独立分支和 Draft PR，等待人工审查，不得自动合并。

## 长期阶段 A-E

| 阶段 | 建议分支 | 纵向目标 | 入口条件 | 当前状态 |
| --- | --- | --- | --- | --- |
| Stage A | `codex/workbench-task-console-v1` | 将 `/` 升级为任务控制台，聚合运行中任务、可继续任务、最近结果和能力状态 | Workbench Shell v1 已进入 `main` | 已合并：PR #12，`48b7feeb8279d548ebe7f0d0343d6f3af378eab8` |
| Stage B | `codex/workbench-recovery-v1` | 统一任务状态、精确恢复目标、失败诊断和 stale 任务处理 | Stage A 已合并，用户已明确授权 | 已合并：PR #13，`98293b802919c32dc2037c6c438a13f3aee9093f` |
| Stage C | `codex/workbench-library-v1` | 建立 Case、Creator Report 和 Strategy Plan 的只读资产库 | Stage B 经审查后合并 | 已完成：PR #14，`e1628f8174938a9493a1c2e8c14dc16373f943bd`；治理记录 PR #15，`9883c6ae0a4585d031fea8191e7a4ed9c4153e5f` |
| Stage D | `codex/frontend-modules-v1` | 在不引入框架和构建链的前提下拆分前端模块 | Stage C 合并且行为稳定 | 已完成并合并：`8e32166a8f377435380122204c33334034ec44eb` |
| Stage E | 不创建 | 原计划的 Douyin 本地连接器研究 | 已取消 | 已取消，不启动；禁止浏览器 Cookie 自动读取、本地连接器扩展、签名破解和验证码绕过 |

每个阶段必须从最新 `main` 新建独立分支，形成一个可单独合并的纵向切片，运行该阶段要求的完整测试，创建 Draft PR 后等待人工审查。不得自动合并，也不得自动进入下一阶段。

## Stage A：Workbench Task Console v1

### 目标

Stage A 将首页从功能说明页改为任务控制台，使用户打开工作台后按以下优先级获得下一步：

1. 有运行中任务时，优先看到任务类型、阶段、进度、时间和当前消息，并可查看任务或进入对应页面。
2. 没有运行中任务但有可继续任务时，优先看到任务当前步骤、样本与报告状态，并可继续单作品或创作者拆解。
3. 没有任务时，显示“分析单条作品”和“分析创作者账号”两个主入口。
4. 第一屏之后提供紧凑能力状态、最近结果和“导入 → 富化 → 拆解 → 复用”帮助区。

Stage A 必须保持单作品拆解、Creator Clone、报告即时显示、刷新恢复、唯一设置入口和现有本机安全合同不回归。

### 范围与边界

Stage A 范围内：

- 新增只读 `GET /api/workbench/overview` 聚合接口。
- 聚合运行中任务、可继续任务、最近 Case、Creator Report、Strategy Plan、失败任务和能力摘要。
- 首页依据聚合结果渲染运行中、可继续、空状态、最近结果、部分失败和来源失败状态。
- 每类最近结果只返回并展示少量条目；配置修改仍只从右上角齿轮进入。
- 单个数据源失败时保留其他来源，并通过 `source_errors` 明确降级。

Stage A 不负责：

- 自动取消、自动重试、自动推进工作流或自动修改任务状态。
- 完整的恢复建议、stale 状态模型和失败诊断；这些属于 Stage B。
- 资产库、复杂搜索筛选或新的报告真源；这些属于 Stage C。
- 拆分 `app.js`、引入前端框架或构建工具；模块化属于 Stage D。
- 浏览器扩展、本地连接器、新平台、自动发布或账号运营能力。

### 数据源与真源

Overview 只聚合已有本机状态，不建立第二真源：

| 来源 | Stage A 读取内容 | 明确不读取或不触发 |
| --- | --- | --- |
| 任务数据库 | job 状态、进度、消息、错误码和时间元数据 | 不写任务，不执行任务，不自动重试 |
| Case 索引与产物 | Case 标识、标题、状态、时间及必要文件是否存在 | 不读取视频或图片内容，不递归扫描全部 Case |
| Creator Runtime 索引 | session/project 标识、工作流状态和更新时间 | 不重放动作，不改变 Runtime 状态 |
| Creator Clone 产物 | 样本计数、报告与 Strategy Plan 的存在性和更新时间 | 不重新蒸馏，不调用 LLM，不复制报告数据 |
| 本机能力状态 | Douyin 数据源最近一次已知健康状态、LLM 是否配置、本地工具摘要 | 不进行平台自检，不启动子进程，不发起远程请求 |

除非后续审计证明现有存储无法支持，Stage A 不新增数据库表。任何派生索引都不能替代数据库、Runtime 或既有产物文件作为真源。

### 安全原则

- 延续 loopback-only、本机 Host 限制和写操作 Origin/Referer 校验；Overview 本身保持只读。
- 响应不得包含 Cookie 原文或掩码字段、API Key、登录 token、签名媒体 URL、本机绝对路径或敏感配置值。
- 对可展示标题、消息、错误和标识做白名单或净化处理；文件入口继续使用既有安全路由。
- Cookie 仍由用户主动配置，不进入数据库、素材包、Prompt、日志或 Overview；本机 Chrome 辅助不读取 Cookie。
- 单个来源异常必须安全降级，不得因一个索引损坏而阻断整个首页，也不得把内部异常细节直接返回给页面。
- 不绕验证码、不绕风控、不做签名破解，不新增隐式登录态采集。

### 性能原则

- Overview 只读取必要元数据，使用只读、限时和有界查询。
- 每个首页区块限制返回数量；Case 候选、Runtime 候选和单文件大小均设置上限。
- 不递归扫描全部大文件，不读取媒体内容，不调用 ffmpeg、LLM 或外部平台。
- 来源被截断或部分失败时返回明确元信息，不能静默伪装为完整结果。
- Stage A 验收前必须增加至少 500 个 Case、任务或报告条目的规模测试；如需缓存，只允许可重建缓存或分页，不建立不可恢复的第二真源。

## Stage A 完成项

以下项目已经通过自动化与本机冒烟验证，并随 PR #12 合并到 `main`：

- Workbench Shell v1、Creator Clone 报告即时显示、唯一设置入口和六步任务流程已作为 Stage A 基线进入 `main`，并完成本阶段回归验证。
- `GET /api/workbench/overview` 的只读路由与聚合服务已合并并接入应用路由。
- Overview 响应已覆盖 `running_tasks`、`resumable_tasks`、`recent_cases`、`recent_creator_reports`、`recent_strategy_plans`、`recent_failures`、`capabilities`、`source_errors` 和截断元信息。
- job、Case、Creator Runtime、Creator Clone 产物采用来源级独立读取；单一来源失败时保留其他区块并安全降级。
- Douyin 数据源采用最近一次已知健康状态，LLM 只汇总是否配置，本地工具只做无网络、无子进程的摘要检查。
- 实现已加入结果数量、数据库查询、Runtime 候选和 JSON 文件大小上限，并对公开文本、资源标识和输出入口进行约束。
- Strategy Plan 列表已比较报告与方案更新时间，并把明显早于报告的方案标记为 `stale`；该规则仍不能完全证明方案语义上新鲜。
- 首页已按“运行中任务 → 可继续任务 → 新建任务”的顺序渲染，并通过 Node 行为测试覆盖三种优先级和接口失败降级。
- 首页已展示紧凑的 Douyin 数据源、LLM、本地工具和运行任务状态；最近 Case、Creator Report、Strategy Plan 和失败任务各限制最多 5 条。
- Overview 已覆盖空状态、来源失败、文件缺失、畸形 `samples.json`、Bearer token 脱敏、超限 Runtime 索引、500 条规模和只读文件树测试。
- 完整测试、JavaScript 语法、Python 编译、实际 HTTP 冒烟和浏览器响应式检查均已通过，详见测试记录。

## 当前维护

- Stage D 已合并；Creator 报告视图与设置弹窗已建立显式模块边界。
- Creator Runtime、六步流程状态、任务轮询、恢复合同、单作品流程和 Strategy Plan 编排仍由 `app.js` 持有，继续避免第二状态源。
- 当前维护分支强化个人账号 Cookie + Douyin Web API 主页扫描主路径；合同见 `docs/douyin-cookie-provider.md`。
- Stage E 已取消，不创建 `research/douyin-local-connector`，也不接入新的隐式采集路径。

## 已否决

- 否决为 Overview 新建不可重建的数据副本或第二真源；当前范围不新增数据库表。
- 否决在 Overview 请求中触发远程调用、平台自检、扫描、下载、媒体解析、ffmpeg 或 LLM。
- 否决自动取消、自动重试、自动推进下一阶段，以及把 stale 任务自动改成 failed。
- 否决在首页或 API 暴露 Cookie、API Key、token、签名 URL、敏感配置或本机绝对路径。
- 否决继续把首页第一屏用作大段产品功能介绍。
- 否决在 Stage A 同时交付资产库、前端模块化、浏览器扩展、新平台、自动发布或账号矩阵能力。
- 否决在 Stage B Draft PR 后自动合并或直接开始 Stage C。

## 已知问题

### 1. 测试运行数据隔离（已关闭）

已关闭：Stage A 新增测试显式注入临时 SQLite 和临时产物目录；测试结束后不污染默认 job、Case、Creator Runtime 或最近报告。

开发注意事项：手动开发冒烟仍应使用临时或明确可清理的数据目录。

### 2. 旧 stale job

历史 `pending` 或 `running` job 可能已失去心跳但仍保留旧状态。Stage B 以 30 分钟心跳窗口派生 `stale` 展示，并在 Overview 中单列 `stale_tasks` 与 `stale_task_count`。该判断只影响只读 DTO，不回写数据库、不把原任务改成 `failed`，也不触发重试；恢复提示和人工重新执行入口正在本阶段实现。

### 3. Strategy Plan 陈旧性风险

仅比较 Strategy Plan 与 Creator Report 的文件更新时间，无法证明样本选择、证据或其他上游输入没有变化；时间戳粒度和外部文件操作也可能产生误判。当前候选状态只能提示风险，不能消除语义陈旧性。Stage A 应覆盖明显过期方案被标记为 `stale` 的测试，Stage B/C 再设计可追踪的输入版本或派生索引策略。

### 4. Runtime 与资产索引截断

为限制请求成本，Creator Runtime 和 Stage C 资产库都只检查有界数量的最新候选。超过上限时，较旧任务或产物可能不在当前索引中；响应会把来源标记为截断和部分结果，页面显示非阻断式提示。Stage C 提供分页与安全元数据搜索，但仍不承诺越过单源硬上限的无限历史扫描。

## Stage B 合并状态

Stage B 已通过 PR #13 完成人工审查，并以 squash commit `98293b802919c32dc2037c6c438a13f3aee9093f` 合并到 `main`。Stage C 启动前同步后的 `main` 与该 merge commit 一致，工作区干净，基线回归为 `370 passed, 1 warning`。

Stage B 当前范围固定为：

1. 统一任务 DTO，状态仅使用 `pending`、`running`、`success`、`failed`、`recoverable`、`stale`。
2. 使用结构化 `resume_target` 精确恢复到单作品或 Creator 六步流程的正确页面与步骤。
3. 失败任务展示 `error_code`、`last_completed_stage`、`available_results` 和 `recovery_hint`。
4. 对超过 30 分钟未更新的 `pending` / `running` 任务派生 `stale` 视图；Overview 新增 `stale_tasks` 和 `capabilities.stale_task_count`。
5. 恢复入口只负责读取状态和导航；不自动重试、不自动执行工作流、不修改任务数据库状态。

稳定 DTO 见 `docs/workbench-task-model.md`，逐流程恢复行为见 `docs/workbench-recovery.md`。Stage B 已关闭无资源旧失败 Job 被伪标记为可恢复的问题；只有安全资源目标或可观察的活跃 Job 才能恢复业务上下文。

## Stage C 完成状态

Stage C 基线为 `main` 的 `98293b802919c32dc2037c6c438a13f3aee9093f`，分支为 `codex/workbench-library-v1`。PR #14 已完成人工验收，并以 squash commit `e1628f8174938a9493a1c2e8c14dc16373f943bd` 合并到 `main`。本阶段合同见 `docs/workbench-library.md`：

1. 新增独立 `/library` 页面，不把完整历史浏览继续塞入首页 DOM。
2. 新增有界、只读 `GET /api/library/assets`，统一 Case、Creator Report 和 Strategy Plan DTO。
3. 只读取安全元数据和已知文件存在性，不读取媒体正文，不调用外部服务、ffmpeg 或 LLM。
4. 支持关键词、类型、状态、日期、分页和来源级部分失败。
5. Creator 返回入口复用 Stage B 精确恢复能力，但只有安全可读的 `samples.json` 才能恢复到 `profile/export`，且不自动执行任何业务步骤。
6. 单源上限、JSON 大小和请求预算均明确；截断必须作为部分结果展示。

Stage C 已知边界：Runtime `DONE`、Creator 报告文件或 Strategy Plan 单独存在，都不能证明 Creator 上下文可恢复。资产仍按真实文件状态列出；HTML/Markdown 报告可以独立打开，但缺失、损坏、超大或不可读取的 `samples.json` 不生成“返回 Creator”入口。

合并后 `main` 已完成完整回归和只读 HTTP 冒烟；Stage C 的治理记录由 PR #15 以 squash commit `9883c6ae0a4585d031fea8191e7a4ed9c4153e5f` 合并。Stage D 从该最新 `main` SHA 启动，不复用 Stage C 分支。

## Stage D 完成状态

Stage D 基线为 `main` 的 `9883c6ae0a4585d031fea8191e7a4ed9c4153e5f`，最终以 `8e32166a8f377435380122204c33334034ec44eb` 合并。本轮未引入前端框架或构建链，只建立显式、可测试的浏览器模块边界：

1. `CreatorReportView` 只负责 Creator 蒸馏报告的 HTML 生成、挂载、空状态和渲染失败降级；报告数据获取、工作流推进、Runtime 与 Strategy Plan 仍由 `app.js` 编排。
2. `SettingsPanel` 只负责设置弹窗交互、配置状态展示和既有设置 API 调用；敏感值不进入页面，调用方只注入 DOM、请求函数和必要回调。
3. 首页使用固定脚本顺序显式加载模块，不引入动态加载器，不增加隐式全局状态。
4. 模块 API 使用冻结命名空间；初始化可重复执行，避免重复绑定事件。
5. 依赖方向、DOM/API 所有权、事件合同和暂不拆分的高风险边界记录在 `docs/frontend-modules.md`。

Stage D 当前边界：`app.js` 仍然较大，但本轮刻意不拆 Creator 六步状态机、轮询、恢复、单作品和 Strategy Plan。后续模块化必须继续以单一状态源和现有 Workbench 合同为门禁，不能仅为了减少行数迁移状态。

## Douyin Cookie Provider 维护

Stage D 合并后，主页扫描正式主路径收敛为用户主动配置的个人账号 Cookie + 现有 Douyin Web API Provider。维护范围包括安全诊断、稳定错误分类、有界分页、有界重试和明确降级，不新增数据源或绕过能力。

- Cookie 只保存在本机运行时配置，不进入数据库、Job、Creator/Case 产物、Prompt、报告、日志或浏览器存储。
- 默认每页 20、配置最大 10 页，硬上限 20 页 / 200 条；重复 cursor、空页、连续无新增和分页合同异常立即停止。
- 每页最多一次重试，只覆盖网络错误、timeout、429 和 5xx。
- 主页主路径失败时保留作品链接、JSON/CSV、已有 Case 和既有公开页面回退；不会自动启动 Chrome 或读取浏览器 Cookie。
- Stage E 明确取消。本维护不创建本地连接器、浏览器扩展、签名破解、验证码处理或批量账号能力。

## 测试记录

| 检查项 | 状态 | 结果或证据 |
| --- | --- | --- |
| Stage C 最新 `main` 基线 `pytest -q` | 通过 | `370 passed, 1 warning in 49.11s`；基线 `98293b802919c32dc2037c6c438a13f3aee9093f` |
| Stage A 完整 `pytest -q` | 通过 | `356 passed, 1 warning in 50.96s` |
| `node --check app/static/app.js` | 通过 | 使用 Codex bundled Node.js |
| `node --check app/static/workbench.js` | 通过 | 使用 Codex bundled Node.js |
| 新增 JavaScript 模块 `node --check` | 通过 | `app/static/workbench-tasks.js` |
| `git diff --check` | 通过 | 无空白或补丁格式错误 |
| Overview API 正常、空状态与来源失败 | 通过 | `tests/test_workbench_overview.py` 与 Node 任务优先级、截断提示、5/500 计数测试 |
| 文件缺失、stale、敏感字段与截断 | 通过 | 覆盖 Bearer/JWT、畸形样本、超限 Runtime 索引和 Strategy stale |
| 报告即时显示与刷新恢复 | 通过 | 既有 Creator Clone 回归测试进入完整测试套件 |
| 500 条规模测试 | 通过 | 500 Jobs + 500 Cases + 500 Creator 记录；有界结果与读取次数 |
| 实际 HTTP 冒烟 | 通过 | `/` 与 `/api/workbench/overview` 均返回 200；热请求约 0.04 秒，响应约 9 KiB |
| 浏览器、移动端与键盘检查 | 通过 | 1280 / 1024 / 390 视口无横向溢出；当前本机数据渲染成功，控制台错误 0 |

### Stage B 测试记录

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 完整 Python 测试 | 通过 | 合并后 `main` 回归为 `370 passed, 1 warning`；warning 为 Starlette TestClient 的 httpx2 迁移提示 |
| JavaScript 语法 | 通过 | `app.js`、`workbench.js`、`workbench-tasks.js` 均通过 bundled Node `--check` |
| Python 编译 | 通过 | Stage B 新增/修改的任务 DTO、Overview、Job 路由和测试隔离模块通过 `compileall` |
| 差异格式 | 通过 | `git diff --check` 无输出 |
| 测试数据隔离 | 通过 | 完整测试前后默认 SQLite SHA-256 与 `outputs` 文件树指纹一致；测试使用逐用例临时数据库和产物目录 |
| HTTP / 浏览器冒烟 | 通过 | `/` 与 Overview 正常渲染；5,639 个 Creator 目录下冷请求约 0.46 秒，短 TTL 缓存后的热请求约 0.05 秒，响应约 18 KiB；旧任务显示 stale；恢复后精确进入 Creator 第 5 步；失败 Case 进入对应详情页；控制台错误 0 |
| 不自动修改状态 | 通过 | stale Creator Job 恢复前后仍为原始 `running`、进度与 `updated_at` 不变，未触发自动重试 |
| 安全恢复接口 | 通过 | Workbench 只读取 `/api/workbench/jobs/{job_id}`；响应不含原始 Job JSON、签名 URL、Prompt、请求头或本机路径，恢复富化不会自动进入蒸馏 |
| 素材池兜底索引 | 通过 | 只有 `samples.json`、尚未进入 Runtime 会话的素材池可恢复到素材池/选样；扫描与响应均有硬上限，超限明确标记部分结果 |

### Stage C 测试记录

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 完整 Python 测试 | 通过 | 合并后 `main` 为 `379 passed, 1 warning in 50.30s`；warning 仍为 Starlette TestClient 的 httpx2 迁移提示 |
| JavaScript 语法 | 通过 | `app.js`、`workbench.js`、`workbench-tasks.js` 与新增 `library.js` 均通过 bundled Node `--check` |
| Python 编译与差异格式 | 通过 | `python -m compileall -q app tests` 与 `git diff --check` 无错误 |
| 三类资产合同 | 通过 | Case、Creator Report、Strategy Plan 使用统一 DTO；类型/状态/关键词/日期/分页均有 API 测试 |
| 安全边界 | 通过 | 覆盖 Cookie、Authorization、Bearer、API Key、`sk-` Key、本机路径、外部/签名 URL、路径穿越、非法 ID、符号链接、损坏和超大 JSON |
| 来源降级 | 通过 | Case 数据库不可用时 Creator 资产仍返回；损坏或截断来源使用 `source_errors` / `meta.partial` 非阻断展示 |
| Creator 恢复入口真实性 | 通过 | Runtime-only `DONE`、缺失/损坏 `samples.json` 不生成恢复目标；报告直链与 Creator 恢复相互独立；有效 sample set 仍恢复到 `profile/export` 且不创建 Job |
| 500×3 规模 | 通过 | 500 Case + 500 Creator Report + 500 Strategy Plan，测试用例约 0.74 秒；结果分页为 100，响应小于 250 KiB，缓存命中不重复读取 JSON |
| 实际 HTTP | 通过 | `/`、`/library`、Overview 与资产 API 均返回 200；当前 2,000+ 本机资产冷索引约 2.05 秒，30 秒快照内筛选/翻页约 0.03 秒，20 条响应约 18 KiB |
| 响应式与恢复 | 通过 | 1280 / 1024 / 390 视口无页面横向溢出；桌面为紧凑表格、手机为卡片；Creator 返回后进入既有 `export` 阶段且未创建任务 |

### Stage D 当前验证记录

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 完整 Python 测试 | 通过 | `381 passed, 1 warning`；warning 仍为 Starlette TestClient 的 httpx2 迁移提示 |
| 模块行为测试 | 通过 | Creator 报告覆盖缺失 DOM、空/畸形输入、转义、失败降级与 API 冻结；设置覆盖缺失 DOM、重复初始化、保存/测试请求和敏感输入不回显 |
| JavaScript 语法 | 通过 | `app.js`、`workbench.js`、`workbench-tasks.js`、`library.js`、`creator-report-view.js` 与 `settings-panel.js` 均通过 bundled Node `--check` |
| Creator 报告恢复 | 通过 | 已有 Creator 素材池进入 `#profile` 后报告与 Strategy Plan 首次加载即显示，不依赖手动刷新 |
| 设置弹窗 | 通过 | 可打开、关闭和重新打开；非敏感设置保存成功；API Key 与 Cookie 输入框不回显已保存原文 |
| 资产恢复合同 | 通过 | `/library` 返回有效 Creator 后恢复报告与 Strategy Plan；Job 总数操作前后均为 9730，未创建任务 |
| 实际 HTTP | 通过 | `/`、`/library`、Overview、资产 API 与 `/calibration` 均返回 200；资产 API 保持 `Cache-Control: no-store` |
| 响应式 | 通过 | 1280 / 1024 / 390 视口下首页报告、设置弹窗与资产库均无页面级横向溢出；手机端六步条保留既有的区块内横向滚动 |

Stage D 已合并到 `main`；上述结果对应合并候选实现。后续 Cookie Provider 维护使用独立分支，不复用 Stage D 分支。

开发注意事项：手动开发冒烟仍应使用临时或明确可清理的数据目录，避免污染默认 job、Case、Creator Runtime 或最近报告。

浏览器自动化若不可用，必须记录实际 HTTP 冒烟、Node 纯函数或 DOM 行为模拟的替代结果，并明确列出未覆盖项。

## 阶段 PR 记录

| 字段 | 当前记录 |
| --- | --- |
| Stage A 状态 | 已完成并合并 |
| Head 分支 | `codex/workbench-task-console-v1` |
| Base 分支与基线 commit | `main` / `a4f0dd1` |
| PR 编号 | #12 |
| PR 链接 | `https://github.com/Daiobs/short-video-agent/pull/12` |
| 人工审查结论 | 通过；由用户明确授权 Ready for review 与 squash merge |
| 合并状态 | 已 squash merge |
| 合并 commit | `48b7feeb8279d548ebe7f0d0343d6f3af378eab8`（`Add task-first workbench console`） |
| 合并后回归 | `356 passed, 1 warning` |
| Stage B 状态 | 已完成并合并 |
| Stage B PR | #13，已由用户授权审查并 squash merge |
| Stage B 合并 commit | `98293b802919c32dc2037c6c438a13f3aee9093f` |
| Stage C 分支 | `codex/workbench-library-v1` |
| Stage C 基线 | `main` / `98293b802919c32dc2037c6c438a13f3aee9093f` |
| Stage C 状态 | 已完成并合并 |
| Stage C PR | #14，已由用户人工验收并授权 Ready for review 与 squash merge |
| Stage C 合并 commit | `e1628f8174938a9493a1c2e8c14dc16373f943bd`（`Add read-only workbench asset library`） |
| Stage C 合并后回归 | `379 passed, 1 warning`；四个 JavaScript 文件、`compileall`、`git diff --check` 与四个 HTTP 入口均通过 |
| Stage C 治理记录 | PR #15，`9883c6ae0a4585d031fea8191e7a4ed9c4153e5f`（`Record Stage C merge`） |
| Stage D 分支与基线 | `codex/frontend-modules-v1` / `9883c6ae0a4585d031fea8191e7a4ed9c4153e5f` |
| Stage D 当前范围 | Creator 报告视图与设置弹窗低风险提取；完整合同见 `docs/frontend-modules.md` |
| Stage D 状态 | 已完成并合并；merge SHA `8e32166a8f377435380122204c33334034ec44eb` |
| Stage E 状态 | 已取消，不启动 |
