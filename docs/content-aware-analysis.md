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

每次正式请求依据实际发送的图片和文本建立证据说明。text_only 不声称看过图片；精简请求不声称收到完整素材包。静态帧不能证明连续运镜、节拍或精确动作时序。缺证据仅约束相关结论，不要求整份报告失败。

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

## 仍存在的限制

自动方向仍是关键词与现有材料的启发式初判，不是可靠的分类模型。模型建议不会自行触发重分析。引用白名单和数字计数不验证结论语义；静态帧不能证明连续动作、运镜或声音节奏。真实报告是否更具体，需要用户以已有素材主动验收。

本轮未改变原有模型重试问题、HTTP 网关、证据采集和账户授权策略；只验证当前调用机制不因分类新增调用。
