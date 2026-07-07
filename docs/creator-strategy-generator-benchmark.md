# Creator Strategy Generator Benchmark

P5.5 目标是做真实样本基准验收，不新增功能、不扩展平台、不重构 Runtime。本文件记录当前系统从创作者素材池到 Creator Strategy Generator 的可用性边界：报告是否能支撑下一批创作方案，方案是否可拍，以及低证据场景是否会被正确降级。

## 验收范围

本轮只验证已存在链路：

```text
素材池 -> 样本选择 -> 证据富化 -> 创作者蒸馏报告
-> report_quality / diagnostics / creator_report_view_model
-> Creator Strategy Generator -> creator_strategy_plan.json
```

本轮不验证：

- 新平台接入。
- 新采集能力。
- 新 Runtime 状态机。
- 新 LLM prompt 或模型选择。
- 自动成片、字幕、TTS 或发布。

## 基准样本类型

### 1. COS / 美拍 / 摄影出片账号

目标：验证系统是否能把首帧、妆造、动作、镜头、标题话题和封面建议转成具体可拍方案。

重点验收字段：

- `shot_templates`
- `title_cover_suggestions`
- `pre_publish_checklist`

通过标准：

- 首帧建议必须具体到人物脸、眼神、姿态、道具或妆造亮点。
- 镜头建议必须包含距离、角度、光线或场景要求。
- 标题/封面建议必须能直接用于下一条内容 A/B 测试。
- 不能只输出“提升颜值”“增强氛围”这类空话。

### 2. 知识 / 教学账号

目标：验证系统是否能把问题切入、步骤化表达、收藏理由和发布前自检转成脚本结构。

重点验收字段：

- `script_templates`
- `pre_publish_checklist`
- `next_topics`

通过标准：

- 脚本模板必须包含开头问题、步骤推进、证明或案例、收藏/评论理由。
- 下一批选题必须说明观众为什么会收藏或复看。
- 发布前自检必须能检查“是否讲清楚”“是否有步骤”“是否有结果承诺”。

备注：本轮本地真实样本中，最接近该类型的是“摄影美拍 / 出片教程”账号。它不是纯知识课，而是“出片结果展示 + 轻教学包装”，因此用于验证教学型近邻场景。纯知识账号仍需在下一轮补充专门样本。

### 3. 低证据 / 仅元数据账号

目标：验证系统是否正确标记低置信，而不是在缺少视频、关键帧、ASR、OCR、评论时假装高置信。

重点验收字段：

- `low_confidence_notes`
- `evidence_gaps`
- `report_quality`
- `diagnostics`

通过标准：

- `report_quality_score` 应显著偏低。
- `low_confidence_notes` 必须指出缺少哪些证据。
- `next_topics` 和模板可以生成兜底方向，但必须带 `requires_review=true`。
- 不能给出高置信的镜头、口播、评论动机结论。

## 统一人工验收 Schema

```json id="benchmark_schema"
{
  "case_name": "",
  "content_profile": "",
  "report_quality_score": 0,
  "strategy_plan_score": 0,
  "can_directly_shoot": true,
  "strong_parts": [],
  "weak_parts": [],
  "missing_evidence": [],
  "manual_notes": "",
  "next_fix_suggestion": ""
}
```

评分口径：

- `report_quality_score`：沿用系统 `report_quality.quality_score`，没有该字段时按 0 记录。
- `strategy_plan_score`：人工评估 Creator Strategy Generator 输出是否可执行，满分 100。
- `can_directly_shoot`：是否能不再二次发散，直接组织拍摄或脚本。

## Benchmark A: COS / 美拍 / 颜值

### 输入与样本

- case_name: `beauty_cos_150_pool_selected_8`
- set_id: `clone_5a048bd3b84b4ef6a2774362089ea407`
- 输入方式：主页扫描 + 样本选择 + 证据富化 + 大模型 Map-Reduce + Generate。
- 内容类型：`美拍 / COS / 颜值`
- sample_count: 150
- selected_count: 8
- metadata_only / partial / full: 0 / 8 / 0

### 证据覆盖

- 关键帧：8 / 8
- ASR：8 / 8
- OCR：8 / 8
- 评论：8 / 8
- case report：有

