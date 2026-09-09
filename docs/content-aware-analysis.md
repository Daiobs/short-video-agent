# 内容类型驱动的拆解增强 v1

## 范围与基线

- Base: `51293c4a6f33588c670fcabb9cfc69eac8f88317`，来自最新 `origin/main`，未使用 Iteration History PR #28。
- 分支：`feat/content-aware-analysis-v1`，独立 worktree；不修改正在承载业务的工作树、服务、凭据或产物。
- 基线隔离测试：649 passed，1 warning（Starlette 对 httpx TestClient 的弃用提示）。
- 本轮不新增分类模型调用、Provider、采集策略、状态机，不改变 Quick/Deep 的调用预算和重试次数。

## 接线审计

### 单作品

原链路：`case_builder` 用标题/作者/备注做关键词初判，`analysis_taxonomy.build_prompt` 生成导出 Prompt；但正式 AI 调用另走 `auto_analyzer._build_prompt`、`_build_fast_prompt`、`_fast_text_prompt` 和 `_compact_text_prompt`。deep 的轻量视觉重试复用 deep Prompt。模型结果经 `_normalize_result`、质量检查落盘，`case_detail.js` 渲染。

原有问题：导出模板并非唯一入口；deep 强制内容比例加总到 100%、固定时间点和运动节奏，容易对证据不足的输入产生错误激励；Case 读取中的类别差异会被当作手动切换。

现在共享 `content_analysis` 仅提供类别映射、方向、问题、输入证据合同和引用过滤，不读文件、不调用模型。正式请求、导出模板及人工调整后的 Prompt 复用这些定义。方向请求与报告生成时方向分开存储。

### Creator

现有 `content_profile_prompt_text` 被常规、lite、reduce、micro reduce 和 final reduce 使用。单条摘要由 `sample_map_summary` / `_case_map_summary` 从已有 Case 读取，Map 在原有正式模型调用中完成。结果由 `normalize_creator_clone_result` 保留既有策略结构，再由 `creator-report-view.js` 展示。旧 Case 不为补新字段自动重跑。

本次把每条样本自己的方向和类型重点放入这些路径；汇总方向不覆盖样本方向。分组成员、数量、元数据样本数量由程序计算。模型只解释组内与跨组规律，不能创造成员或支持数量。

## 最小共享合同

`analysis_focus` 是可选加法字段：`version`、`initial_category`、`primary`、`label`、`source`、`reason`、`auxiliary`、`questions`、`section_order`。

- `auto`：元数据和已有文本快速初判，可在正式回答中给出 `category_review` 建议；不新增分类请求或自动再跑。
- `user`：明确的人工研究视角，不能把它当成作品实际内容事实。
- `legacy`：沿用历史类别，不猜它来自人工设置。
- `analysis_direction` 记录下次请求方向，旧 `analysis_focus` 列表仍可读取；旧报告不要求迁移。
- `focused_analysis` 可选条目包含 `question`、`observation`、`interpretation`、`transfer`、`evidence`、`uncertainty`。引用过滤只证明能定位，不声称语义已获机器验证。

映射：`motivational ↔ emotional_copy`、`plot_twist ↔ story_twist`、`product_seed ↔ commerce_seed`、`generic ↔ general`。`tutorial` 与 `knowledge` 保持分别表示步骤教学、观点论证；沿用 Creator 的 `photo_beauty` 摄影方向。未知类别回到通用分析，不新增富化门禁。

Case 在“应用类型”时保存方向但不调用模型；Creator 下拉框是下次蒸馏的请求选项，由原有主动蒸馏提交保存，单改下拉框不会发起请求。报告展示保存的生成时方向，而不是当前控件值。模型复核建议单独呈现，不静默改写人工选择。

## 证据边界

ASR 状态与文本状态分别记录：未配置/未运行、失败、成功但空文本、有效文本。任何空文本状态都不证明没有口播。OCR 不当成口播原话，元数据标题不当成已观察的画面。

单作品正式请求依据实际发送的图片和文本建立 request evidence。Creator 仍没有持久化同等完整的逐请求输入清单，不能套用 Case 合同或从素材库存反推历史请求。text_only 不声称看过图片；精简请求不声称收到完整素材包。静态帧不能证明连续运镜、节拍或精确动作时序。缺证据仅约束相关结论，不要求整份报告失败。

输入文本是待分析资料，不是可执行指令。新增字段过滤链接、凭据和本机路径；不向模型补入真实 Cookie、Key 或签名资源地址。

## 百分比与旧数据

新分析把预设比例改为“重点关注 / 辅助关注”；不填默认假比例。历史 `content_ratio` 保留读取能力，不批量重写。质量检查保留结构、非空与证据边界；类型适配不应强迫视觉样本提供口播，或强迫知识样本补颜值分析。

