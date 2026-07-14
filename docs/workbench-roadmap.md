# Workbench Roadmap

本文记录“任务驱动的短视频拆解工作台”的长期阶段、阶段边界和验收状态。当前只执行 Stage A；文中“候选完成”表示实现已进入阶段工作树，但仍需集成审查、完整测试和 Draft PR 审查，不能视为已经验收或合并。

## 长期阶段 A-E

| 阶段 | 建议分支 | 纵向目标 | 入口条件 | 当前状态 |
| --- | --- | --- | --- | --- |
| Stage A | `codex/workbench-task-console-v1` | 将 `/` 升级为任务控制台，聚合运行中任务、可继续任务、最近结果和能力状态 | Workbench Shell v1 已进入 `main` | 候选完成，等待 Draft PR 人工审查 |
| Stage B | `codex/workbench-recovery-v1` | 统一任务状态、精确恢复目标、失败诊断和 stale 任务处理 | Stage A 经审查后合并，并获得人工确认 | 未开始 |
| Stage C | `codex/workbench-library-v1` | 建立 Case、Creator Report 和 Strategy Plan 的只读资产库 | Stage B 经审查后合并 | 未开始 |
| Stage D | `codex/frontend-modules-v1` | 在不引入框架和构建链的前提下拆分前端模块 | Stage C 合并且行为稳定 | 未开始 |
| Stage E | `research/douyin-local-connector` | 研究 Douyin 本地连接器的权限、配对协议和威胁模型 | Stage A-D 完成，或用户明确要求提前研究 | 未开始；默认不接入生产流程 |

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

## 当前完成项（待人工审查）

以下项目已经通过本分支自动化与本机冒烟验证，但在 Draft PR 获得人工审查并合并前，Stage A 仍不能视为完成：

- Workbench Shell v1、Creator Clone 报告即时显示、唯一设置入口和六步任务流程已作为 Stage A 基线进入 `main`，仍需在本阶段做回归验证。
- `GET /api/workbench/overview` 的只读路由与聚合服务已有候选实现，并已接入应用路由候选改动。
- 候选响应已覆盖 `running_tasks`、`resumable_tasks`、`recent_cases`、`recent_creator_reports`、`recent_strategy_plans`、`recent_failures`、`capabilities`、`source_errors` 和截断元信息。
- job、Case、Creator Runtime、Creator Clone 产物采用来源级独立读取；单一来源失败时保留其他区块的候选降级逻辑。
- Douyin 数据源采用最近一次已知健康状态，LLM 只汇总是否配置，本地工具只做无网络、无子进程的摘要检查。
- 候选实现已加入结果数量、数据库查询、Runtime 候选和 JSON 文件大小上限，并对公开文本、资源标识和输出入口进行约束。
- Strategy Plan 候选列表已比较报告与方案更新时间，并把明显早于报告的方案标记为 `stale`；该规则仍不能完全证明方案语义上新鲜。
- 首页已按“运行中任务 → 可继续任务 → 新建任务”的顺序渲染，并通过 Node 行为测试覆盖三种优先级和接口失败降级。
- 首页已展示紧凑的 Douyin 数据源、LLM、本地工具和运行任务状态；最近 Case、Creator Report、Strategy Plan 和失败任务各限制最多 5 条。
- Overview 已覆盖空状态、来源失败、文件缺失、畸形 `samples.json`、Bearer token 脱敏、超限 Runtime 索引、500 条规模和只读文件树测试。
- 完整测试、JavaScript 语法、Python 编译、实际 HTTP 冒烟和浏览器响应式检查均已通过，详见测试记录。

## 明确未完成

- Stage A Draft PR #12 已创建；人工审查、合并和合并 commit 均未完成。
- Stage B 未开始，当前不得实现其统一恢复模型、自动诊断或 stale 任务操作。

因此，当前不能宣布 Stage A 完成。

## 已否决

- 否决为 Overview 新建不可重建的数据副本或第二真源；当前范围不新增数据库表。
- 否决在 Overview 请求中触发远程调用、平台自检、扫描、下载、媒体解析、ffmpeg 或 LLM。
- 否决自动取消、自动重试、自动推进下一阶段，以及把 stale 任务自动改成 failed。
- 否决在首页或 API 暴露 Cookie、API Key、token、签名 URL、敏感配置或本机绝对路径。
- 否决继续把首页第一屏用作大段产品功能介绍。
- 否决在 Stage A 同时交付资产库、前端模块化、浏览器扩展、新平台、自动发布或账号矩阵能力。
- 否决在 Draft PR 后自动合并或直接开始 Stage B。

## 已知问题

### 1. 测试运行数据未隔离

