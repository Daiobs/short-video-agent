(function initializeCreatorReportView(global) {
  "use strict";

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function objectValue(value) {
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  }

  function hasContent(value) {
    if (Array.isArray(value)) return value.some(hasContent);
    if (value && typeof value === "object") return Object.values(value).some(hasContent);
    return value !== null && value !== undefined && String(value).trim() !== "";
  }

  function renderValue(value) {
    if (!hasContent(value)) return "";
    if (Array.isArray(value)) return `<ul class="public-report-list">${value.filter(hasContent).map((item) => `<li>${renderValue(item)}</li>`).join("")}</ul>`;
    const labels = {
      subject: "主体", composition: "构图", lighting_color: "光线色彩", scene: "场景",
      movement_rhythm: "动作变化", style_keywords: "风格", first_impression: "第一眼",
      why_stop_scrolling: "停留理由", optimization: "优化方向", first_3_seconds: "开头观察",
      script_structure: "表达结构", opening_line: "开头一句", spoken_hook: "口播吸引点",
      has_speech: "口播判断", quotable_lines: "关键表达", remake_angle: "改编角度",
      copyable_points: "可迁移做法", avoid_copying: "不要照搬", opening_3s: "开头设计",
      shot_table: "拍摄方案", caption: "文案", titles: "标题", hashtags: "标签",
      visual_style: "视觉风格", shot_types: "景别", scene_order: "呈现顺序",
      opening_hooks: "开头结构", ending_patterns: "结尾方式", subtitle_voice: "字幕与声音",
      assumptions: "观众假设", tension_sources: "张力来源", detail_selection_rules: "细节选择",
      novelty_vs_familiarity: "熟悉与新鲜感", audience_promise: "观众承诺",
      what_the_creator_sells: "账号定位", hidden_genre: "表达类型", audience_assumption: "观众假设",
    };
    if (value && typeof value === "object") return `<dl class="public-report-fields">${Object.entries(value).filter(([, item]) => hasContent(item)).map(([key, item]) => `<dt>${escapeHtml(labels[key] || key)}</dt><dd>${renderValue(item)}</dd>`).join("")}</dl>`;
    return escapeHtml(value);
  }

  function renderFocus(result) {
    const focus = objectValue(result.analysis_focus);
    const review = objectValue(result.category_review);
    const hasFocus = hasContent(focus.primary) || hasContent(focus.label);
    const hasReview = hasContent(review.suggested_category) || hasContent(review.reason);
    if (!hasFocus && !hasReview) return "";
    const labels = {
      auto: "自动判断", beauty_cos: "美拍 / COS / 颜值", photo_beauty: "摄影美拍 / 出片教程",
      tutorial: "步骤教程", knowledge: "知识 / 观点", motivational: "情绪文案",
      emotional_copy: "情绪文案", plot_twist: "剧情 / 反转", story_twist: "剧情 / 反转",
      product_seed: "种草 / 带货", commerce_seed: "种草 / 带货",
      edge_visual: "视觉吸引", generic: "通用短视频", general: "通用短视频",
    };
    const directionLabel = (value) => Array.isArray(value)
      ? value.map(directionLabel)
      : typeof value === "string" && Object.hasOwn(labels, value) ? labels[value] : value;
    const sources = {auto: "自动判断", user: "用户指定", legacy: "历史报告，来源未记录"};
    return `<section class="analysis-focus" style="min-width:0;overflow-wrap:anywhere" aria-label="本次分析重点">
      ${hasFocus ? `<h4>本次分析重点：${escapeHtml(focus.label || directionLabel(focus.primary))}</h4>
      <p>${escapeHtml(sources[focus.source] || "来源未记录")}</p>` : ""}
      ${hasFocus || hasReview ? `<details><summary>分析方向说明${hasReview ? " · 模型建议可复核" : ""}</summary>` : ""}
      ${hasContent(focus.reason) ? `<p>判断依据：${renderValue(focus.reason)}</p>` : ""}
      ${hasContent(focus.initial_category) ? `<p>自动初判：${renderValue(directionLabel(focus.initial_category))}</p>` : ""}
      ${hasContent(focus.auxiliary) ? `<details><summary>辅助视角</summary>${renderValue(directionLabel(focus.auxiliary))}</details>` : ""}
      ${hasReview ? `<section aria-label="模型复核建议"><h4>模型复核建议（未自动切换）</h4>
        ${hasContent(review.suggested_category) ? `<p>建议方向：${renderValue(directionLabel(review.suggested_category))}</p>` : ""}
        ${hasContent(review.reason) ? `<p>复核依据：${renderValue(review.reason)}</p>` : ""}
        <p>此建议不改变本次报告采用的方向，也不会自动重新分析。</p></section>` : ""}
      ${hasFocus || hasReview ? "</details>" : ""}
    </section>`;
  }

  function renderFocusedAnalysis(items) {
    if (!Array.isArray(items)) return "";
    return items.map(objectValue).filter((item) => [item.observation, item.interpretation, item.transfer, item.evidence, item.uncertainty].some(hasContent)).map((item) => `
      <section style="min-width:0;overflow-wrap:anywhere">
        ${hasContent(item.question) ? `<h4>${escapeHtml(item.question)}</h4>` : ""}
        <dl class="public-report-fields">${[["观察", item.observation], ["解释", item.interpretation], ["可迁移方法", item.transfer], ["支持证据", item.evidence], ["尚不能确认", item.uncertainty]].filter(([, value]) => hasContent(value)).map(([label, value]) => `<dt>${label}</dt><dd>${renderValue(value)}</dd>`).join("")}</dl>
      </section>`).join("");
  }

  function renderSections(focus, sections) {
    const order = Array.isArray(focus?.section_order) ? focus.section_order : [];
    const available = sections.filter((section) => hasContent(section.value));
    const rank = (section) => {
      if (section.key === "focused_analysis") return -2;
      if (section.key === "content_groups") return -1;
      const index = order.findIndex((key) => key === section.key || section.aliases?.includes(key));
      return index < 0 ? Infinity : index;
    };
    const primary = order.length ? available.filter((section) => rank(section) !== Infinity) : available;
    if (order.length) primary.sort((a, b) => rank(a) - rank(b));
    const auxiliary = order.length ? available.filter((section) => rank(section) === Infinity) : [];
    const markup = (section) => `<section data-analysis-section="${escapeHtml(section.key)}" style="min-width:0;overflow-wrap:anywhere"><h4>${escapeHtml(section.label)}</h4>${section.html ?? renderValue(section.value)}</section>`;
    return primary.map(markup).join("") + (auxiliary.length ? `<details class="analysis-auxiliary"><summary>辅助分析</summary>${auxiliary.map(markup).join("")}</details>` : "");
  }

  function createRenderer(helpers = {}) {
    const {
      compactReportList,
      creatorStrategyFromResult,
      formatNumber,
      normalizeItems,
      publicValueHasContent,
      qualityLabelFromScore,
      renderCompactPerformanceSegments,
      renderCreatorCloneEvidenceOverview,
      renderFormulaCards,
      renderPublicCard,
      renderPublicFields,
      renderPublicList,
      renderTopicBuckets,
      cleanPublicReportText,
    } = helpers;

    const required = {
      compactReportList,
      creatorStrategyFromResult,
      formatNumber,
      normalizeItems,
      publicValueHasContent,
      qualityLabelFromScore,
      renderCompactPerformanceSegments,
      renderCreatorCloneEvidenceOverview,
      renderFormulaCards,
      renderPublicCard,
      renderPublicFields,
      renderPublicList,
      renderTopicBuckets,
      cleanPublicReportText,
    };
    Object.entries(required).forEach(([name, value]) => {
      if (typeof value !== "function") {
        throw new TypeError(`CreatorReportView requires helper: ${name}`);
      }
    });

    function reportValueHasAny(...values) {
      return values.some((value) => publicValueHasContent(value));
    }

    function renderFormulaList(strategy, result) {
      const templates = normalizeItems(strategy.templates);
      const formulas = normalizeItems(result.transferable_formulas);
      if (templates.length || formulas.length) {
        return renderFormulaCards(templates.length ? templates : formulas);
      }
      const fallback = compactReportList(
        strategy.content_strategy,
        result.creator_clone_spec?.structure_rules,
        result.creator_clone_spec?.visual_rules,
        result.expression_patterns?.opening_hooks,
      ).slice(0, 4);
      return renderPublicList(fallback, "本次没有返回独立公式，建议先从内容策略中人工提炼 2-3 个可复用拍法。");
    }

    function renderThinkingPatterns(patterns = {}) {
      return `
        ${renderPublicFields([["熟悉与新鲜感", patterns.novelty_vs_familiarity]])}
        <h5>观众假设</h5>
        ${renderPublicList(patterns.assumptions, "暂无观众假设。")}
        <h5>张力来源</h5>
        ${renderPublicList(patterns.tension_sources, "暂无张力判断。")}
        <h5>细节选择规则</h5>
        ${renderPublicList(patterns.detail_selection_rules, "暂无细节选择规则。")}
      `;
    }

    function renderExpressionPatterns(patterns = {}, spec = {}) {
      return renderPublicList(compactReportList(
        patterns.opening_hooks,
        patterns.scene_order,
        patterns.shot_types,
        patterns.subtitle_voice,
        patterns.visual_style,
        patterns.ending_patterns,
        spec.expression_rules,
        spec.visual_rules,
        spec.ending_rules,
      ), "暂无表达/视觉规律。");
    }

    function renderHero({viewModel, result, overview, templateLabel, positioningText}) {
      const evidence = objectValue(viewModel.evidence_counts);
      const counts = objectValue(overview.understanding_counts);
      const selectedCount = Number(evidence.selected_count ?? overview.selected_count ?? 0);
      const sampleCount = Number(evidence.sample_count ?? overview.sample_count ?? 0);
      const confidence = viewModel.confidence_label || overview.confidence || "";
      const evidenceLine = viewModel.confidence_note
        || `完整 ${formatNumber(counts.full || evidence.understanding_full || 0)} · 部分 ${formatNumber(counts.partial || evidence.understanding_partial || 0)} · 仅元数据 ${formatNumber(counts.metadata_only || evidence.understanding_metadata_only || 0)}`;
      const mediaLine = [evidence.with_video, evidence.with_keyframes, evidence.with_asr, evidence.with_ocr, evidence.with_comments]
        .some((value) => value !== undefined)
        ? `视频 ${formatNumber(evidence.with_video || 0)} · 关键帧 ${formatNumber(evidence.with_keyframes || 0)} · ASR ${formatNumber(evidence.with_asr || 0)} · OCR ${formatNumber(evidence.with_ocr || 0)} · 评论 ${formatNumber(evidence.with_comments || 0)}`
        : "";
      return `
        <article class="creator-report-hero-card">
          <div>
            <span>创作者蒸馏报告</span>
            <h3>${escapeHtml(viewModel.headline || positioningText || "账号规律已完成蒸馏")}</h3>
            <p>${escapeHtml(viewModel.summary || result.summary || "请先查看下方核心结论和可复刻公式。")}</p>
          </div>
          <dl>
            <dt>分析模板</dt>
            <dd>${escapeHtml(viewModel.template_label || templateLabel || "自动识别")}</dd>
            <dt>样本</dt>
            <dd>${formatNumber(selectedCount)} / ${formatNumber(sampleCount)}</dd>
            <dt>证据完整度</dt>
            <dd>${escapeHtml(evidenceLine)}</dd>
            ${mediaLine ? `<dt>证据覆盖</dt><dd>${escapeHtml(mediaLine)}</dd>` : ""}
            ${confidence ? `<dt>置信度</dt><dd>${escapeHtml(confidence)}</dd>` : ""}
          </dl>
        </article>
      `;
    }

    function splitSummary(value, options = {}) {
      const maxParagraphs = options.maxParagraphs || 4;
      const maxChars = options.maxChars || 130;
      const text = cleanPublicReportText(value || "创作者蒸馏完成。");
      if (!text) {
        return ["创作者蒸馏完成。"];
      }
      const sentences = text
        .split(/(?<=[。！？!?；])\s*/)
        .map((item) => item.trim())
        .filter(Boolean);
      if (sentences.length <= 1) {
        return [text];
      }
      const paragraphs = [];
      sentences.forEach((sentence) => {
        const previous = paragraphs[paragraphs.length - 1] || "";
        if (previous && `${previous}${sentence}`.length <= maxChars) {
          paragraphs[paragraphs.length - 1] = `${previous}${sentence}`;
        } else if (paragraphs.length < maxParagraphs) {
          paragraphs.push(sentence);
        }
      });
      return paragraphs.length ? paragraphs : [text];
    }

    function renderSummary(summary) {
      const paragraphs = splitSummary(summary);
      const headline = paragraphs[0] || "创作者蒸馏完成。";
      const rest = paragraphs.slice(1);
      return `
        <strong>${escapeHtml(headline)}</strong>
        ${rest.length ? `
          <div class="public-analysis-hero-body">
            ${rest.map((item) => `<p>${escapeHtml(item)}</p>`).join("")}
          </div>
        ` : ""}
      `;
    }

    function renderSampleEvidence(items = []) {
      const rows = normalizeItems(items).filter((item) => item && typeof item === "object").slice(0, 6);
      if (!rows.length) {
        return '<p class="muted compact-copy">暂无样本证据引用；请优先查看高互动样本并补齐关键帧/ASR/OCR。</p>';
      }
      return `
        <ul class="public-report-list creator-evidence-reference-list">
          ${rows.map((item) => {
            const metric = item.metric_label
              ? `${item.metric_label} ${formatNumber(item.metric_value || 0)}`
              : item.metric
                ? `${item.metric} ${formatNumber(item.metric_value || 0)}`
                : "";
            const evidence = item.evidence_level ? `证据 ${item.evidence_level}` : "";
            const meta = [metric, evidence, item.sample_id].filter(Boolean).join(" · ");
            return `<li><strong>${escapeHtml(item.title || "代表样本")}</strong>${meta ? ` <span class="muted">(${escapeHtml(meta)})</span>` : ""}${item.reason ? `<br><span class="muted">${escapeHtml(item.reason)}</span>` : ""}</li>`;
          }).join("")}
        </ul>
      `;
    }

    function renderLowConfidence(valueUpgrade = {}) {
      const reasons = normalizeItems(valueUpgrade.low_confidence_reasons || valueUpgrade.evidence_gaps).slice(0, 6);
      if (!valueUpgrade.low_confidence && !reasons.length) {
        return '<p class="muted compact-copy">当前没有明显低置信提示。</p>';
      }
      return `
        <div class="creator-low-confidence-note">
          <strong>低置信提示</strong>
          ${renderPublicList(reasons, "证据不足的结论会在这里显示。")}
        </div>
      `;
    }

    function renderDiagnostics(valueUpgrade = {}, quality = {}) {
      const diagnostics = objectValue(valueUpgrade.diagnostics);
      if (!diagnostics.source_label && !diagnostics.coverage_text && !diagnostics.quality_label) {
        return "";
      }
      const score = diagnostics.quality_score ?? quality.quality_score ?? quality.score;
      const missing = normalizeItems(diagnostics.missing_evidence_labels).slice(0, 5);
      return `
        <div class="creator-report-diagnostics">
          <div class="creator-report-diagnostic-grid">
            <article><span>报告来源</span><strong>${escapeHtml(diagnostics.source_label || "待确认")}</strong></article>
            <article><span>结构与可执行性检查</span><strong>${score !== undefined && score !== null ? `${formatNumber(score)}/100` : "未记录"}</strong><p>仅检查报告结构与落地项，不是事实准确率或效果验证。</p></article>
            <article class="wide"><span>已记录的素材库存</span><strong>${escapeHtml(diagnostics.coverage_text || "暂无素材库存统计")}</strong></article>
          </div>
          ${diagnostics.is_fallback && diagnostics.fallback_reason ? `<p class="creator-report-source-warning">${escapeHtml(diagnostics.fallback_reason)}</p>` : ""}
          ${missing.length ? `<p class="muted compact-copy">优先补齐：${escapeHtml(missing.join("、"))}</p>` : ""}
        </div>
      `;
    }

    function renderQualitySummary(valueUpgrade = {}) {
      const quality = objectValue(valueUpgrade.quality);
      const score = quality.quality_score ?? quality.score;
      const missing = normalizeItems(quality.missing_evidence).slice(0, 4);
      const warnings = normalizeItems(quality.warnings).slice(0, 3);
      const diagnostics = renderDiagnostics(valueUpgrade, quality);
      if (score === undefined && !missing.length && !warnings.length && !diagnostics) {
        return "";
      }
      return `
        <div class="creator-report-quality-summary">
          ${diagnostics}
          ${score !== undefined && !diagnostics ? `<p><strong>结构与可执行性检查：</strong>${formatNumber(score)} / 100。不是事实可信度。</p>` : ""}
          ${missing.length ? `<h5>缺少的证据或落地项</h5>${renderPublicList(missing)}` : ""}
          ${warnings.length ? `<h5>质量提醒</h5>${renderPublicList(warnings)}` : ""}
        </div>
      `;
    }

    function renderEvidenceDetails(overview, result, viewModel) {
      const thinking = objectValue(result.thinking_patterns);
      const patterns = objectValue(result.expression_patterns);
      const spec = objectValue(result.creator_clone_spec);
      const strategy = objectValue(creatorStrategyFromResult(result));
      const hasThinking = reportValueHasAny(thinking.assumptions, thinking.tension_sources, thinking.detail_selection_rules, thinking.novelty_vs_familiarity);
      const hasExpression = reportValueHasAny(
        patterns.opening_hooks,
        patterns.scene_order,
        patterns.shot_types,
        patterns.subtitle_voice,
        patterns.visual_style,
        patterns.ending_patterns,
        spec.expression_rules,
        spec.visual_rules,
      );
      return `
        <details class="creator-report-evidence-details">
          <summary>报告依据：样本、证据完整度和后台细节</summary>
          ${renderCreatorCloneEvidenceOverview(overview)}
          ${renderCompactPerformanceSegments(objectValue(result.performance_segments))}
          <div class="creator-report-evidence-inner">
            ${reportValueHasAny(result.topic_buckets) ? `<section><h5>选题桶</h5>${renderTopicBuckets(result.topic_buckets)}</section>` : ""}
            ${hasThinking ? `<section><h5>思维模式</h5>${renderThinkingPatterns(thinking)}</section>` : ""}
            ${hasExpression ? `<section><h5>表达 / 视觉依据</h5>${renderExpressionPatterns(patterns, spec)}</section>` : ""}
            ${reportValueHasAny(strategy.templates, result.transferable_formulas) ? `<section><h5>原始公式字段</h5>${renderFormulaList(strategy, result)}</section>` : ""}
            ${reportValueHasAny(result.evidence_gaps) ? `<section><h5>证据缺口</h5>${renderPublicList(result.evidence_gaps)}</section>` : ""}
            ${reportValueHasAny(viewModel.technical_notes) ? `<section><h5>运行备注</h5>${renderPublicList(viewModel.technical_notes)}</section>` : ""}
          </div>
        </details>
      `;
    }

    function renderReportMarkup({result: rawResult, overview: rawOverview, templateLabel = "", viewModel: rawViewModel}) {
      const result = objectValue(rawResult);
      const overview = objectValue(rawOverview);
      const viewModel = objectValue(rawViewModel);
      const strategy = objectValue(creatorStrategyFromResult(result));
      const positioning = objectValue(result.creator_positioning);
      const sections = objectValue(viewModel.sections);
      const valueUpgrade = objectValue(viewModel.value_upgrade);
      const observation = objectValue(valueUpgrade.observation);
      const explanation = objectValue(valueUpgrade.explanation);
      const execution = objectValue(valueUpgrade.execution);
      const focus = objectValue(result.analysis_focus);
      const first = (...values) => values.find(hasContent);
      const unique = (...values) => {
        const seen = new Set();
        return values.flatMap((value) => Array.isArray(value) ? value : hasContent(value) ? [value] : [])
          .filter((value) => hasContent(value) && !seen.has(JSON.stringify(value)) && seen.add(JSON.stringify(value)));
      };
      const samples = new Map();
      const collectSamples = (value) => {
        if (Array.isArray(value)) return value.forEach(collectSamples);
        if (!value || typeof value !== "object") return;
        if (value.sample_id && hasContent(value.title) && !samples.has(String(value.sample_id))) samples.set(String(value.sample_id), value.title);
        Object.values(value).forEach(collectSamples);
      };
      collectSamples([valueUpgrade.sample_evidence, result.performance_segments, result.transferable_formulas, overview.samples]);
      const metricLabels = {like_count: "点赞", comment_count: "评论", share_count: "分享", collect_count: "收藏", view_count: "播放", engagement_score: "综合互动分"};
      const detail = (value) => `<details class="report-source-detail"><summary>原始记录</summary><pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre></details>`;
      const sample = (value) => {
        if (Array.isArray(value)) return `<ul class="public-report-list">${value.filter(hasContent).map((item) => `<li>${sample(item)}</li>`).join("")}</ul>`;
        const item = typeof value === "string" ? {sample_id: value} : objectValue(value);
        const title = first(item.title, samples.get(String(item.sample_id))) || "样本名称未记录";
        const metric = metricLabels[item.metric] || item.metric_label;
        const amount = item.metric_value === null || item.metric_value === undefined || item.metric_value === "" ? "未采集" : formatNumber(item.metric_value);
        return `<strong>${escapeHtml(title)}</strong>${metric ? `<span class="report-sample-metric">${escapeHtml(metric)} ${escapeHtml(amount)}</span>` : ""}
          ${hasContent(item.reason) ? `<p>${escapeHtml(item.reason)}</p>` : ""}${item.sample_id ? detail(item) : ""}`;
      };
      const labels = {
        text: "", content: "", summary: "", description: "", question: "问题", name: "其他名称", title: "其他标题", formula: "方法", idea: "具体方案", sample_id: "支持样本", label: "", value: "", observation: "观察", interpretation: "解释（待验证）", explanation: "解释（待验证）",
        transfer: "可借鉴动作", execution: "具体动作", when_to_use: "适用情况", beat_structure: "步骤", beats: "步骤", structure: "结构", steps: "步骤",
        support: "支持样本", evidence: "支持依据", evidence_refs: "支持依据", uncertainty: "尚不能确认", risks: "需要注意", reason: "依据", why_it_works: "解释（待验证）",
        expected_metric_strength: "建议关注的指标", formula_used: "沿用的方法", why_worth_trying: "值得尝试的理由", production_requirements: "准备材料", input_material_needed: "所需素材",
        likely_strength: "预期优势（待验证）", low_confidence: "需要复核", validation: "验证建议", validation_rules: "验证建议", opening: "开头", opening_3s: "开头", hook: "吸引点", script: "脚本", shot_table: "拍摄结构",
        what_the_creator_sells: "内容定位", audience_promise: "内容承诺", hidden_genre: "呈现方式", audience_assumption: "观众假设（未验证）",
        assumptions: "观众假设（未验证）", tension_sources: "吸引力假设", detail_selection_rules: "细节选择", novelty_vs_familiarity: "熟悉与新鲜感",
        opening_hooks: "开头方式", scene_order: "呈现顺序", shot_types: "景别", subtitle_voice: "文字与声音相关描述（以证据限制为准）", visual_style: "视觉呈现", ending_patterns: "收尾方式",
        taste: "风格取舍", topic_selection_rules: "选题方法", structure_rules: "结构方法", expression_rules: "表达方法", visual_rules: "画面方法", caption_voice: "文案语气", ending_rules: "收尾方法",
        anti_patterns: "避免照搬", self_check_rubric: "执行自检", caption: "发布文案", title_options: "候选标题", hashtags: "话题", goal: "目标", action: "行动", result: "结果", outcome: "结果",
      };
      // Creator objects have explicit presentation fields. Unknown extensions remain available in details.
      const narrative = (value) => {
        if (!hasContent(value)) return "";
        if (Array.isArray(value)) return `<ul class="public-report-list">${value.filter(hasContent).map((item) => `<li>${narrative(item)}</li>`).join("")}</ul>`;
        if (typeof value !== "object") return escapeHtml(value);
        const titleKey = ["name", "title", "formula", "idea", "question"].find((key) => hasContent(value[key]));
        const title = value[titleKey];
        const fields = Object.entries(value).filter(([key, item]) => key !== titleKey && hasContent(item));
        const known = fields.filter(([key]) => Object.hasOwn(labels, key));
        const extra = Object.fromEntries(fields.filter(([key]) => !Object.hasOwn(labels, key)));
        return `${title ? `<h5>${escapeHtml(title)}</h5>` : ""}${known.map(([key, item]) => {
          const body = key === "sample_id" ? sample({sample_id: item}) : ["support", "evidence", "evidence_refs"].includes(key)
            ? evidence(item)
            : key === "beat_structure" && typeof item === "string" && item.includes("→")
              ? `<ol>${item.split("→").map((step) => `<li>${escapeHtml(step.trim())}</li>`).join("")}</ol>` : narrative(item);
          return `<div class="report-reading-field">${labels[key] ? `<span class="report-field-label">${labels[key]}</span>` : ""}<div>${body}</div></div>`;
        }).join("")}${Object.keys(extra).length ? detail(extra) : ""}`;
      };
      const evidence = (value) => {
        if (Array.isArray(value)) return `<ul class="public-report-list">${value.filter(hasContent).map((item) => `<li>${evidence(item)}</li>`).join("")}</ul>`;
        if (typeof value === "string") return /^sample_[\w-]+$/.test(value) || samples.has(value) ? sample(value) : escapeHtml(value);
        if (value && typeof value === "object" && value.sample_id) {
          const extra = Object.fromEntries(Object.entries(value).filter(([key]) => !["sample_id", "title", "metric", "metric_value", "metric_label", "reason", "evidence_level"].includes(key)));
          return sample(value) + narrative(extra);
        }
        return narrative(value);
      };
      const block = (label, value) => hasContent(value) ? `<section class="report-reading-block"><h4>${escapeHtml(label)}</h4>${narrative(value)}</section>` : "";
      const card = (id, title, body) => body.trim() ? `<section data-report-section="${id}">${renderPublicCard(title, body, "creator-reading-card")}</section>` : "";
      const groupMarkup = normalizeItems(result.content_groups).map((data) => {
        if (!data || typeof data !== "object") return "";
        const content = first(data.focused_analysis, data.patterns, data.summary, data.observations);
        const members = first(data.sample_ids, data.members);
        const count = data.count ?? data.sample_count;
        if (![content, members, data.uncertainty, count, data.analyzed_count, data.metadata_only_count, data.missing_analysis_count].some(hasContent)) return "";
        return `<section class="report-reading-block"><h4>${escapeHtml(data.label || data.content_category || data.category || "样本类型")}</h4>
          <p class="muted">${count !== undefined && count !== null ? `样本 ${escapeHtml(count)} · ` : ""}${data.analyzed_count !== undefined ? `已有分析：${escapeHtml(data.analyzed_count)} · ` : ""}${data.metadata_only_count !== undefined ? `仅元数据：${escapeHtml(data.metadata_only_count)}，不视为已验证的内容规律。` : ""}${data.missing_analysis_count !== undefined ? ` 缺少单条分析：${escapeHtml(data.missing_analysis_count)}` : ""}</p>
          ${narrative(content)}${block("尚不能确认", data.uncertainty)}${hasContent(members) ? `<details><summary>支持样本</summary>${sample(members)}</details>` : ""}</section>`;
      }).join("");
      const formulas = first(result.transferable_formulas, sections.formulas, strategy.templates, strategy.content_strategy);
      const ideas = first(result.candidate_ideas, execution.next_content_suggestions, sections.next_ideas, strategy.idea_bank);
      const examples = first(valueUpgrade.sample_evidence, Object.values(objectValue(result.performance_segments)).flat().filter((item) => item && typeof item === "object" && item.sample_id));
      const limits = unique(result.evidence_gaps, valueUpgrade.evidence_gaps, valueUpgrade.low_confidence_reasons, valueUpgrade.quality?.missing_evidence, valueUpgrade.quality?.warnings, result.report_quality?.missing_evidence, result.report_quality?.warnings, result.report_quality?.evidence_warnings);
      // Creator results do not persist an authoritative per-request manifest yet.
      // The Case manifest contract and model-written evidence fields cannot fill that historical gap.
      const inputNote = "<p>本次输入范围未完整记录。不能用当前素材库存推断模型当时看过哪些材料。</p>";
      const supplementary = `${block("策略要点", strategy.content_strategy)}${block("开头建议", strategy.hooks)}${block("模板", strategy.templates)}${block("补充选题", strategy.idea_bank)}${block("避免照搬", strategy.anti_patterns)}`;
      return `<section class="creator-distillation-report creator-reading-report" aria-label="创作者蒸馏核心报告">
        ${card("positioning", "1. 账号定位与本轮结论", `${hasContent(first(result.summary, viewModel.summary)) ? `<div class="public-analysis-hero">${narrative(first(result.summary, viewModel.summary))}</div>` : ""}
          ${hasContent(viewModel.headline) ? `<h3>${escapeHtml(viewModel.headline)}</h3>` : ""}${renderFocus(result)}${!hasContent(focus.primary) && templateLabel ? `<p>生成时方向：${escapeHtml(templateLabel)}</p>` : ""}
          ${narrative(first(positioning, strategy.positioning, sections.core_judgment?.fields))}${block("本轮观察", first(observation.bullets, sections.core_judgment?.bullets))}`)}
        ${card("patterns", "2. 核心规律与可复用结构", `${block("类型重点分析", result.focused_analysis)}${block("选题规律", result.topic_buckets)}
          ${block("内容组织", result.thinking_patterns)}${block("表达与呈现", result.expression_patterns)}${block("已有解释（待验证）", first(explanation.bullets, sections.traffic_sources?.hooks))}
          ${block("可复用方法", formulas)}${block("跨样本规律", sections.repeatable_patterns)}${groupMarkup ? `<details class="report-content-groups"><summary>按样本类型归纳</summary>${groupMarkup}</details>` : ""}
          ${hasContent(result.creator_clone_spec) ? `<details><summary>完整创作方法</summary>${narrative(result.creator_clone_spec)}</details>` : ""}
          ${supplementary ? `<details><summary>补充策略与模板</summary>${supplementary}</details>` : ""}`)}
        ${card("samples", "3. 代表样本对比", hasContent(examples) ? `<p class="muted">互动数据用于比较差异，不直接证明流量原因或转化效果。</p>${sample(examples)}` : "")}
        ${card("actions", "4. 下一条怎么做", `${block("具体行动", unique(first(result.next_actions, execution.bullets, sections.next_actions), hasContent(result.next_actions) ? execution.bullets : []))}
          ${block("候选选题与执行方式", ideas)}${block("验证建议", first(strategy.validation_rules, sections.checklist))}`)}
        ${card("limits", "5. 证据与限制", `${hasContent(limits) ? narrative(limits) : "<p>报告未单独记录证据限制；这不代表结论已经核验。</p>"}
          <section class="report-reading-block"><h4>本次生成的输入记录</h4>${inputNote}<p class="muted">已有单条分析、Map 或批次摘要属于二手材料，不等于本次直接查看原视频；其来源限制仍适用。</p></section>
          <details><summary>当前已归档素材与结构检查</summary>${renderQualitySummary({...valueUpgrade, quality: first(valueUpgrade.quality, result.report_quality) || {}})}<p>素材库存不等于本次输入，也不代表已被模型理解。</p></details>`)}
        <details class="creator-report-evidence-details"><summary>完整材料与技术详情</summary>${renderEvidenceDetails(overview, result, viewModel)}</details>
      </section>`;
    }

    function hasReport(container) {
      if (!container) {
        return false;
      }
      if (typeof container.querySelector === "function") {
        return Boolean(container.querySelector(".creator-distillation-report"));
      }
      return String(container.innerHTML || "").includes("creator-distillation-report");
    }

    function clear(container) {
      if (!container) {
        return false;
      }
      container.innerHTML = "";
      return true;
    }

    function showFailure(container, message = "报告已生成，但首次渲染失败。请稍后重试或刷新页面恢复完整报告。") {
      if (!container) {
        return false;
      }
      if (hasReport(container)) {
        container.innerHTML += `<p role="status">${escapeHtml(message)} 上次可用报告已保留。</p>`;
        return true;
      }
      container.innerHTML = `
        <section class="public-analysis-hero">
          <span>REPORT_RENDER_FAILED</span>
          <strong>${escapeHtml(message)}</strong>
        </section>
      `;
      return true;
    }

    function render({container, result, overview, templateLabel = "", viewModel, consoleRef = global.console} = {}) {
      if (!container) {
        return false;
      }
      try {
        container.innerHTML = renderReportMarkup({result, overview, templateLabel, viewModel});
        if (!hasReport(container)) {
          throw new Error("蒸馏报告节点未生成。");
        }
        return true;
      } catch (error) {
        consoleRef?.error?.("Creator report render failed", error);
        showFailure(container);
        return false;
      }
    }

    return Object.freeze({
      render,
      renderReportMarkup,
      renderSummary,
      hasReport,
      clear,
      showFailure,
    });
  }

  global.CreatorReportView = Object.freeze({createRenderer, hasContent, renderValue, renderFocus, renderFocusedAnalysis, renderSections});
})(window);
