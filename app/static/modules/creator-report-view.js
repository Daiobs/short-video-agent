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
      ${hasContent(focus.reason) ? `<p>判断依据：${renderValue(focus.reason)}</p>` : ""}
      ${hasContent(focus.initial_category) ? `<p>自动初判：${renderValue(directionLabel(focus.initial_category))}</p>` : ""}
      ${hasContent(focus.auxiliary) ? `<details><summary>辅助视角</summary>${renderValue(directionLabel(focus.auxiliary))}</details>` : ""}
      ${hasReview ? `<section aria-label="模型复核建议"><h4>模型复核建议（未自动切换）</h4>
        ${hasContent(review.suggested_category) ? `<p>建议方向：${renderValue(directionLabel(review.suggested_category))}</p>` : ""}
        ${hasContent(review.reason) ? `<p>复核依据：${renderValue(review.reason)}</p>` : ""}
        <p>此建议不改变本次报告采用的方向，也不会自动重新分析。</p></section>` : ""}
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
            <article><span>质量判断</span><strong>${escapeHtml(diagnostics.quality_label || qualityLabelFromScore(score))}${score !== undefined && score !== null ? ` · ${formatNumber(score)}/100` : ""}</strong></article>
            <article class="wide"><span>证据覆盖</span><strong>${escapeHtml(diagnostics.coverage_text || "暂无证据覆盖统计")}</strong></article>
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
          ${score !== undefined ? `<p><strong>报告质量：</strong>${formatNumber(score)} / 100</p>` : ""}
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
      const positioningText = viewModel.headline || strategy.positioning || positioning.what_the_creator_sells || result.summary || "待补充";
      const observation = objectValue(valueUpgrade.observation);
      const explanation = objectValue(valueUpgrade.explanation);
      const execution = objectValue(valueUpgrade.execution);
      const repeatablePatterns = normalizeItems(sections.repeatable_patterns).slice(0, 6);
      const focus = objectValue(result.analysis_focus);
      const focused = renderFocusedAnalysis(result.focused_analysis);
      if (hasContent(focus.primary) || hasContent(focus.label) || focused || hasContent(result.content_groups)) {
        const groups = Array.isArray(result.content_groups) ? result.content_groups : [];
        const groupMarkup = groups.map((group) => {
          const data = objectValue(group);
          const body = renderFocusedAnalysis(data.focused_analysis) || renderValue(data.patterns || data.summary || data.observations);
          const members = data.sample_ids || data.members;
          if (!body && !hasContent(members)) return "";
          return `<section style="min-width:0;overflow-wrap:anywhere"><h4>${escapeHtml(data.label || data.content_category || data.category || "样本类型")}</h4>
            ${data.count !== undefined || data.sample_count !== undefined ? `<p>样本数：${escapeHtml(data.count ?? data.sample_count ?? "未记录")}</p>` : ""}
            ${data.analyzed_count !== undefined ? `<p>已有分析：${escapeHtml(data.analyzed_count)}</p>` : ""}
            ${data.metadata_only_count !== undefined ? `<p>仅元数据：${escapeHtml(data.metadata_only_count)}，不视为已验证的内容规律。</p>` : ""}
            ${hasContent(members) ? `<details><summary>支持样本</summary>${renderValue(members)}</details>` : ""}
            ${body}${hasContent(data.uncertainty) ? `<p>适用边界：${renderValue(data.uncertainty)}</p>` : ""}</section>`;
        }).join("");
        const contentSections = [
          {key: "focused_analysis", label: "类型重点分析", value: focused, html: focused},
          {key: "content_groups", label: "按样本类型归纳", value: groupMarkup, html: groupMarkup},
          {key: "creator_positioning", label: "账号定位", value: result.creator_positioning},
          {key: "topic_buckets", label: "选题规律", value: result.topic_buckets},
          {key: "thinking_patterns", aliases: ["script_structure", "emotion_path"], label: "思维与论证", value: result.thinking_patterns},
          {key: "expression_patterns", aliases: ["visual_analysis", "first_3_seconds", "timeline"], label: "表达与视觉", value: result.expression_patterns},
          {key: "transferable_formulas", aliases: ["replication"], label: "可迁移结构", value: result.transferable_formulas || sections.formulas},
          {key: "creator_clone_spec", label: "创作方法", value: result.creator_clone_spec},
          {key: "observation", label: "观察", value: observation.bullets || sections.core_judgment?.bullets},
          {key: "explanation", label: "解释", value: explanation.bullets || sections.traffic_sources?.hooks},
          {key: "execution", label: "下一步", value: execution.bullets || sections.next_actions},
          {key: "next_actions", label: "行动建议", value: result.next_actions},
          {key: "candidate_ideas", label: "下一条内容", value: result.candidate_ideas || execution.next_content_suggestions || sections.next_ideas},
          {key: "sample_evidence", label: "样本证据", value: valueUpgrade.sample_evidence},
          {key: "repeatable_patterns", label: "跨形式共性", value: repeatablePatterns},
          {key: "evidence_gaps", label: "证据与适用边界", value: result.evidence_gaps || valueUpgrade.evidence_gaps},
        ];
        return `<section class="creator-distillation-report" aria-label="创作者蒸馏核心报告" style="min-width:0;overflow-wrap:anywhere">
          ${hasContent(result.summary) ? `<section class="public-analysis-hero">${renderSummary(result.summary)}</section>` : ""}
          ${renderFocus(result)}
          ${renderSections(focus, contentSections)}
          ${renderQualitySummary(valueUpgrade)}
          ${renderEvidenceDetails(overview, result, viewModel)}
        </section>`;
      }
      const executionBody = `
        ${renderPublicList(execution.bullets || sections.next_actions, "先从最高互动样本中选 3 条，人工复核开头、封面、动作和标题，再生成候选脚本。")}
        <h5>下一条内容建议</h5>
        ${renderPublicList(execution.next_content_suggestions || sections.next_ideas, "本次没有返回独立选题库，可先基于爆款共性手动生成候选选题。")}
      `;
      return `
        <section class="public-analysis-hero">
          <span>${escapeHtml(`样本 ${overview.selected_count || 0}/${overview.sample_count || 0} · ${overview.confidence || "unknown"} · ${templateLabel || "自动判断"}`)}</span>
          ${renderSummary(result.summary || "创作者蒸馏完成。")}
        </section>
        <section class="creator-distillation-report" aria-label="创作者蒸馏核心报告">
          ${renderFocus(result)}
          ${renderHero({viewModel, result, overview, templateLabel, positioningText})}
          <div class="public-report-grid creator-distillation-grid creator-decision-grid">
            ${renderPublicCard("1. 观察：这个账号做了什么", `
              ${renderPublicFields([
                ["定位", positioningText],
                ["观众承诺", positioning.audience_promise],
                ["隐藏类型", positioning.hidden_genre],
                ["观众假设", positioning.audience_assumption],
              ])}
              <h5>稳定出现的内容动作</h5>
              ${renderPublicList(observation.bullets || sections.core_judgment?.bullets, "暂无观察结论。")}
            `, "featured wide")}
            ${renderPublicCard("2. 解释：为什么这些内容有效", `
              ${renderPublicList(explanation.bullets || sections.traffic_sources?.hooks, "暂无解释结论。")}
              <h5>样本证据</h5>
              ${renderSampleEvidence(valueUpgrade.sample_evidence)}
            `, "featured")}
            ${renderPublicCard("3. 执行：下一条怎么拍 / 怎么写 / 怎么验证", executionBody, "featured")}
            ${renderPublicCard("4. 可复刻结构：保留有效动作，替换具体素材", `
              ${renderPublicList(sections.formulas, "本次没有返回独立公式，建议先从高互动样本中人工提炼 2-3 个可复用拍法。")}
              <h5>共性创作要素</h5>
              ${renderPublicList(repeatablePatterns, "暂无稳定共性。")}
            `)}
            ${renderPublicCard("5. 置信度与证据缺口", `${renderLowConfidence(valueUpgrade)}${renderQualitySummary(valueUpgrade)}`)}
          </div>
          ${renderEvidenceDetails(overview, result, viewModel)}
        </section>
      `;
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