测试、开发运行和本机真实状态若复用默认数据库或产物根目录，Overview 可能把测试 job、Case 或 Creator 产物当作最近结果。验收前应让相关测试显式注入临时数据库和临时产物目录，并确认测试结束后不污染默认运行数据。该项当前未关闭。

### 2. 旧 stale job

历史 `pending` 或 `running` job 可能已失去心跳但仍保留旧状态。当前候选实现用更新时间窗口避免其占据“正在运行”，但不会展示 stale 诊断，也不会修改原状态。Stage A 需验证旧记录不会污染运行中数量；显式 stale 状态、恢复提示和人工重新执行入口留给 Stage B。

### 3. Strategy Plan 陈旧性风险

仅比较 Strategy Plan 与 Creator Report 的文件更新时间，无法证明样本选择、证据或其他上游输入没有变化；时间戳粒度和外部文件操作也可能产生误判。当前候选状态只能提示风险，不能消除语义陈旧性。Stage A 应覆盖明显过期方案被标记为 `stale` 的测试，Stage B/C 再设计可追踪的输入版本或派生索引策略。

### 4. Runtime 索引截断

为限制请求成本，Creator Runtime 只检查有界数量的最新候选。超过上限时，较旧但仍可继续的任务或报告可能不出现在首页；候选响应会把该来源标记为截断和部分结果。Stage A 需验证提示与降级行为，完整历史浏览或分页属于后续资产库范围。

## Stage B 入口条件

只有同时满足以下条件，才可从最新 `main` 新建 `codex/workbench-recovery-v1`：

1. Stage A 的 API、首页优先级、最近结果、能力状态、空状态和安全降级全部通过验收。
2. 单作品、Creator Clone、报告即时显示、刷新恢复、设置入口和本机安全合同完成回归。
3. 全局测试、JavaScript `--check`、差异检查、至少 500 条规模测试和可用的页面/HTTP 冒烟结果已如实记录。
4. 四项已知问题均有明确处置：在 Stage A 关闭，或作为有测试与用户提示的受控限制进入后续阶段。
5. Stage A Draft PR 已完成人工审查并合并，合并 commit 已记录。
6. 用户明确确认进入 Stage B；不得由自动流程自行推进。

Stage B 的首要工作是统一任务 DTO、精确 `resume_target`、失败恢复提示和 stale 状态表达，不得回头改变 Stage A 的只读安全边界。

## 测试记录

| 检查项 | 状态 | 结果或证据 |
| --- | --- | --- |
| 最新 `main` 基线 `pytest -q` | 通过 | `344 passed, 1 warning`，阶段开始前执行 |
| Stage A 完整 `pytest -q` | 通过 | `356 passed, 1 warning in 47.76s` |
| `node --check app/static/app.js` | 通过 | 使用 Codex bundled Node.js |
| `node --check app/static/workbench.js` | 通过 | 使用 Codex bundled Node.js |
| 新增 JavaScript 模块 `node --check` | 通过 | `app/static/workbench-tasks.js` |
| `git diff --check` | 通过 | 无空白或补丁格式错误 |
| Overview API 正常、空状态与来源失败 | 通过 | `tests/test_workbench_overview.py` 与 Node 任务优先级测试 |
| 文件缺失、stale、敏感字段与截断 | 通过 | 覆盖 Bearer/JWT、畸形样本、超限 Runtime 索引和 Strategy stale |
| 报告即时显示与刷新恢复 | 通过 | 既有 Creator Clone 回归测试进入完整测试套件 |
| 500 条规模测试 | 通过 | 500 Jobs + 500 Cases + 500 Creator 记录；有界结果与读取次数 |
| 实际 HTTP 冒烟 | 通过 | `/` 与 `/api/workbench/overview` 均返回 200；热请求约 0.04 秒，响应约 9 KiB |
| 浏览器、移动端与键盘检查 | 通过 | 1280 / 1024 / 390 视口无横向溢出；当前本机数据渲染成功，控制台错误 0 |

浏览器自动化若不可用，必须记录实际 HTTP 冒烟、Node 纯函数或 DOM 行为模拟的替代结果，并明确列出未覆盖项。

## PR 信息占位

| 字段 | 当前记录 |
| --- | --- |
| Stage A 状态 | Draft PR #12，等待人工审查 |
| Head 分支 | `codex/workbench-task-console-v1` |
| Base 分支与基线 commit | `main` / `a4f0dd1` |
| Draft PR 编号 | #12 |
| Draft PR 链接 | `https://github.com/Daiobs/short-video-agent/pull/12` |
| 人工审查结论 | 待记录 |
| 合并状态 | 未合并 |
| 合并 commit | 不适用，待合并后记录 |
| Stage B 授权 | 未获得；不得开始 |
