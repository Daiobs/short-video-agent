from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisProfile:
    category_id: str
    label: str
    description: str
    keywords: tuple[str, ...]
    analysis_lens: tuple[str, ...]
    key_questions: tuple[str, ...]
    content_ratio: tuple[str, ...]
    prompt_focus: tuple[str, ...]


BASE_ANALYSIS_FOCUS = (
    "前3秒钩子",
    "封面标题",
    "画面节奏",
    "字幕结构",
    "音乐和情绪路径",
    "人设呈现",
    "可借鉴点",
    "可复刻脚本",
    "分镜表",
    "发布文案和标签",
    "如何改编到我的账号",
)


ANALYSIS_PROFILES: tuple[AnalysisProfile, ...] = (
    AnalysisProfile(
        category_id="beauty_cos",
        label="美拍 / COS / 颜值向",
        description="重点拆第一眼吸引力、人物状态、妆造服化、镜头距离、姿态动作和氛围感。",
        keywords=("cos", "少御", "御姐", "甜妹", "妆", "穿搭", "写真", "美拍", "颜值", "舞蹈", "黑婚纱"),
        analysis_lens=(
            "第一眼是否直接给出人物脸、眼神、姿态或服化亮点",
            "妆造、服装、发型、道具和背景是否统一服务同一种人设",
            "镜头距离、俯仰角、光线颜色是否强化颜值或氛围",
            "动作变化是否足够让观众继续看，而不是只有静态摆拍",
            "标题和话题是否把人物气质转化为可点击理由",
        ),
        key_questions=(
            "0-1 秒观众第一眼会被什么吸引？",
            "人物人设更偏甜美、少御、冷感、反差，还是氛围感？",
            "画面里最可复刻的元素是妆造、动作、镜头、布景还是标题？",
            "如果复刻到你的账号，哪些元素要保留，哪些要替换成更安全或更符合人设的表达？",
        ),
        content_ratio=(
            "视觉吸引 45%",
            "人物人设 25%",
            "动作节奏 15%",
            "标题话题 10%",
            "互动引导 5%",
        ),
        prompt_focus=(
            "把 0-3 秒逐帧拆成第一眼吸引点、人物动作和表情变化。",
            "判断妆造、服装、背景、光线和镜头角度如何共同塑造人设。",
            "输出一个适合 COS / 甜美账号复刻的安全改编方案。",
        ),
    ),
    AnalysisProfile(
        category_id="motivational",
        label="鸡汤 / 情绪价值",
        description="重点拆情绪起点、金句密度、转折、共鸣人群和评论区触发点。",
        keywords=("人生", "低谷", "自由", "努力", "坚持", "热爱", "治愈", "焦虑", "情绪", "文案", "清醒", "成长"),
        analysis_lens=(
            "开头是否直接击中一种具体处境或情绪痛点",
            "文案是否有压缩表达、反差表达或金句表达",
            "画面和音乐是否承托情绪，而不是和文案割裂",
            "中段是否有情绪递进，结尾是否给出释放、鼓励或态度",
            "评论区是否容易出现代入、共鸣、争议或自我表达",
        ),
        key_questions=(
            "这条内容在替谁说话？",
            "最强的一句金句是什么，能否改成你的账号语气？",
            "情绪路径是低谷到翻盘、委屈到释放，还是孤独到自由？",
            "如果复刻，应该复刻文案结构、画面情绪，还是声音节奏？",
        ),
        content_ratio=(
            "情绪痛点 35%",
            "金句文案 30%",
            "音乐氛围 15%",
            "画面承托 10%",
            "评论触发 10%",
        ),
        prompt_focus=(
            "提炼这条视频的情绪路径和目标人群。",
            "拆出可复用的金句结构，而不是照搬原文。",
            "给出 3 个不同语气的复刻标题和开头文案。",
        ),
    ),
    AnalysisProfile(
        category_id="tutorial",
        label="教学 / 教程",
        description="重点拆痛点、步骤、前后对比、信息密度和观众执行成本。",
        keywords=("教程", "教学", "怎么", "如何", "步骤", "技巧", "干货", "方法", "避坑", "新手", "一招"),
        analysis_lens=(
            "开头是否明确告诉用户能解决什么问题",
            "步骤是否足够短、清楚、可执行",
            "是否有前后对比或结果展示来证明价值",
            "字幕、口播和画面是否同步承载信息",
            "是否有收藏、转发或评论提问的理由",
        ),
        key_questions=(
            "这条视频解决了什么具体问题？",
            "用户看完能立刻做什么？",
            "哪一步最容易被压缩成标题或封面卖点？",
            "信息密度是否太高，需不需要拆成系列？",
        ),
        content_ratio=(
            "痛点承诺 25%",
            "步骤清晰 35%",
            "结果证明 20%",
            "字幕信息 10%",
            "收藏理由 10%",
        ),
        prompt_focus=(
            "把教程拆成问题、步骤、结果、注意事项四块。",
            "判断哪些步骤适合保留，哪些需要重拍或补充特写。",
            "输出一个更适合短视频节奏的教学分镜表。",
        ),
    ),
    AnalysisProfile(
        category_id="plot_twist",
        label="剧情 / 反转",
        description="重点拆冲突、悬念、人物关系、信息差和结尾反转。",
        keywords=("剧情", "反转", "没想到", "结局", "最后", "挑战", "整蛊", "误会", "故事", "名场面"),
        analysis_lens=(
            "开头是否迅速建立人物、目标或冲突",
            "中段是否持续制造悬念或信息差",
            "关键转折是否提前埋伏笔",
            "结尾是否有反转、爽点、笑点或评论争议点",
            "表演、字幕、剪辑是否服务剧情推进",
        ),
        key_questions=(
            "这条剧情的核心冲突是什么？",
            "观众为什么会想看到结尾？",
            "反转是否来自信息差、身份差、预期差还是情绪差？",
            "能否换成你的角色和场景复刻同一结构？",
        ),
        content_ratio=(
            "冲突建立 25%",
            "悬念推进 25%",
            "反转强度 25%",
            "表演表达 15%",
            "互动争议 10%",
        ),
        prompt_focus=(
            "按起因、冲突、转折、结尾拆剧情结构。",
            "指出观众继续看的悬念点在哪里。",
            "输出一个可换角色复刻的剧情脚本。",
        ),
    ),
    AnalysisProfile(
        category_id="product_seed",
        label="种草 / 带货",
        description="重点拆需求场景、卖点露出、信任证据、前后对比和转化路径。",
        keywords=("好物", "推荐", "测评", "种草", "下单", "同款", "平替", "开箱", "购物", "链接", "买"),
        analysis_lens=(
            "开头是否出现明确需求场景或痛点",
            "产品卖点是否用画面证明，而不是只靠口播",
            "是否有前后对比、细节特写或真实使用过程",
            "信任感来自测评、价格、场景、个人体验还是评论背书",
            "结尾是否自然引导收藏、评论、私信或购买",
        ),
        key_questions=(
            "用户为什么需要这个东西？",
            "最强卖点是否在前 3 秒内出现？",
            "有没有足够的证据证明它有用？",
            "如果不直接卖货，能否改成种草内容或场景内容？",
        ),
        content_ratio=(
            "痛点场景 25%",
            "卖点证明 30%",
            "细节特写 15%",
            "信任建立 20%",
            "转化引导 10%",
        ),
        prompt_focus=(
            "拆出痛点、卖点、证据和转化动作。",
            "判断画面是否足够证明产品价值。",
            "输出一个更自然的种草短视频脚本。",
        ),
    ),
    AnalysisProfile(
        category_id="knowledge",
        label="知识 / 观点",
        description="重点拆观点强度、信息结构、例子、反常识和可讨论性。",
        keywords=("知识", "观点", "科普", "认知", "商业", "心理", "逻辑", "真相", "普通人", "底层"),
        analysis_lens=(
            "开头观点是否足够明确、反常识或有争议",
            "论证是否有例子、数据、类比或生活场景",
            "结构是否从问题到观点再到行动建议",
            "字幕是否帮助理解，而不是堆满信息",
            "结尾是否留下讨论点或收藏理由",
        ),
        key_questions=(
            "这条内容的核心观点一句话是什么？",
            "观点是否新、狠、准，还是只是常识复述？",
            "有没有能让观众转发或评论的争议点？",
            "你的账号能否用更具人设的方式表达同一观点？",
        ),
        content_ratio=(
            "观点钩子 30%",
            "论证结构 30%",
            "例子类比 20%",
            "字幕承载 10%",
            "讨论引导 10%",
        ),
        prompt_focus=(
            "提炼核心观点和反常识表达。",
            "拆解论证结构和例子使用。",
            "输出一个适合你账号风格的观点脚本。",
        ),
    ),
    AnalysisProfile(
        category_id="edge_visual",
        label="强视觉吸引 / 尺度边界",
        description="重点拆视觉吸引点、平台风险、可替代表达和账号长期安全性。",
        keywords=("擦边", "性感", "辣妹", "身材", "黑丝", "泳装", "吊带", "腿", "尺度", "诱惑"),
        analysis_lens=(
            "视觉吸引来自服装、姿态、镜头距离、光线还是动作节奏",
            "内容是否存在平台审核、账号标签或受众偏移风险",
            "是否能用妆造、氛围、剧情、角色设定替代高风险表达",
            "标题和评论区是否可能把内容导向低质量互动",
            "复刻时应保留吸引结构，而不是照搬尺度表达",
        ),
        key_questions=(
            "这条内容的吸引力是否主要依赖尺度？",
            "能否把吸引点替换成角色、剧情、妆造或镜头语言？",
            "哪些动作和镜头可能影响账号长期定位？",
            "如何改成更安全、更高级、更符合人设的版本？",
        ),
        content_ratio=(
            "视觉吸引 40%",
            "尺度风险 25%",
            "人设匹配 15%",
            "可替代表达 15%",
            "评论质量 5%",
        ),
        prompt_focus=(
            "评估视觉吸引力和平台风险边界。",
            "提出不依赖尺度的替代表达方案。",
            "输出更安全、更高级的复刻脚本。",
        ),
    ),
    AnalysisProfile(
        category_id="generic",
        label="通用短视频",
        description="用于无法明确分类的素材，先按钩子、节奏、人设、文案和复刻成本拆解。",
        keywords=(),
        analysis_lens=(
            "开头是否有明确第一眼吸引点",
            "中段是否有信息、动作或情绪变化维持观看",
            "结尾是否有记忆点、互动点或复看点",
            "标题、话题、封面和画面是否一致",
            "这个结构能否迁移到你的账号方向",
        ),
        key_questions=(
            "这条视频靠什么让人停下来？",
            "观众为什么看完？",
            "最值得复刻的是结构、画面、文案、声音还是人设？",
            "复刻成本高不高，哪些元素可以低成本替换？",
        ),
        content_ratio=(
            "前3秒钩子 25%",
            "画面节奏 25%",
            "人设表达 20%",
            "文案标题 15%",
            "互动引导 15%",
        ),
        prompt_focus=(
            "按通用短视频结构拆解钩子、节奏、人设、文案。",
            "判断最可复刻的 3 个元素。",
            "输出一个低成本复刻版本。",
        ),
    ),
)