### 蒸馏报告输出

- `creator_clone_strategy`: 有。
- `report_quality`: 100 / 100。
- `diagnostics`: `大模型 Map-Reduce`，`quality_label=高可信`，非 fallback。
- `creator_report_view_model`: 有；包含 `core_judgment`、`traffic_sources`、`formulas`、`repeatable_patterns`、`next_ideas`、`next_actions`、`checklist`、`anti_patterns`。

核心报告摘要：

> 高表现集中在强视觉角色扮演、一句可代入标题钩子、身体动作或队形冲击。最高赞样本绑定可识别 IP 角色，高分享/收藏样本偏多人画面和队形关系。

### Generate 输出

- `next_topics`: 8 条。
  - 示例：热门格斗/二游女角色台词化短片。
  - 示例：姐妹团/拉拉队式多人关系梗。
- `script_templates`: 5 条。
  - 示例：单角色高还原近景片，承担高赞和角色认知建立。
  - 示例：多人同框关系幻想/队形片，承担高分享与高收藏。
- `shot_templates`: 3 条。
  - 示例：近景首帧抓停留：人物脸、眼神、姿态直接占屏；微转头、抬眼或手势变化；近景或半身，轻微俯拍/平拍。
  - 示例：妆造细节推进：先给完整造型，再让手部、发饰、道具进入画面。
- `title_cover_suggestions`: 5 条。
  - 示例：这一眼真的很适合当封面。
  - 示例：同一套妆造，哪个状态更出片？
- `pre_publish_checklist`: 8 条。
  - 示例：目标高赞时看角色识别评论和点赞率。
  - 示例：目标高评时看接话型评论占比。
- `low_confidence_notes`: 4 条。
  - 主要来自缺少完整镜头切换、BGM 和评论语义分布的限制。

### 人工验收

```json
{
  "case_name": "beauty_cos_150_pool_selected_8",
  "content_profile": "美拍 / COS / 颜值",
  "report_quality_score": 100,
  "strategy_plan_score": 84,
  "can_directly_shoot": true,
  "strong_parts": [
    "shot_templates 能落到首帧、眼神、姿态、镜头距离和光线场景。",
    "title_cover_suggestions 可以直接做封面和标题 A/B 测试。",
    "next_topics 保留了角色/IP、多人队形和视觉冲击三个有效方向。"
  ],
  "weak_parts": [
    "部分 script_templates 仍像规则摘要，不够像完整分镜脚本。",
    "low_confidence_notes 仍存在，说明 BGM、完整镜头节奏和评论语义不足。"
  ],
  "missing_evidence": [
    "完整镜头切换节奏",
    "BGM / 卡点信息",
    "评论语义分布"
  ],
  "manual_notes": "该组已能支撑下一条美拍/COS内容拍摄，最强输出是首帧和封面标题建议。",
  "next_fix_suggestion": "下一步让 shot_templates 增加 0-1s / 1-3s / 3-结尾的时间切片，减少二次拆解成本。"
}
```

## Benchmark B: 摄影出片教程 / 轻教学账号

### 输入与样本

- case_name: `photo_beauty_tutorial_150_selected_150`
- set_id: `clone_46d5bcfc47104156b73e2beef3ca014b`
- 输入方式：主页扫描 + 样本选择 + 证据富化 + 大模型 Map-Reduce + Generate。
- 内容类型：`摄影美拍 / 出片教程`
- sample_count: 150
- selected_count: 150
- metadata_only / partial / full: 2 / 148 / 0

### 证据覆盖

- 关键帧：148 / 150
- ASR：148 / 150
- OCR：148 / 150
- 评论：148 / 150
- case report：有

### 蒸馏报告输出

- `creator_clone_strategy`: 有。
- `report_quality`: 92 / 100。
- `diagnostics`: 历史结果未单独持久化顶层 `diagnostics`，但 `creator_report_view_model` 和 `report_quality` 可用。
- `creator_report_view_model`: 有；包含核心判断、流量来源、公式、共性规律、下一步建议、checklist 和 anti_patterns。

核心报告摘要：