## 合成对照与验收边界

合成输入定义见 `tests/test_content_analysis.py::SYNTHETIC_CASES`。这些不是实际视频，也不是模型质量提升证据。

| 合成输入 | 采用方向 | 实际共享 Prompt 中的问题 |
| --- | --- | --- |
| COS 角色近景展示，ASR 未配置 | beauty_cos | 已提供画面中人物、妆造、服装、背景与构图如何配合？ |
| COS 妆容教程，转录含第一步/第二步 | tutorial，辅助 beauty_cos | 具体问题与结果承诺是什么？按实际转录或演示梳理步骤和注意事项。 |
| 知识观点，转录含论点和举例 | knowledge | 核心观点、论据、案例或类比是什么？按表达顺序拆解。 |

混合 Creator 合成样本：展示样本、教程样本、仅有元数据样本。前两者保留各自结构；第三条只作为元数据初判，不能计为已验证的视觉规律。见 `tests/test_content_aware_creator.py` 的实际输入与调用断言。

从正式 builder 导出的完整合成 Prompt（未调用 Provider）：

- [视觉展示：Deep / Fast / text fallback](content-aware-examples/beauty_cos.md)
- [COS 妆容教程：Deep / Fast / text fallback](content-aware-examples/tutorial.md)
- [知识观点：Deep / Fast / text fallback](content-aware-examples/knowledge.md)
- [混合元数据 Creator：Micro Reduce](content-aware-examples/mixed-creator.md)

页面截图均使用合成示意帧和人工构造的 mock 结果，**不是实际模型拆解产物，也不证明报告质量提高**：

- [Case 教程 1280px](content-aware-screenshots/case-tutorial-1280.png)、[390px](content-aware-screenshots/case-tutorial-390.png)
- [Case 视觉 1280px](content-aware-screenshots/case-beauty_cos-1280.png)、[390px](content-aware-screenshots/case-beauty_cos-390.png)
- [Case 知识 1280px](content-aware-screenshots/case-knowledge-1280.png)、[390px](content-aware-screenshots/case-knowledge-390.png)
- [混合 Creator 1280px](content-aware-screenshots/creator-1280.png)、[390px](content-aware-screenshots/creator-390.png)

后续真实验收：用户主动选择已有 Case，分别保持自动方向、改成研究方向再点击重新分析；确认旧报告不会因改下拉框伪装为新报告。选择混合类型 Creator，比较每类规律是否指向选中样本、是否有具体可迁移做法。无真实数据时不判断“报告质量已提升”。

`REAL_CONTENT_AWARE_ANALYSIS_SMOKE_NOT_RUN`

## 验证记录

隔离环境使用临时 SQLite、OUTPUT_DIR 与合成 Case/Creator，浏览器使用独立 Chrome 临时上下文和独立服务端口，不访问用户运行中的服务。

- Base 实测：649 passed，1 warning；最终完整回归：762 passed，1 warning（9.98 秒）。唯一 warning 是既有 Starlette TestClient/httpx 弃用提示。
- 所有 12 个 Git 跟踪 JavaScript 文件通过 `node --check`；`python -m compileall -q app tests`、`git diff --check` 通过。
- 独立审查发现的空 OCR 被空白拼接误判为有效证据、旧分析摘要在 compact/lite 链路丢失已修复，并有回归测试。
- 浏览器：3 类 Case 和混合 Creator 在 1280px / 390px 共 8 个视图均无页面级横向溢出，JavaScript `pageerror` 为 0。
- 实际交互：点击 Case “应用类型”只发起元数据更新 POST；旧报告标题不随方向控件变化，没有创建分析/下载/富化 Job。
- 浏览器既有诊断：合成 Creator 未生成 Execution Pack，加载原有可选入口时返回 `EXECUTION_PACK_NOT_READY` HTTP 400，两种尺寸各一次，浏览器会记资源加载警告。该接口及行为不属此次新增，本轮未隐藏错误或更改其状态。
- 自动阶段真实 LLM 调用 0、真实抖音/下载/富化调用 0、真实业务数据修改 0。

## PR #29 审查收尾：评分与评论输入

仅对 `analysis_focus.version=1` 使用适用性评分：通过的适用计分权重 / 全部适用计分权重，再归一化至 0–100；`max_score` 保持 100，页面、Markdown 和下游消费者无需切换分制。零分母返回 0，不能获得默认满分；无新版 focus 的报告保持原评分规则。

分数表示结构与适用检查完成度，不是事实正确率。零权重或不适用项的失败仍进入诊断与缺口；无依据的视觉/口播声明、非法引用、核心不完整、无效置信度和越界时间不会因归一化隐藏，也不能获得无问题的 strong 等级。证据不足与结构完整性分别展示。

