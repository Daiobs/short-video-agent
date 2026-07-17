# 功能比较

## 比较基线与限制

`short-video-agent` 的结论来自当前 `main` 的 README、工作台文档、路由和测试；基线 Head 为 `8e32166a8f377435380122204c33334034ec44eb`。[E-002][E-012]

本机没有找到独立的 `xingkong-workbench-secure` 仓库，因此该列严格使用用户给出的北极星：本地优先、人工确认、安全、可验证、可回滚、面向内容运营工作流；同时用当前仓库已经落地的只读 Overview、任务恢复、资产库和本机安全合同作可验证代理。不能把代理实现写成另一个仓库的确定事实。

## 功能矩阵

| 维度 | EchoLens | short-video-agent | xingkong-workbench-secure | 建议 |
| --- | --- | --- | --- | --- |
| 输入方式 | 抖音分享文本/链接；剪贴板自动填入 | 单作品链接、主页、作品列表、本地视频、JSON/CSV、已有 Case | 应以本地文件和显式授权 handoff 为主 | `ADOPT-NOW` 聚焦输入；`DO-NOT-ADOPT` 自动读剪贴板 |
| 数据获取 | 公共作品解析；完整 Cookie 后同步收藏/关注 | 多 Provider、公开解析、用户配置 Cookie、本机 Chrome DOM、手动回退 | 最小权限、本机连接器、显式确认 | `DO-NOT-ADOPT` 远端完整 Cookie |
| 内容解析 | 类型、作者、链接、封面、视频、音频、标题、ASR | 元数据、视频、关键帧、contact sheet、ASR、OCR、评论、指标 | 应保存可验证输入与处理记录 | `ADOPT-NOW` 结果动作；保持本地证据深度 |
| 证据保存 | 可预览/下载媒体；未见结构化证据索引 | 固定 Case 目录和结构化素材包 | 强调可验证、可回滚 | EchoLens 不足，不应降级 |
| AI 分析 | `E1`、思考和获取结果；成功样本未见 | 单作品拆解、Creator 蒸馏、Strategy Generator、缺证据降级 | 人工确认优先，不以全自动为目标 | `NEEDS-VALIDATION`；不把按钮等同于能力 |
| 任务编排 | 笼统处理中；队列未知 | BackgroundTasks + SQLite Job、状态聚合、轮询 | 任务可观察且不自动推进 | `ADOPT-NOW` 只借鉴简洁 UI，保留现有任务合同 |
| 历史记录 | 侧栏最近记录和搜索，当前为空 | Overview 最近结果、任务、Case、Creator Report、Strategy Plan | 应有操作与结果历史 | `ADOPT-LATER` 统一轻量历史入口 |
| 结果复用 | 媒体下载、字段复制；报告复用未见 | Case、Prompt、报告、Strategy、资产库和精确恢复 | 应支持可回滚复用 | `ADOPT-NOW` 就地动作；不削弱真源 |
| 用户反馈 | 未见 | 人工质量验收、校准样本和报告 | 人工确认是核心 | EchoLens 无直接参考 |
| 人工确认 | 法律复选框；模型按钮需点击 | 解析、富化、蒸馏、恢复均显式操作 | 核心原则 | `ADOPT-NOW` 保持显式确认 |
| 可追溯性 | 未见模型版本、时间、证据映射或任务 ID | Job DTO、Case 产物、报告质量、恢复目标 | 核心要求 | `DO-NOT-ADOPT` EchoLens 的不透明结果 |
| 本地优先 | 否，登录 SaaS | 是，本机 FastAPI/SQLite/文件产物 | 核心原则 | 不改变现有方向 |
| 隐私保护 | 法律声明称凭证加密；需要远端完整 Cookie | loopback、敏感值不回显/不入库或日志、专用本机 profile | 最小权限与本机处理 | EchoLens 风险显著更高 |
| 错误恢复 | 可见 ASR 错误，但恢复范围不清 | stale/failed/recoverable、精确恢复、部分结果保留 | 要求安全、可回滚 | `ADOPT-NOW` 简洁文案；保留现有恢复机制 |
| 成本控制 | 未见额度；模型调用成本未知 | 样本上限、Prompt fallback、用户配置 LLM、手动触发 | 应在提交前可见成本 | `DO-NOT-ADOPT` 不透明调用 |
| 页面体验 | 暗色、聚焦、结果动作紧凑；状态有冲突 | 功能更全，工作台/Case/Library 信息密度更高 | 应明确下一步和确认点 | 借鉴聚焦与空状态 |
| 第一版完成度 | 媒体工具较完整；AI 分析证据不足 | 已有单作品、Creator、任务恢复、资产库与校准 | 以安全闭环为完成标准 | EchoLens 只适合作为窄 UX benchmark |

## 重合度计算

采用上表 17 个产品维度（不含“建议”列）进行保守评分：

- 明确同类能力：1 分。
- 目标相近但实现边界不同：0.5 分。
- 无证据或方向相反：0 分。

由于 EchoLens 的成功 AI 结果、历史详情和后端任务机制未观察，分数用区间表达：

| 比较对象 | 重合度 | 解释 |
| --- | --- | --- |
| `short-video-agent` | **46%（±8%）** | 共同覆盖抖音链接、媒体获取、ASR、历史入口和人工触发；EchoLens 缺关键帧/OCR/评论/证据化拆解/Creator 策略 |
| `xingkong-workbench-secure` | **24%（±8%）** | 共同点是人工动作、状态和历史；远端 SaaS、完整 Cookie 托管、不可验证服务端处理与本地优先相反 |

因此 EchoLens **更接近 `short-video-agent`**，但只接近它的“单作品输入和媒体/转录层”，不接近其北极星中的“爆款证据、规律和可复用创作规则”。

## 直接参考落点

### short-video-agent

- 单作品输入区：收敛主动作和状态层级。
- Case 结果页：为现有视频、contact sheet、ASR、OCR、Prompt 和报告添加一致的预览/复制/下载动作条。
- 任务状态：将复杂 Job 状态翻译成更短的用户文案，同时保留稳定错误码和恢复目标。

### xingkong-workbench-secure

- 只参考通用的空状态、缺少能力提示和“前往设置”导航模式。
- 把收藏/关注类数据源设计成可插拔本机连接器或净化 handoff，而不是把完整 Cookie 交给远端服务。
- 任何刷新、同步、分析或生成都必须在动作前显示范围、成本和外部影响。

## 共同基础设施

1. 统一任务状态：`pending/running/partial/success/failed/stale`。
2. 可搜索历史和只读资产索引。
3. 媒体与文本产物的安全打开、复制和下载。
4. Provider 能力状态和人类可读错误。
5. 敏感数据源的配置状态，只显示“已配置/未配置”，不回显内容。
6. 输入、证据、推断、建议的版本化关系。

## 不应引入现有项目

- 远端保存完整抖音 Cookie。
- 默认读取剪贴板。
- 将 ASR 或 AI 原始错误作为唯一恢复指引。
- 只显示模型品牌别名而不记录 provider/version/cost。
- 用单页 UI 状态替代 Case、Job、Evidence 和 Report 真源。
- 自动发布、养号、账号矩阵或不可逆平台操作；EchoLens 本身也没有证明这些能力。