> 账号以高颜值、强妆造、轻剧情互动为核心；表层像出片教程，实质是高识别角色/风格、第一眼视觉吸引和一句可转述标题。

### Generate 输出

- `next_topics`: 8 条。
  - 问题：部分标题退化成“下一批选题 1/2”，可执行性不足。
- `script_templates`: 5 条。
  - 示例：角色点名对视公式。
  - 示例：命令式感受放大公式。
- `shot_templates`: 3 条。
  - 示例：近景首帧抓停留。
  - 示例：妆造细节推进。
- `title_cover_suggestions`: 5 条。
  - 示例：这一眼真的很适合当封面。
  - 示例：同一套妆造，哪个状态更出片？
- `pre_publish_checklist`: 8 条。
  - 示例：首帧 1 秒内，陌生用户能否看清脸并知道这是某种明确角色/人设？
  - 示例：标题是否包含角色名、命令式感受句或可直接回复的问题？
- `low_confidence_notes`: 4 条。
  - 主要来自缺少完整镜头拆解、封面图单独证据和具体运镜时长。

### 人工验收

```json
{
  "case_name": "photo_beauty_tutorial_150_selected_150",
  "content_profile": "摄影美拍 / 出片教程",
  "report_quality_score": 92,
  "strategy_plan_score": 68,
  "can_directly_shoot": false,
  "strong_parts": [
    "pre_publish_checklist 能检查首帧、标题和互动问题。",
    "shot_templates 对近景、妆造、光线和标题话题仍然具体。",
    "报告能识别这不是纯知识课，而是出片结果展示加轻教学包装。"
  ],
  "weak_parts": [
    "next_topics 出现“下一批选题 1”这类占位标题，不够可直接拍。",
    "script_templates 更偏美拍公式，不足以验证纯知识/教学账号的步骤化表达。",
    "缺少明确的教程步骤、知识承诺和收藏理由模板。"
  ],
  "missing_evidence": [
    "封面图单独证据",
    "完整镜头拆解",
    "纯知识账号样本"
  ],
  "manual_notes": "这组能验证摄影出片/轻教学近邻，但不能代表知识课、教程课、干货号的完整验收。",
  "next_fix_suggestion": "补一组纯知识/教学账号真实样本，要求脚本模板输出问题切入、步骤、案例证明和收藏理由。"
}
```

### P5.6 修复计划

Benchmark B 当前不是纯知识样本，而是“摄影出片 / 轻教学近邻”。因此 P5.6 只修复两类确定问题：

1. `next_topics` 不得再输出“下一批选题 1/2”“topic 1”“新选题”“选题方向”“未命名选题”等占位标题；当历史报告缺少 `next_ideas` 时，必须按 `content_profile` 生成具体可执行标题。
2. `knowledge` profile 先补硬模板能力：脚本必须覆盖问题切入、步骤推进、案例证明、收藏理由和评论承接；发布前自检必须覆盖问题、结果承诺、步骤、案例/证明和收藏理由。

本轮不把 Benchmark B 当成纯知识账号验收通过；它只能证明系统能识别“出片展示 + 轻教学包装”。

## Benchmark C: 低证据 / 仅元数据

### 输入与样本

- case_name: `low_evidence_metadata_only_2`
- set_id: `clone_16bbf74e4983411a8392521aa1811101`
- 输入方式：多链接/测试素材池 + 大模型 Map-Reduce + Generate。
- 内容类型：`通用短视频`
- sample_count: 2
- selected_count: 2
- metadata_only / partial / full: 2 / 0 / 0

### 证据覆盖

- 关键帧：0 / 2
- ASR：0 / 2
- OCR：0 / 2
- 评论：0 / 2
- case report：无可用媒体证据。

### 蒸馏报告输出

- `creator_clone_strategy`: 有，但字段很弱。
- `report_quality`: 3 / 100。
- `diagnostics`: `quality_label=占位/降级报告`；缺少视频、关键帧、ASR、OCR、评论。
- `creator_report_view_model`: 有，但主要用于说明缺口。

系统诊断摘要：