PROFILE_MAP = {profile.category_id: profile for profile in ANALYSIS_PROFILES}
DEFAULT_CATEGORY = "generic"


def get_analysis_profile(category_id: str | None) -> AnalysisProfile:
    return PROFILE_MAP.get(category_id or "", PROFILE_MAP[DEFAULT_CATEGORY])


def list_analysis_profiles() -> list[dict]:
    return [
        {
            "category_id": profile.category_id,
            "label": profile.label,
            "description": profile.description,
        }
        for profile in ANALYSIS_PROFILES
    ]


def infer_content_category(text: str) -> str:
    normalized = (text or "").lower()
    best_category = DEFAULT_CATEGORY
    best_score = 0
    for profile in ANALYSIS_PROFILES:
        if profile.category_id == DEFAULT_CATEGORY:
            continue
        score = sum(1 for keyword in profile.keywords if keyword.lower() in normalized)
        if score > best_score:
            best_category = profile.category_id
            best_score = score
    return best_category


def build_analysis_context(category_id: str) -> dict:
    profile = get_analysis_profile(category_id)
    return {
        "category_id": profile.category_id,
        "label": profile.label,
        "description": profile.description,
        "analysis_lens": list(profile.analysis_lens),
        "key_questions": list(profile.key_questions),
        "content_ratio": list(profile.content_ratio),
        "prompt_focus": list(profile.prompt_focus),
    }