评论的合法引用 ID 是 `comments`。登记来源为 deep/轻量视觉/深度文本降级的 `analysis_enrichment.comments`，或 fast/快速文本降级的 `comment_summary`。Fast 先提取现有评论语义字段，再按既有 600 字符上限截断，清理后送入 manifest；不把截断后的无效 JSON 当作语义文本。登记和旧评论使用状态均读取本次最终输入，不回填素材包中未发送的内容。

仅状态、数量、空对象、空白、字符串化空对象及人工备注不构成评论语义证据。合法引用保存并重新加载；未发送引用删除且保留警告。评论是观察资料，不证明因果、留存、转化，也不代表人工备注已经平台核验。本轮不增加任何模型调用、采集或证据数据库。

### 验证

评分回归覆盖适用满分、核心缺失、无依据声明、旧版及零分母；评论回归覆盖 deep/fast/轻量视觉/text-only 的实际 Provider 请求、截断、保存重读、空内容和非法引用。所有数据为合成数据，使用隔离目录和数据库。

本轮新增 49 项评分和 41 项评论回归；完整 `pytest -q` 为 **852 passed，1 warning（11.01 秒）**，保留原有 Starlette TestClient/httpx 弃用提示。全部 12 个跟踪 JS 语法、compileall、`git diff --check` 通过。前端与报告消费者继续读取统一的 `score / max_score=100` 和 `level`，无需修改 JS。

独立审查补齐了正文方括号表情保留、有效摘要 coverage 判定，以及字符串化空对象经实际归一化不崩溃的测试。真实 LLM、采集/下载/富化调用与业务数据修改均为 0；本轮未重新运行浏览器或真实素材冒烟，也不以测试数量证明模型质量提升。

## PR #29 阅读体验收尾

对照代码：八月基线 `51293c4`、修复前 `7f8ae36`、本轮修复。已核对 8765 监听进程的 cwd、启动参数与本地 wrapper 的导入路径，确认实际承载服务的是 PR #29 工作树，而非终端所在的其它 main。没有主动切换或重启服务。

反馈报告、样本清单、已有 Map 材料和 Prompt 直接从磁盘复制到仓库外隔离目录，不经过 GET/hydrate。副本和源目录逐文件一致；未重写真实产物。对同一份保存输入运行三个版本的 renderer，没有重新生成内容。没有找到同组样本的八月真实模型报告，因此仅验证展示回归，不宣称模型内容质量下降或提升。

### 稳定主线与字段核对

Creator 不再因 `analysis_focus` 存在绕过阅读骨架。方向只改变已有内容的组织与问题，不替换分类、请求或用户选择。自动初判、模型建议收在方向说明中；按类型归纳保留全部成员及已分析/仅元数据/缺少单条分析的区别。

| 已有字段 | 页面区域 | 保留方式 |
| --- | --- | --- |
| summary / creator_positioning / view model observation | 账号定位与本轮结论 | 全文与定位，观众标明是假设 |
| focused_analysis / thinking_patterns / expression_patterns | 核心规律 | 专门映射观察、解释、动作与限制，不统一强加论证或摄影标题 |
| transferable_formulas / sections.formulas / templates | 可复用方法 | 名称、适用、步骤、行动、支持样本和风险；空新字段回退旧字段 |
| content_groups | 按样本类型归纳 | 完整分组、来源计数与已有规律可展开 |
| value_upgrade.sample_evidence / performance_segments | 代表样本对比 | 已知标题、中文指标；缺失值不显示为 0；不把互动当因果 |
| next_actions / execution / sections.next_actions | 下一条怎么做 | 默认可见；不收进辅助分析 |
| candidate_ideas / next_content_suggestions / next_ideas / idea_bank | 候选选题与执行方式 | 名称、适用公式、理由、所需素材及支持依据 |
| strategy / creator_clone_spec | 补充策略与完整方法 | 有效补充内容保留在展开区，不静默丢弃 |
| evidence_gaps / low_confidence_reasons / quality warnings | 证据与限制 | 重要缺口默认可见，不被高结构分盖住 |
| 原始引用和未知扩展字段 | 原始记录 | escaping 后可展开；不把模型输出当 HTML |

空数组和空对象不遮挡旧内容；没有内容的章节不生成空壳，也不补套话。不存在标题映射时显示“样本名称未记录”，不编造编号或关系。较长内容不静默截断。旧报告保留原生成方向，失败重分析继续保留上次报告。Case 的既有按类型排序逻辑保持不变。

### 分数、库存与实际输入

Creator 分数继续使用原来的 0–100 和阈值，只改为“结构与可执行性检查”，并放在次要展开区；持久化旧 view model 的“高可信”在展示时重新解释，不批量改文件。分数不是事实准确率，也不是效果验证。