- 报告结构不完整：缺少 `hooks`、`templates`、`anti_patterns`、`idea_bank`、`validation_rules`。
- 报告可执行性不足：缺少可直接执行的下一条选题。
- 证据不足：2 / 2 条样本尚未达到可蒸馏证据。

### Generate 输出

- `next_topics`: 5 条。
  - 示例：复刻最高互动样本的开头承诺。
  - 示例：把高评样本改成互动问题。
- `script_templates`: 5 条。
  - 示例：先看高赞高评。
  - 示例：证据优先。
- `shot_templates`: 3 条。
  - 示例：信息首帧。
  - 示例：证明镜头。
- `title_cover_suggestions`: 5 条。
  - 示例：这条为什么能起量？
  - 示例：下一条可以直接复刻这个结构。
- `pre_publish_checklist`: 6 条。
- `low_confidence_notes`: 7 条。
  - 示例：报告质量分 3/100，下一批方案需要人工复核。
  - 示例：缺少视频证据，相关建议需要人工复核。
  - 示例：缺少关键帧、ASR、OCR、评论证据，相关建议需要人工复核。

### 人工验收

```json
{
  "case_name": "low_evidence_metadata_only_2",
  "content_profile": "通用短视频",
  "report_quality_score": 3,
  "strategy_plan_score": 72,
  "can_directly_shoot": false,
  "strong_parts": [
    "系统正确把质量分打到 3/100。",
    "low_confidence_notes 明确指出缺少视频、关键帧、ASR、OCR、评论。",
    "所有下一批方案都要求人工复核，没有伪装高置信。"
  ],
  "weak_parts": [
    "兜底 next_topics 和 script_templates 只能提供通用结构，不能代表账号真实规律。",
    "shot_templates 是通用信息流模板，不应直接用于拍摄。"
  ],
  "missing_evidence": [
    "视频文件",
    "关键帧",
    "ASR",
    "OCR",
    "评论",
    "有效互动指标"
  ],
  "manual_notes": "该组的验收重点不是可拍性，而是安全降级。当前 Generator 通过了低证据保护：能生成兜底建议，但明确低置信并要求复核。",
  "next_fix_suggestion": "前端应在低证据 strategy plan 上强化视觉提示：只可作为补证据清单，不建议直接拍摄。"
}
```

## 总体验收结论

### 已通过

- 美拍/COS 场景能够生成可拍的首帧、镜头、封面标题和发布前 checklist。
- 摄影出片/轻教学场景能够识别“出片结果展示 + 轻教学包装”的内容本质，不会误判成纯知识课。
- 低证据场景能够正确给出低质量分和低置信 notes，没有假装完整账号规律。

### 未完全通过

- 纯知识/教学账号尚缺专门真实样本，不能只用摄影出片教程替代。
- `next_topics` 在部分历史报告上会退化成“下一批选题 1/2”，说明 report_view_model 的 `next_ideas` 或 generator fallback 需要更强约束。
- `script_templates` 对美拍类可用，但对知识类还缺“问题 -> 步骤 -> 案例 -> 收藏理由”的硬模板验收。

### 下一轮修复建议

1. 补一组纯知识/教学账号真实样本，样本量建议 20-50 条，至少 5 条完整证据。
2. Generator 对 `next_topics` 做占位文本拦截：禁止输出“下一批选题 N”。
3. Generator 按内容类型引入硬验收：
   - 美拍：首帧 / 妆造 / 镜头 / 标题 / 封面。
   - 知识：问题 / 步骤 / 证明 / 收藏理由 / 可信来源。
   - 低证据：只允许补证据建议和低置信复核建议。
4. 前端对 `low_confidence_notes` 非空的 strategy plan 增加“不可直接拍摄”的醒目提示。

### TODO: 纯知识 / 教学账号真实样本

- 补充纯知识 / 教学账号真实样本 20-50 条。
- 至少 5 条样本达到完整证据：视频、关键帧、ASR、OCR、评论或等价人工证据。
- 重新评估 `knowledge` strategy plan：
  - `next_topics` 是否围绕真实问题和收藏理由。
  - `script_templates` 是否真的包含问题、步骤、案例、收藏和评论承接。
  - `pre_publish_checklist` 是否能用于发布前质量检查。