def build_prompt(metadata: dict, ffprobe: dict, analysis_context: dict) -> str:
    lens = "\n".join(f"* {item}" for item in analysis_context.get("analysis_lens", []))
    questions = "\n".join(f"* {item}" for item in analysis_context.get("key_questions", []))
    ratios = "\n".join(f"* {item}" for item in analysis_context.get("content_ratio", []))
    prompt_focus = "\n".join(f"* {item}" for item in analysis_context.get("prompt_focus", []))
    focus = "\n".join(f"* {item}" for item in BASE_ANALYSIS_FOCUS)

    return f"""# 爆款案例拆解 Prompt

请基于素材包中的 `contact_sheet.jpg`、关键帧、基础元数据和 `analysis_input.json`，分析该短视频为什么值得复盘，并输出适合我账号复刻的方案。

如果 `analysis_input.json` 中存在 `analysis_enrichment`，请优先结合其中的 ASR 转写、OCR 画面文字、评论摘要和指标快照，不要只看关键帧。

注意：如果点赞、评论、分享为空，请明确说明“无法判断真实爆款强度，只能分析内容结构”。

## 1. 基础信息

* 标题：{metadata.get("title", "")}
* 作者：{metadata.get("author", "")}
* 点赞：{metadata.get("like_count", 0)}
* 评论：{metadata.get("comment_count", 0)}
* 分享：{metadata.get("share_count", 0)}
* 发布时间：{metadata.get("create_time", "")}
* 视频时长：{ffprobe.get("duration", 0)}
* 分辨率：{ffprobe.get("width", 0)}x{ffprobe.get("height", 0)}
* 来源链接：{metadata.get("source_url", "")}
* 内容类型：{analysis_context.get("label", "通用短视频")}

## 2. 本类型优先分析镜头

{lens}

## 3. 内容占比判断

请按以下维度估算这条视频的内容占比，并说明判断依据：

{ratios}

## 4. 关键问题

{questions}

## 5. 前 3 秒钩子分析

请结合 0s、1s、2s、3s 关键帧分析：

* 第一眼看到什么；
* 信息是否足够明确；
* 是否有表情、姿态、反差、冲突或结果承诺；
* 观众继续看的理由是什么；
* 如果要优化，前 3 秒应该怎么重拍。

## 6. 分类重点

{prompt_focus}

## 7. 富化数据拆解

如果素材包已生成 `analysis_enrichment`，请补充分析：

* ASR 语音转写：开头第一句话、口播钩子、金句密度、脚本结构；
* OCR 画面文字：封面承诺、字幕节奏、文字和画面的关系；
* 评论摘要：用户需求、高频词、评论区互动钩子；
* 指标快照：当前互动数据是否足以判断真实爆款强度。

## 8. 通用复盘清单

{focus}

## 9. 可借鉴点

请输出：

* 最值得学习的 3-5 个点；
* 哪些点适合我的账号；
* 哪些点不建议照搬；
* 哪些点可以低成本替换。

## 10. 可复刻脚本

请给出一个适合我账号的改编版本，包括：

* 视频标题；
* 3 秒开头；
* 分镜表；
* 拍摄动作；
* 字幕；
* 发布文案；
* 标签；
* 评论区引导。

## 11. 分镜表

请输出表格：

| 时间 | 画面 | 动作 | 字幕 | 音乐/节奏 | 目的 |
| -- | -- | -- | -- | ----- | -- |

## 12. 发布建议

请给出：

* 适合发布时间；
* 封面标题；
* 话题标签；
* 置顶评论；
* 是否适合投放或二创改编。
"""