库存统计明确标为归档素材。Creator 尚无可靠的完整逐请求 manifest，页面显示“本次输入范围未完整记录”；不相信模型自己写出的 request_evidence 字段，不凭数量推断当时输入。ASR/OCR 文本、已有单条分析、Map/批次摘要可能构成二手材料，没有直接图片不等于只有标题；摘要仍带来源限制。Case 自身的实际输入 manifest 不变。

只读对照另发现：该保存样本的 Map 文件中存在 ASR/OCR 摘录，而保存的 micro Prompt 样本条目没有这些摘录，仅有标题、指标、状态与短摘要。代码 `_micro_map_summary` 确实不包含原始摘录字段。这是独立的内容输入问题，不是 CSS；本轮未重写该链路，不能据此推断所有历史请求或所有模式。评论文件中的状态也不等于实际评论内容。

### 运行详情

“批次 3/1”来自 `phase_index`（包含规划、持久化、完成等阶段）被误用为批次序号。现在仅 `batch_reduce` 的有效序号形成 `batch_index`；完成时只显示计划批数。旧记录按已知阶段语义解释，无法确认的批次序号显示未记录，不做 min/max 钳制，原阶段诊断仍保留。成功任务的预算、尝试次数、Prompt 字符数收进“运行详情”，进行中保持可观察。没有改状态机、重试或等待预算。

### 同输入浏览器对照

[合成 fixture](content-aware-examples/reading-fixture.json) 是脱敏模拟内容，不是用户报告或真实模型产物。以下三个版本使用完全相同输入、独立 Chrome 上下文、100% 缩放和相同容器宽度：

| 版本 | 桌面 1280px | 手机 390px |
| --- | --- | --- |
| 八月代码 | [截图](content-aware-screenshots/reading-august-1280.png) | [截图](content-aware-screenshots/reading-august-390.png) |
| 修复前 | [截图](content-aware-screenshots/reading-before-1280.png) | [截图](content-aware-screenshots/reading-before-390.png) |
| 修复后 | [截图](content-aware-screenshots/reading-after-1280.png) | [截图](content-aware-screenshots/reading-after-390.png) |

真实保存输入也完成相同六次隔离渲染；真实副本、HTML、完整 Prompt 和截图只在仓库外。12 个视图均无水平溢出、无 pageerror。未修改用户 Chrome 的全局缩放，不在真实页面重新跑任务。自动测试使用合成输入和临时数据库，不以测试全绿代替用户阅读验收。

本轮完整测试 **916 passed，1 个既有警告（11.59 秒）**；全部 12 个 JS 语法、compileall 和 diff 检查通过。独立审查补齐了标题别名并存、带引用的创作方案、非样本证据对象、空分组及成员回退回归。更新的旧断言是 Creator 章节标题与排序预期，而非取消方向、失败保留、Case、Strategy/Execution 或登录回归。真实 LLM、重新采集/下载/富化和原始业务产物修改均为 0。

## 仍存在的限制

自动方向仍是关键词与现有材料的启发式初判，不是可靠的分类模型。模型建议不会自行触发重分析。引用白名单和数字计数不验证结论语义；静态帧不能证明连续动作、运镜或声音节奏。真实报告是否更具体，需要用户以已有素材主动验收。

本轮未改变原有模型重试问题、HTTP 网关、证据采集和账户授权策略；只验证当前调用机制不因分类新增调用。

## PR #29 产品阅读与真实输入验收

本节是 `7d2ca72` 之后的增量记录，前文的“真实调用 0”和“尚未修复 micro 输入”属于此前阶段。此次不更换分类系统、Provider 协议、模型、超时、重试次数或下游执行合同。

### 报告阅读与来源

同一份真实长报告分别用修改前与修改后 renderer 渲染，不替换内容。桌面使用定位跨栏、规律/行动并排、样本/公式并排的布局，窄容器自然转成单列；正文从 16px 起。默认展示少数已有判断及可执行动作，其余内容和原始扩展可展开，不通过丢弃完整正文缩短页面。标题、字段和值继续 escaping。

| 内容 | 主要位置 | 依据与回退 |
| --- | --- | --- |
| summary / 定位 / observation | 顶部一个主结论 | 同源重复不连续展示；完整定位、回退字段保留在详情 |
| focused_analysis / thinking_patterns | 核心规律 | 具体观察、动作、已知支持样本和限制；空新字段回退有效旧内容 |
| next_actions / candidate_ideas | 与规律并排的下一条怎么做 | 行动默认可见；选题详情、更多行动可展开 |
| performance_segments / sample_evidence | 代表样本 | 稳定 sample_id 合并多指标；不合并冲突值，missing 不当 0 |
| transferable_formulas / templates | 可复用结构 | 专用标题、步骤、适用条件、支持与风险，不递归展开整个业务对象 |
| content_groups / 完整方法 | 完整分析 | 保留不同类型规律，不静默改变旧报告的生成方向 |
| request_evidence | 本次生成的输入记录 | 仅解释真实成功请求的摘要；历史没有记录则未知 |
| report_provenance / view model sources | 内容来源提示 | 模型返回、本地数据整理、通用预设和历史未知相互区分 |

