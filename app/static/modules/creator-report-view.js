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
      const strategy = objectValue(hasContent(result.creator_clone_strategy) ? result.creator_clone_strategy : result.creator_strategy);
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
      const viewModel = objectValue(rawViewModel || result.creator_report_view_model);
      const strategy = objectValue(hasContent(result.creator_clone_strategy) ? result.creator_clone_strategy : result.creator_strategy);
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
      const referenceManifest = objectValue(result.reference_manifest || viewModel.reference_manifest);
      const hasReferenceManifest = referenceManifest.version === 1 && Array.isArray(referenceManifest.samples);
      const sampleRows = hasReferenceManifest ? referenceManifest.samples : [
        ...(Array.isArray(overview.samples) ? overview.samples : []),
        ...(Array.isArray(valueUpgrade.sample_evidence) ? valueUpgrade.sample_evidence : []),
      ];
      const sampleRecords = new Map();
      const caseAliases = new Map();
      sampleRows.forEach((row, index) => {
        if (!row || typeof row.sample_id !== "string" || !/^[A-Za-z0-9_-]{1,160}$/.test(row.sample_id)) return;
        const record = {...row, label: row.title && row.title !== "样本名称未记录" ? row.title : `样本 ${index + 1}（名称未记录）`};
        sampleRecords.set(row.sample_id, record);
        if (typeof row.case_id === "string" && /^case_[A-Za-z0-9_-]+$/.test(row.case_id)) {
          if (!caseAliases.has(row.case_id)) caseAliases.set(row.case_id, new Map());
          caseAliases.get(row.case_id).set(row.sample_id, record);
        }
      });
      caseAliases.forEach((records, id) => {
        if (records.size === 1 && !sampleRecords.has(id)) sampleRecords.set(id, records.values().next().value);
      });
      const samples = new Map([...sampleRecords].map(([id, row]) => [id, row.label]));
      const objectPaths = new WeakMap();
      const recordPaths = (value, path) => {
        if (!value || typeof value !== "object") return;
        objectPaths.set(value, path);
        Object.entries(value).forEach(([key, entry]) => recordPaths(entry, Array.isArray(value) ? `${path}[${key}]` : path ? `${path}.${key}` : key));
      };
      recordPaths(result, "");
      const referenceEntries = Array.isArray(referenceManifest.entries) ? referenceManifest.entries : [];
      const referenceKeys = ["sample_id", "case_id", "aweme_id", "support", "supporting_samples", "sample_ids", "references", "evidence", "evidence_refs", "basis"];
      const inlineIds = /\b(?:sample_|case_)[A-Za-z0-9_-]+\b/g;
      const safeCaseUrl = (row) => typeof row?.open_url === "string" && /^\/cases\/case_[A-Za-z0-9_-]+$/.test(row.open_url) && row.open_url === `/cases/${row.case_id}` ? row.open_url : "";
      const referenceLabel = (id) => {
        const row = sampleRecords.get(String(id));
        if (!row) return '<span class="report-reference-warning">引用无法定位，需复核</span>';
        const url = safeCaseUrl(row);
        return url ? `<a href="${escapeHtml(url)}">${escapeHtml(row.label)}</a>` : escapeHtml(row.label);
      };
      const readableText = (value) => {
        const text = String(value ?? "");
        let cursor = 0, html = "";
        for (const match of text.matchAll(inlineIds)) {
          html += escapeHtml(text.slice(cursor, match.index)) + referenceLabel(match[0]);
          cursor = match.index + match[0].length;
        }
        return html + escapeHtml(text.slice(cursor));
      };
      const itemReferences = (value) => {
        const path = value && typeof value === "object" ? objectPaths.get(value) : undefined;
        const entries = path ? referenceEntries.filter((entry) => typeof entry.path === "string" &&
          (entry.path === path || entry.path.startsWith(`${path}.`) || entry.path.startsWith(`${path}[`))) : [];
        const valid = new Set(), invalid = new Set();
        entries.forEach((entry) => {
          (Array.isArray(entry.valid_sample_ids) ? entry.valid_sample_ids : []).forEach((id) => sampleRecords.has(id) ? valid.add(id) : invalid.add(id));
          (Array.isArray(entry.invalid_refs) ? entry.invalid_refs : []).forEach((id) => invalid.add(id));
        });
        // Compatibility rendering never invents identity from a model-provided title.
        const collect = (entry, isReference = false) => {
          if (Array.isArray(entry)) return entry.forEach((part) => collect(part, isReference));
          if (entry && typeof entry === "object") return Object.entries(entry).forEach(([key, part]) => collect(part, referenceKeys.includes(key)));
          if (typeof entry !== "string") return;
          const ids = [...entry.matchAll(inlineIds)].map((match) => match[0]);
          if (isReference && sampleRecords.has(entry)) ids.push(entry);
          ids.forEach((id) => sampleRecords.has(id) ? valid.add(sampleRecords.get(id).sample_id) : invalid.add(id));
        };
        collect(value);
        return {valid: [...valid], invalid: [...invalid]};
      };
      const referenceNote = (value, empty = false) => {
        const refs = itemReferences(value);
        return `${refs.valid.length ? `<p class="report-source-note">参考样本：${refs.valid.map(referenceLabel).join("、")}；未提供具体片段定位。引用可定位不代表结论已验证。</p>` : ""}${refs.invalid.length ? '<p class="report-reference-warning">引用无法定位，需复核。</p>' : ""}${!refs.valid.length && !refs.invalid.length && empty ? '<p class="report-source-note">此条未单列支持依据。</p>' : ""}`;
      };
      const metricLabels = {like_count: "点赞", comment_count: "评论", share_count: "分享", collect_count: "收藏", view_count: "播放", engagement_score: "综合互动分"};
      const detail = (value) => `<details class="report-source-detail"><summary>原始记录</summary><pre>${escapeHtml(JSON.stringify(value, (key, entry) => key === "request_evidence" ? undefined : entry, 2))}</pre></details>`;
      const sample = (value) => {
        if (Array.isArray(value)) return `<ul class="public-report-list">${value.filter(hasContent).map((item) => `<li>${sample(item)}</li>`).join("")}</ul>`;
        const item = typeof value === "string" ? {sample_id: value} : objectValue(value);
        const id = item.sample_id || item.case_id || item.aweme_id;
        const metric = metricLabels[item.metric] || item.metric_label;
        const amount = item.metric_value === null || item.metric_value === undefined || item.metric_value === "" ? "未采集" : formatNumber(item.metric_value);
        return `<strong>${referenceLabel(id)}</strong>${metric ? `<span class="report-sample-metric">${escapeHtml(metric)} ${escapeHtml(amount)}</span>` : ""}
          ${hasContent(item.reason) ? `<p>${readableText(item.reason)}</p>` : ""}${id ? detail(item) : ""}`;
      };
      const labels = {
        text: "", content: "", summary: "", description: "", question: "问题", name: "其他名称", title: "其他标题", formula: "方法", idea: "具体方案", sample_id: "支持样本", label: "", value: "", observation: "观察", interpretation: "解释（待验证）", explanation: "解释（待验证）",
        transfer: "可借鉴动作", execution: "具体动作", when_to_use: "适用情况", beat_structure: "步骤", beats: "步骤", structure: "结构", steps: "步骤",
        support: "支持样本", supporting_samples: "参考样本", basis: "依据", evidence: "支持依据", evidence_refs: "支持依据", uncertainty: "尚不能确认", risks: "需要注意", reason: "依据", why_it_works: "解释（待验证）",
        applicable_formats: "适用形式", validation_action: "验证动作", effect_hypothesis: "效果假设（待验证）", format: "呈现形式", test: "验证方法", confidence: "模型自评", model_confidence: "模型自评", evidence_level: "材料标注", metrics: "记录指标", pattern: "呈现规律", example: "具体例子", note: "说明与限制",
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
        if (typeof value === "string" && /^[\[{]/.test(value.trim())) {
          try {
            const decoded = JSON.parse(value);
            if (decoded && typeof decoded === "object") return narrative(decoded);
          } catch (_) { /* Historical prose that is not JSON remains prose. */ }
        }
        if (Array.isArray(value)) return `<ul class="public-report-list">${value.filter(hasContent).map((item) => `<li>${narrative(item)}</li>`).join("")}</ul>`;
        if (typeof value !== "object") return readableText(value);
        const titleKey = ["name", "title", "formula", "idea", "question"].find((key) => hasContent(value[key]));
        const title = value[titleKey];
        const fields = Object.entries(value).filter(([key, item]) => key !== titleKey && hasContent(item));
        const known = fields.filter(([key]) => Object.hasOwn(labels, key));
        const extra = Object.fromEntries(fields.filter(([key]) => !Object.hasOwn(labels, key)));
        return `${title ? `<h5>${readableText(title)}</h5>` : ""}${known.map(([key, item]) => {
          if (["confidence", "model_confidence", "evidence_level"].includes(key)) {
            const level = {high: "较高", medium: "中等", low: "较低"}[item];
            const meaning = key === "evidence_level" ? `材料标注${level || "未明确"}，不代表本次实际使用或结论核验。` : `模型自评${level || "未明确"}，不是事实准确率。`;
            return `<details class="report-level-detail"><summary>${labels[key]}说明</summary><p>${meaning}</p>${detail({[key]: item})}</details>`;
          }
          const body = key === "sample_id" ? sample({sample_id: item}) : referenceKeys.includes(key)
            ? evidence(item)
            : key === "metrics" ? `<dl class="report-sample-metrics">${Object.entries(objectValue(item)).filter(([metric]) => Object.hasOwn(metricLabels, metric)).map(([metric, amount]) => `<div><dt>${metricLabels[metric]}</dt><dd>${amount === null ? "未采集" : escapeHtml(formatNumber(amount))}</dd></div>`).join("")}</dl>${detail(item)}`
            : key === "beat_structure" && typeof item === "string" && item.includes("→")
              ? `<ol>${item.split("→").map((step) => `<li>${readableText(step.trim())}</li>`).join("")}</ol>` : narrative(item);
          return `<div class="report-reading-field">${labels[key] ? `<span class="report-field-label">${labels[key]}</span>` : ""}<div>${body}</div></div>`;
        }).join("")}${referenceNote(value)}${Object.keys(extra).length ? detail(extra) : ""}`;
      };
      const evidence = (value) => {
        if (Array.isArray(value)) return `<ul class="public-report-list">${value.filter(hasContent).map((item) => `<li>${evidence(item)}</li>`).join("")}</ul>`;
        if (typeof value === "string") return /^(?:sample_|case_)[\w-]+$/.test(value) || samples.has(value) ? sample(value) : readableText(value);
        if (value && typeof value === "object" && value.sample_id) {
          const extra = Object.fromEntries(Object.entries(value).filter(([key]) => !["sample_id", "title", "metric", "metric_value", "metric_label", "reason", "evidence_level"].includes(key)));
          return sample(value) + narrative(extra);
        }
        return narrative(value);
      };
      const block = (label, value) => hasContent(value) ? `<section class="report-reading-block"><h4>${escapeHtml(label)}</h4>${narrative(value)}</section>` : "";
      const card = (id, title, body) => body.trim() ? `<section ${id === "actions" ? 'id="creator-report-priority-actions" tabindex="-1" ' : ""}data-report-section="${id}" class="creator-reading-section"><h3>${escapeHtml(title)}</h3>${body}</section>` : "";
      const items = (value) => Array.isArray(value) ? value.filter(hasContent) : hasContent(value) ? [value] : [];
      const textKey = (value) => typeof value === "string" ? value.trim().replace(/\s+/g, " ") : JSON.stringify(value);
      const distinct = (values) => [...new Map(values.filter(hasContent).map((value) => [textKey(value), value])).values()];
      const compactText = (value) => {
        if (typeof value === "string" && /^[\[{]/.test(value.trim())) {
          try {
            const decoded = JSON.parse(value);
            if (decoded && typeof decoded === "object") return narrative(decoded);
          } catch (_) { /* Do not split serialized legacy objects before decoding them. */ }
        }
        if (typeof value !== "string" || value.length <= 160) return narrative(value);
        // Split at a sentence boundary, with every remaining character retained behind a native disclosure.
        const end = value.search(/[。！？.!?](?:\s|$|[^\x00-\x7F])/);
        let prefixLength = end < 0 ? Array.from(value).slice(0, 160).join("").length : end + 1;
        for (const match of value.matchAll(inlineIds)) {
          if (match.index < prefixLength && match.index + match[0].length > prefixLength) prefixLength = match.index + match[0].length;
        }
        return `${narrative(value.slice(0, prefixLength))}<details class="report-long-copy"><summary>展开全文</summary>${narrative(value.slice(prefixLength))}</details>`;
      };
      const sourceNote = (item, origin) => {
        const source = origin;
        return ["local_fallback", "generic_fallback", "local_generic", "fallback"].includes(source)
          ? "通用参考建议 · 本地预设，不是账号规律"
          : source === "model" ? "本轮模型分析 · 解释与创意仍需验证"
          : source === "deterministic" ? "本地数据整理，不是因果判断"
          : "来源未区分；创意与解释仍需验证";
      };
      const component = (kind, value, origin, showSource = true) => {
        const item = objectValue(value);
        const titleKey = ["name", "title", "formula", "idea", "question"].find((key) => hasContent(item[key]));
        const fields = kind === "formula"
          ? ["text", "when_to_use", "beat_structure", "steps", "structure", "observation", "interpretation", "execution", "applicable_formats", "support", "supporting_samples", "evidence", "basis", "validation_action", "risks", "uncertainty"]
          : kind === "idea"
            ? ["text", "opening_3s", "idea", "action", "formula_used", "why_worth_trying", "production_requirements", "format", "basis", "evidence", "effect_hypothesis", "test", "validation", "risks"]
            : ["observation", "pattern", "example", "note", "interpretation", "transfer", "evidence", "uncertainty"];
        const selected = Object.fromEntries(fields.filter((key) => key !== titleKey && hasContent(item[key])).map((key) => [key, item[key]]));
        const extra = Object.fromEntries(Object.entries(item).filter(([key]) => key !== titleKey && !fields.includes(key)));
        if (kind === "finding" && typeof value === "object") {
          const primary = ["observation", "pattern", "transfer", "example", "note", "uncertainty"].filter((key) => hasContent(item[key])).map((key) =>
            `<div class="report-reading-field"><span class="report-field-label">${escapeHtml(labels[key])}</span><div>${key === "uncertainty" ? narrative(item[key]) : compactText(item[key])}</div></div>`).join("");
          const reasoning = `${hasContent(item.interpretation) ? block("解释（待验证）", item.interpretation) : ""}${hasContent(item.evidence) ? `<div class="report-reading-field"><span class="report-field-label">完整支持依据</span><div>${evidence(item.evidence)}</div></div>` : ""}${Object.keys(extra).length ? detail(extra) : ""}`;
          const hasWrittenEvidence = referenceKeys.some((key) => hasContent(item[key]));
          return `<article class="report-finding-card">${titleKey ? `<h4>${readableText(item[titleKey])}</h4>` : ""}${primary}${referenceNote(item, !hasWrittenEvidence)}${hasWrittenEvidence && !itemReferences(item).valid.length && !itemReferences(item).invalid.length ? '<p class="report-source-note">已记录支持依据，详见判断依据与适用限制。</p>' : ""}${reasoning ? `<details><summary>判断依据与适用限制</summary>${reasoning}</details>` : ""}</article>`;
        }
        const fieldMarkup = Object.entries(selected).map(([key, entry]) => `<div class="report-reading-field"><span class="report-field-label">${escapeHtml(labels[key] || "")}</span><div>${referenceKeys.includes(key) ? evidence(entry) : compactText(entry)}</div></div>`).join("") + (Object.keys(extra).length ? detail(extra) : "");
        const body = typeof value === "string" ? compactText(value) : `${titleKey ? `<h4>${readableText(item[titleKey])}</h4>` : ""}${kind === "idea" && titleKey && fieldMarkup ? `<details><summary>选题依据与完整执行方案</summary>${fieldMarkup}</details>` : fieldMarkup}`;
        return `<article class="report-${kind}-card">${body}${referenceNote(value, kind === "finding")}${kind !== "finding" && showSource ? `<p class="report-source-note">${sourceNote(item, origin)}</p>` : ""}</article>`;
      };
      const highlights = (value, renderItem, label = "查看其余内容", limit = 3) => {
        const all = distinct(items(value));
        return all.slice(0, limit).map(renderItem).join("") + (all.length > limit ? `<details class="report-more"><summary>${label}（${all.length - limit}）</summary>${all.slice(limit).map(renderItem).join("")}</details>` : "");
      };
      const fieldOrigins = objectValue(objectValue(result.report_provenance || viewModel.report_provenance).fields);
      const originFor = (path) => fieldOrigins[path] || fieldOrigins[path.split(".")[0]];
      const choose = (...choices) => choices.find(([value]) => hasContent(value)) || [[], undefined];
      const sourcedHighlights = ([value, origin], kind, label, limit = 3) => {
        const generic = [], primary = [];
        items(value).forEach((item, index) => {
          const source = Array.isArray(origin) ? origin[index] : origin;
          const entry = {item, source};
          (["fallback", "local_fallback", "generic_fallback", "local_generic"].includes(source) ? generic : primary).push(entry);
        });
        const uniform = new Set(primary.map(({source}) => source || "unknown")).size === 1;
        const renderItem = ({item, source}) => kind === "action"
          ? `<article class="report-action-card">${compactText(item)}${uniform ? "" : `<p class="report-source-note">${sourceNote(item, source)}</p>`}</article>`
          : component(kind, item, source, !uniform);
        return highlights(primary, renderItem, label, limit) + (uniform ? `<p class="report-source-note">${sourceNote(primary[0].item, primary[0].source)}</p>` : "") + (generic.length ? `<details class="report-generic-advice"><summary>通用参考建议（本地预设）</summary><p>通用参考建议 · 本地预设，不是账号规律</p>${generic.map(({item, source}) => component(kind, item, source, false)).join("")}</details>` : "");
      };
      const safeLink = (value) => {
        if (typeof value !== "string" || /[\s\\]/.test(value)) return "";
        return /^https?:\/\//i.test(value) || /^\/(?!\/)/.test(value) ? value : "";
      };
      const mergedSamples = () => {
        const records = [...items(valueUpgrade.sample_evidence), ...Object.values(objectValue(result.performance_segments)).flatMap(items)];
        const merged = new Map();
        records.forEach((record, index) => {
          if (!record || typeof record !== "object") return;
          if (hasReferenceManifest && !sampleRecords.has(String(record.sample_id))) return;
          const key = hasContent(record.sample_id) ? String(record.sample_id) : `unidentified-${index}`;
          if (!merged.has(key)) merged.set(key, []);
          merged.get(key).push(record);
        });
        return [...merged.values()].map((records) => {
          const title = first(samples.get(String(records[0].sample_id)), ...records.map((r) => r.title)) || "样本名称未记录";
          const metrics = Object.entries(metricLabels).map(([key, label]) => {
            const values = distinct(records.flatMap((r) => [r[key], objectValue(r.metrics)[key], ...(r.metric === key || (!r.metric && r.metric_label === label) ? [r.metric_value] : [])]));
            return `<div><dt>${label}</dt><dd>${values.length ? values.map((v) => escapeHtml(formatNumber(v))).join(" / ") : "未采集"}${values.length > 1 ? '<small>记录冲突，见原始来源</small>' : ""}</dd></div>`;
          }).join("");
          const url = hasReferenceManifest ? "" : records.map((r) => safeLink(r.url || r.source_url || r.open_url)).find(Boolean);
          const trustedRecord = sampleRecords.get(String(records[0].sample_id));
          const caseId = hasReferenceManifest ? (safeCaseUrl(trustedRecord) ? trustedRecord.case_id : "") : records.map((r) => r.case_id).find((id) => typeof id === "string" && /^case_[a-zA-Z0-9_-]+$/.test(id));
          return `<article class="report-sample-card"><h4>${escapeHtml(title)}</h4><dl class="report-sample-metrics">${metrics}</dl><p class="report-source-note">当前样本中的相对代表；指标排名不证明内容效果的原因。</p>${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">查看作品</a>` : ""}${caseId ? ` <a href="/cases/${encodeURIComponent(caseId)}">查看 Case</a>` : ""}<details><summary>原始排名与来源记录</summary><p>本地排名整理；历史 reason 中的通用解释不是模型结论。冲突值保留各自原记录，不合并为单一事实。</p>${detail(records)}</details></article>`;
        });
      };
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
      const sectionSources = Object.fromEntries(Object.entries(objectValue(viewModel.sources)).map(([key, value]) => [key.replace(/^sections\./, ""), value]));
      const upgradeSources = objectValue(valueUpgrade.sources);
      const formulas = choose([result.transferable_formulas, originFor("transferable_formulas")], [sections.formulas, sectionSources.formulas], [strategy.templates, originFor("creator_clone_strategy.templates")], [strategy.content_strategy, originFor("creator_clone_strategy.content_strategy")]);
      const ideas = choose([result.candidate_ideas, originFor("candidate_ideas")], [execution.next_content_suggestions, upgradeSources.next_content_suggestions], [sections.next_ideas, sectionSources.next_ideas], [strategy.idea_bank, originFor("creator_clone_strategy.idea_bank")]);
      const limits = unique(result.evidence_gaps, valueUpgrade.evidence_gaps, valueUpgrade.low_confidence_reasons, valueUpgrade.quality?.missing_evidence, valueUpgrade.quality?.warnings, result.report_quality?.missing_evidence, result.report_quality?.warnings, result.report_quality?.evidence_warnings);
      const requestInput = () => {
        const manifest = objectValue(result.request_evidence);
        if (manifest.version !== 1 || manifest.source !== "actual_request" || manifest.final_attempt !== true) {
          return "<p>本次输入范围未完整记录。不能用当前素材库存推断模型当时看过哪些材料。</p>";
        }
        const submitted = new Map();
        items(manifest.samples).forEach((row) => {
          if (!row || typeof row.sample_id !== "string" || !row.sample_id.trim()) return;
          if (!submitted.has(row.sample_id)) submitted.set(row.sample_id, {kinds: new Set(), orders: new Set(), truncated: false});
          const entry = submitted.get(row.sample_id);
          items(row.materials).forEach((material) => {
            if (["asr", "ocr", "comments", "prior_analysis"].includes(material?.kind)) entry.kinds.add(material.kind);
            if (material?.truncated === true) entry.truncated = true;
          });
          items(row.image_orders).filter((order) => Number.isInteger(order) && order > 0).forEach((order) => entry.orders.add(order));
          if (row.truncated === true) entry.truncated = true;
        });
        const rows = [...submitted.entries()];
        const kinds = {asr: "转录", ocr: "OCR", comments: "评论", prior_analysis: "已有分析（二手）"};
        const counts = Object.entries(kinds).map(([kind, label]) => `${label} ${rows.filter(([, row]) => row.kinds.has(kind)).length} 条样本`).join(" · ");
        const direct = rows.filter(([, row]) => row.orders.size);
        const images = new Set(direct.flatMap(([, row]) => [...row.orders]));
        const truncated = rows.filter(([, row]) => row.truncated).length;
        return `<div class="report-submitted-input"><p>最终成功请求${Number.isInteger(manifest.attempt) ? ` · 尝试 ${manifest.attempt}` : ""}${manifest.degraded === true ? " · 使用降级输入" : ""}</p>
          <p>本次提交 ${rows.length} 条样本；直接图片 ${images.size} 张，覆盖 ${direct.length} 条样本；${rows.length - direct.length} 条未直接查看图片。</p>
          <p>${counts}</p><p>${truncated ? `${truncated} 条样本的输入短摘有截短。` : "未记录样本短摘截短。"}${manifest.structured_rows_found !== true ? " 未识别完整结构化正文，文本覆盖仍有未知。" : ""}</p>
          <details><summary>本次提交的样本与图片对应</summary>${rows.map(([id, row]) => `<div class="report-reading-block"><h5>${escapeHtml(samples.get(id) || "样本名称未记录")}</h5><p>${row.orders.size ? `直接图片序号：${[...row.orders].join("、")}` : "未直接查看图片"}；${[...row.kinds].map((kind) => kinds[kind]).join("、") || "未记录有效文本短摘"}${row.truncated ? "；输入有截短" : ""}</p>${detail({sample_id: id})}</div>`).join("")}</details>
        </div>`;
      };
      const inputNote = requestInput();
      const supplementary = `${block("策略要点", strategy.content_strategy)}${block("开头建议", strategy.hooks)}${block("模板", strategy.templates)}${block("补充选题", strategy.idea_bank)}${block("避免照搬", strategy.anti_patterns)}`;
      const lead = first(result.summary, viewModel.summary, viewModel.headline, positioning, strategy.positioning, sections.core_judgment?.fields);
      const thinkingFindings = Array.isArray(result.thinking_patterns) ? result.thinking_patterns
        : Object.entries(objectValue(result.thinking_patterns)).flatMap(([key, value]) => items(value).map((entry) =>
          typeof entry === "string" ? {question: labels[key] || "内容组织", observation: entry} : entry));
      // Prefer original structured patterns over the VM's lossy text flattening.
      const expression = objectValue(result.expression_patterns);
      const expressionFindings = distinct(["visual_style", "shot_types", "scene_order", "opening_hooks", "subtitle_voice", "ending_patterns"].flatMap((key) => items(expression[key])));
      const findings = choose([result.focused_analysis, originFor("focused_analysis")], [thinkingFindings, originFor("thinking_patterns")], [expressionFindings, originFor("expression_patterns")], [sections.repeatable_patterns, sectionSources.repeatable_patterns], [explanation.bullets, upgradeSources.explanation], [sections.traffic_sources?.hooks, sectionSources["traffic_sources.hooks"]]);
      const actions = choose([result.next_actions, originFor("next_actions")], [execution.bullets, upgradeSources.execution], [sections.next_actions, sectionSources.next_actions]);
      return `<section class="creator-distillation-report creator-reading-report" aria-label="创作者蒸馏核心报告">
        ${card("positioning", "账号定位与本轮结论", `${compactText(lead)}${hasContent(actions[0]) || hasContent(ideas[0]) ? '<a class="report-priority-action-link" data-report-action-jump href="#creator-report-priority-actions">先看下一条怎么做 ↓</a>' : ""}${renderFocus(result)}${!hasContent(focus.primary) && templateLabel ? `<p>生成时方向：${escapeHtml(templateLabel)}</p>` : ""}`)}
        <div class="report-reading-row">
        ${card("patterns", "核心规律与可复用结构", sourcedHighlights(findings, "finding", "查看其余判断", 2))}
        ${card("actions", "下一条怎么做", `${sourcedHighlights(actions, "action", "查看其余行动")}${hasContent(ideas[0]) ? `<h4>候选选题与执行方式</h4>${sourcedHighlights(ideas, "idea", "查看其余选题", 2)}` : ""}`)}
        </div>
        <div class="report-reading-row">
        ${card("samples", "代表样本对比", highlights(mergedSamples(), (html) => html, "查看其余样本", 2))}
        ${card("formulas", "可复用结构与适用条件", sourcedHighlights(formulas, "formula", "查看其余公式", 2))}
        </div>
        <details class="report-complete-analysis"><summary>查看完整分析</summary>
          ${block("选题规律", result.topic_buckets)}${block("内容组织", result.thinking_patterns)}${block("表达与呈现", result.expression_patterns)}${block("已有解释（待验证）", first(explanation.bullets, sections.traffic_sources?.hooks))}
          ${!hasContent(expressionFindings) ? block("跨样本规律", sections.repeatable_patterns) : ""}${block("验证建议", first(strategy.validation_rules, sections.checklist))}${groupMarkup ? `<details class="report-content-groups"><summary>按样本类型归纳</summary>${groupMarkup}</details>` : ""}
          ${hasContent(result.creator_clone_spec) ? `<details><summary>完整创作方法</summary>${narrative(result.creator_clone_spec)}</details>` : ""}
          ${supplementary ? `<details><summary>补充策略与模板 · 历史来源未区分</summary>${supplementary}</details>` : ""}
          <details><summary>定位与观察原字段（含展示回退）</summary>${detail({summary: result.summary, headline: viewModel.headline, positioning, observation, core_judgment: sections.core_judgment})}</details>
          <details><summary>完整报告原字段与扩展</summary>${detail(result)}${detail(viewModel)}</details>
        </details>
        ${card("limits", "证据与限制", `${hasContent(limits) ? limits.map((item) => `<div class="report-limit">${narrative(item)}</div>`).join("") : "<p>报告未单独记录证据限制；这不代表结论已经核验。</p>"}
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

  // Keep the report anchor local: the workbench uses the URL hash for routing.
  global.document?.addEventListener("click", (event) => {
    const trigger = event.target?.closest?.("[data-report-action-jump]");
    const target = trigger?.closest?.(".creator-reading-report")?.querySelector('[data-report-section="actions"]');
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView({behavior: "smooth", block: "start"});
    target.focus({preventScroll: true});
  });
  global.CreatorReportView = Object.freeze({createRenderer, hasContent, renderValue, renderFocus, renderFocusedAnalysis, renderSections});
})(window);