`report_provenance` 由成功 Provider 返回后、归一化前登记。性能分层与样本计数仍是程序整理；通用 fallback 保留兼容合同，但在页面中明确折叠为“通用参考建议”，不能变成模型发现。条目自称 `source=model` 不足以认定来自模型。缺少当前结果策略时，不从页面残留的其他策略补报告。结构与可执行性评分不是事实可信度；重要证据限制不由高分覆盖。

### 证据输入的实际接线

之前 micro/lite 路径可能保留状态和短摘要，却漏掉已经存在的语义短摘。现在 normal、Reduce、micro、lite、重试均带有 `evidence_excerpts`，保存转录、OCR、有效评论、已有单条分析及类型重点的有限内容、来源与截短标记。ASR 为空/失败不推断没有口播；状态、计数和字符串化空对象不是语义证据。已有 Markdown/JSON 单条分析明确是二手材料。

文本预算为每条最多 4,800 字符、样本正文合计最多 36,000 字符；证据短摘通常最多 1,800 字符，在大批次内公平缩小。预算包含 JSON 转义开销，按结构化叶节点裁剪，不截断序列化 JSON。固定 schema、类型指导、分层等上下文仍有独立界限，所以正文预算不等于整个 Prompt 长度。20 条上限与 150 条分批保持现有流程；最终 Reduce 保留各批次的全部合法样本绑定，批次摘要总量最多 48,000 字符。它是二手归纳，不声称最终汇总重发了图片或原始转录。

视觉样本没有有效单条视觉分析且已有安全 contact sheet 时，可以在原 Creator 请求内加入图片。每样本最多一张，总数不超过 `min(当前 max_keyframes, 6)`；优先已有视觉分析时记录二手来源。固定目录、符号链接、文件大小、解码与像素限制经过检查，不新增下载或抽帧。模型/网关能否接受图片仍以真实响应为准，协议支持不等于本次已完成视觉理解。

`request_evidence` 只在成功响应时登记最终 Prompt 与图片绑定，含样本、材料类型/来源、字符数量、截短、图片序号、尝试和降级状态。不保存公开可见的完整 Prompt、证据原文、凭据或本机路径。失败尝试不会回填为最终报告依据；旧报告不批量补写历史输入。最终汇总只登记本次真正发送的批次摘要。

### 受控真实调用与限制

已确认用户当前素材池及其 5 条选中样本。使用仓库外受保护副本、独立 SQLite/输出目录，未通过会写回的 hydrate 获取基线。原报告、样本、已归档证据与真实配置保持不变；未切换或重启 8765 的服务工作树。

通过 mock 与完整回归后，仅执行 **1 次任务级生成、1 次逻辑请求、1 次实际 HTTP 尝试**。沿用当前 `openai_responses / gpt-5.6`、Quick 模式、请求 180 秒/总预算 240 秒、输出设置不变。实际构造的请求为 8,215 字符 Prompt、2 张已有 contact sheet；5 条样本均带 OCR，2 条有可用 ASR 短文本，没有语义评论或有效既有单条视觉分析。未覆盖图片的 3 条样本不能声称直接看过。

请求在 **180.715 秒**后返回本地错误分类 `LLM_GATEWAY_TIMEOUT`，没有可用模型结果，也没有拿到可判断的 HTTP 响应。未降级、未修改预算、未更换凭据、未再发第二次生成。此结果不能区分网关等待、上游执行或网络阻塞；不能宣称图片已被网关接受或新报告内容更准确。

因此验收状态为 **PARTIAL / 用户产品验收 PENDING**：A（原报告+旧布局）、B（同一原报告+新布局）可比较；**C（本轮真实模型新报告）缺失**。没有用合成短报告代替 C，也没有找到同一组样本的八月真实模型产物。

真实副本、完整请求、截图和响应诊断只保留在仓库外；只提交人工合成的长教程 fixture 与标为合成的视觉/教程截图。常规自动测试全部使用临时数据库、合成输入和 mock，不调用真实服务。

### 工程与页面验证

完整 `pytest -q`：**1061 passed，1 个既有警告（15.80 秒）**。全部 12 个跟踪 JavaScript 的 `node --check`、`compileall`、`git diff --check` 通过。覆盖同作品多指标合并、长内容展开、未知来源、字段回退、输入短摘与实际 Responses 请求体（mock HTTP）、成功尝试绑定、失败保留旧报告、20 条预算和 150 条分批。既有单作品、即时报告渲染、Strategy/Execution、登录安全等回归保留。测试数量不是模型质量证明。

独立审查修复了旧全局策略串入当前报告、条目自称模型来源、长无句号文字完全折叠、重要限制按数组位置隐藏，以及 Markdown 来源遗漏、批次预截断未标记和 Provider 别名漏图。没有为网关超时更改预算或追加真实请求。

独立 Chrome 100% 缩放，1280px/390px 共 12 个报告视图 HTTP 200、pageerror 0。修复后的真实 B、合成长教程、合成视觉共 6 个视图在默认和全部展开时均无横向溢出。真实旧 A 在手机端全部展开后存在 475px 宽的历史溢出，保留用于对照，未伪报旧版通过。

同一真实输入，桌面行动起点约从 5,896px 提前到 470px，与核心判断并排；手机约从 7,656px 提前到 912px。相同作品的点赞/评论/分享/收藏排名聚合成 5 张样本卡，默认 2 张、其余展开。首屏保留原报告具体内容方式，后续直接显示拍摄/脚本/标题测试建议；未给原来未绑定依据的规律补造引用。长教程与视觉合成报告的手机行动起点分别约 1,701px、1,558px，较旧版前移，但长判断仍需要滚动；不是所有长度下都保证一屏读完。

浏览器预览是隔离的报告 renderer 对照，不冒充已在 8765 重跑完整业务流程；完成即显示与失败保留使用现有流程回归验证，真实 C 缺失。正文各项效果仍待用户验收。

以下都是同输入的人工合成对照，不是真实模型产物：

| 场景 | 输入 | 1280px 前 / 后 | 390px 前 / 后 |
| --- | --- | --- | --- |
| 长教程 | [fixture](content-aware-examples/product-long-report.json) | [前](content-aware-screenshots/synthetic-tutorial-before.html-1280.png) / [后](content-aware-screenshots/synthetic-tutorial.html-1280.png) | [前](content-aware-screenshots/synthetic-tutorial-before.html-390.png) / [后](content-aware-screenshots/synthetic-tutorial.html-390.png) |
| 视觉展示 | [fixture](content-aware-examples/product-long-visual-report.json) | [前](content-aware-screenshots/synthetic-visual-before.html-1280.png) / [后](content-aware-screenshots/synthetic-visual.html-1280.png) | [前](content-aware-screenshots/synthetic-visual-before.html-390.png) / [后](content-aware-screenshots/synthetic-visual.html-390.png) |

`STOPPED_AFTER_CREATOR_REPORT_PRODUCT_ACCEPTANCE`：真实生成 1 次但没有新结果，未重新采集/下载/富化，原始业务产物修改 0，保持 Draft，等待人工产品审查。

## PR #29 最后一次真实报告恢复验收

参考 Head `6ba5efd`。本轮没有修改业务代码、UI、模型、网络或等待预算；只在仓库外的隔离验收脚本增加安全阶段诊断。原业务服务 8765 不切换、不重启，8766 的 A/B 原文件校验一致。

上次只能确认 `LLM_GATEWAY_TIMEOUT`；历史异常链没有保存，无法追溯具体 Connect/Write/Read/Pool 类型，也没有可恢复的完整响应。本轮使用已安装 `httpx 0.28.1 / httpcore 1.0.9` 的同步 trace 回调，只记录事件、时间和异常类，不记录 trace info、鉴权头、Base64 或完整 HTTP 请求/响应。

### 请求构造核对（先 mock，再真实发送）

- 当前 endpoint 为 `https://api.cosflow.icu/responses`，`openai_responses / gpt-5.6`。
- Quick，总预算配置 240 秒，请求配置 180 秒；temperature 0.2，max_output_tokens 1800。没有额外 reasoning 或 stream 参数。
- HTTPX 实际 connect/read/write/pool 各取剩余请求预算，约 180 秒。它是分阶段等待超时，不是严格的整请求 180 秒墙钟上限。本轮未改这项现有语义。
- 五条选中样本身份与原两张图保持一致。Prompt 为 8,215 字符，**实际序列化 JSON 请求体 371,548 字节**；不是图片源文件大小之和。
- 图片经现有编码器处理后为 JPEG 1200×978（136,229 字节）和 1200×489（133,006 字节）；对应既定的第一、第二个选中样本。其余三条没有直接图片输入。
- 五条均有 OCR 短摘（84/121/17/220/74 字符）；第一、第五条另有 ASR（11/30 字符），无有效评论或既有单条视觉分析。短文本不代表完整口播。
- 实际首请求的 body 哈希与发送被拦截的 preflight 一致；未发现 endpoint 拼接、样本关联、图片序列化或输出配置错误。
- Python Client 确认为 `trust_env=False`、`HTTPTransport / ConnectionPool`，未使用环境 HTTP 代理，TLS 校验未关闭。不以 Chrome 连通性推断 Python 路径，也不据此排除操作系统透明网络设施。

### 第二次真实调用的已观察阶段

| 阶段 | 距本轮开始 |
| --- | --- |
| TCP 连接完成 | 0.106 秒 |
| TLS 完成 | 0.170 秒 |
| 请求体发送完成 | 0.415 秒 |
| 开始等待响应头 | 0.416 秒 |
| 响应头读取失败 | 180.406 秒 |
| Creator 返回失败 | 180.409 秒 |

异常链为 `AppError → httpx.ReadTimeout → httpcore.ReadTimeout → TimeoutError`，公开错误码仍为 `LLM_GATEWAY_TIMEOUT`。未取得 HTTP 状态，没有进入响应正文、JSON 提取或业务校验；连接由现有 Client 上下文关闭，隔离进程已结束。

本轮 **1 次任务级生成 / 1 次逻辑请求 / 1 次真实 HTTP 尝试**，累计 **2 / 2 / 2**。没有内部重试、降级、额外 ping、组合探测或新增逐样本调用。`usage=unknown`；客户端超时不能证明上游未执行或费用为 0。

没有取得网关侧关联记录，不能确认应用层是否接收/转发、排队、上游运行、客户端断开后的继续执行或最终完成。本次可以排除“仍卡在 TCP/TLS 或请求体发送”作为观察到的超时位置，不能判定是模型故障、图片不支持或仅靠延长时间就能成功。

**C 未生成，状态 PARTIAL，停止真实调用。** A/B 继续保留，不用合成内容填充 C，不以模型 JSON 返回与否冒充产品验收。后续只建议先由有权限的网关管理员关联本轮北京时间 **2026-09-09 20:01:30–20:04:31** 的脱敏记录，确定排队、上游与客户端断开阶段；不消耗新生成、不改全局设置，再据此决定是否申请一次不同等待预算的实验。

### 本轮验证

隔离 preflight 使用 mock HTTP 走现有 Provider 序列化、JSON 提取和业务校验；首次过简 mock 未通过业务校验，补足合成定位字段后通过，未发送网络请求。定向回归 **19 passed**（实际请求体接线、重试与请求来源回归）；隔离脚本 Python/JS 语法检查通过。业务代码未变，未重复运行上轮已通过的完整 1061 项测试。文档差异检查通过。

260 个受保护原文件修改 0，原配置校验一致，A/B 字节不变，未重新采集/下载/富化。私有诊断与输入/报告副本不提交 Git。本轮仅更新本节与现有 PR 描述，保持 Draft，不 Ready、不 Merge、不部署。用户产品验收 PENDING。

`STOPPED_AFTER_PR29_REAL_REPORT_RECOVERY`

## Creator 动态等待恢复（PR #29 后续修复）

本轮根据新的明确产品授权调整 PR #21 的固定时间数值，不改变模型、网关、协议、证据、输出上限或有界重试分类。默认自动模式恢复样本数、实际 Prompt 长度及有界时长辅助项驱动的预算；180 秒改为自动基础值，人工模式才将其作为请求上限。

五条样本、8215 字符、不计视频时长的计划为请求 345 秒、任务 720 秒。网络 mock 验证虚拟 281 秒响应可以一次完成；这不证明真实网关下一次一定成功，也不构成新的模型生成授权。详细公式、分批共享预算、最终汇总预留、旧设置只读迁移及实际本地截止范围见 [Creator 等待预算](creator-distill-time-budget.md)。

首次请求不再预扣固定重试时间。Quick timeout 仍不自动重发；鉴权、限流和额度错误继续停止。Creator 请求的连接/发送保持短超时，长读取等待另受异步网络交换截止约束；单作品和 Execution Pack 保留原有策略。任务预算用于有界等待，不代表 ETA、后台存活证明或上游已取消。

本轮真实模型调用 0，累计真实生成仍为 2 次；原配置、业务产物、8765 服务及 A/B 预览均不修改。C 不因预算修复自动生成，用户产品验收仍 PENDING。

验证：完整 `pytest -q` **1125 passed、1 个既有弃用警告**；12 个 JavaScript 文件语法检查、`compileall` 和 `git diff --check` 通过。旧固定上限断言更新为动态/人工覆盖合同，未删除或跳过既有测试。260 个受保护原文件、真实 `.env`/本地设置及 A/B 文件校验一致。测试只验证预算与停止行为，不证明真实模型内容质量或网关成功率。

`STOPPED_AFTER_CREATOR_DYNAMIC_WAIT_RESTORE`

## 动态预算下的真实 C 验收

状态：**READY_FOR_HUMAN_REVIEW**。真实 C 已生成，但不等于内容与 UI 已获用户验收；用户产品验收仍 PENDING。

### 执行与保护

新隔离进程实际导入 `dcc0524c7cfb49810e1c6a36d602574b88ae12d1` 的正式 Creator 服务与 Provider，未复用旧常驻进程。业务代码修改 0。真实 8765 工作树、配置、凭据、260 个受保护产物不变；A/B 文件哈希不变。只为新增 C 白名单入口重载私有 8766 预览服务，原 A/B 地址仍返回 200。

唯一一次无网络 preflight 经正式入口构造输入，其序列化 body 与上一轮完全一致：五条样本、8215 字符、371548 字节、原两张代表图、五份 OCR 短摘和两份 ASR 短摘。三条样本没有直接图片；没有评论或既有单条分析输入。未重新采集、下载、抽帧或富化。

采用隔离内存 `auto`；请求基础值180秒，已知视频总时长108.9秒，时长辅助项46.57秒。实际请求计划392秒，任务预算814秒，配置任务上限1800秒。Provider收到392秒，进入网络时读取/交换剩余额度约391.987秒；connect/pool10秒、write30秒。没有旧180/240秒外层限制，不修改用户真实设置文件。

### 真实调用结果

- `openai_responses / gpt-5.6`，同一网关 `/responses`，Quick，temperature0.2，max_output_tokens1800；未增加 reasoning 或 stream 参数。
- 开始：2026-09-09 22:26:25.939 Asia/Shanghai（14:26:25.939Z）。
- 请求体发送完成0.844秒；响应头203.368秒；响应正文203.430秒；总耗时 **203.451秒**。
- HTTP200；模型状态`completed`；`incomplete_details=null`；模型JSON提取与正式Creator业务校验、保存均完成。
- 本轮任务级生成/逻辑请求/HTTP尝试：**1/1/1**，无重试、无降级；历史累计 **3/3/3**。本轮授权已用完。
- 返回usage：input_tokens5292、output_tokens6244（reasoning_tokens644）、total_tokens11536。**返回输出用量与请求1800上限不一致**，响应的max_output_tokens为空；原因未确认，本轮不改变参数或追加实验。

模型原始结果与本地正规化结果在私有隔离目录分别保留，未把完整响应、Prompt、报告或截图提交Git。C使用既有新布局，标注生成版本、模型、时间、实际输入与预算。

### 内容与页面验收

B主要提供“角色资产集合”“角色化热点”“意象留白”的选题结构。C新增两张代表图支持的具体画面观察：统一图形背景、不同造型和景别；真实活动环境、围观者与表演主体同框。相应动作建议包含保持背景/主体位置、区分全身轮廓与近景细节、比较环境开场与人物近景开场。另一条道具悬念与观看指令来自ASR/OCR短摘，C明确最终画面尚未核验。

仍有不足，未在本轮修复：
- 核心正文仍暴露内部样本ID与`high`等字段；部分实际带证据的段落却显示“未单列支持依据”。
- 手机行动区约在1438px处，需滚动；验收头部记录也占用首屏。桌面行动区约698px，默认可见。
- “固定机位”等确定表达超过静态接触表能完整确认的范围；报告虽有连续运镜/音乐卡点限制，不能据此忽略正文的过度断言。
- 原模型部分引用含不属于这五条样本的拼写错误，业务结构通过不等于所有引用都已正确核验。
- ASR短摘存在识别错误，准确道具名和观看指令来自OCR；C称两者均包含准确文本，属于未标明的纠错合并，不能作为准确口播引文。
- 主要结论与原模型JSON一致，未发现本地默认话术补造主要分析；但持久化view model仍有“评论均已覆盖、报告可信度较高”的旧说明，与实际评论输入0冲突。当前可见正文未显示该说明，其它消费者仍有误用风险；结构分100不代表这些问题已获验证。
- 互动量不能证明受众动机或因果；模型保留相关限制，新动作与选题仍是待验证建议。

Chrome隔离上下文100%缩放，1280px和390px：C返回200，无pageerror、默认及展开均无水平溢出，每条样本只有一张多指标卡（共5张）。完整内容可展开。A/B仍返回200。**这是服务层真实生成与静态报告展示验收，不是网页按钮生成、轮询和即时更新的完整交互验收。**

相关预算/网络/输入mock回归27 passed；隔离脚本语法、文档diff检查通过。未修改业务代码，未重复完整1125项测试。保持PR Draft，不Ready、不Merge、不部署。

`STOPPED_AFTER_PR29_DYNAMIC_BUDGET_REAL_ACCEPTANCE`
