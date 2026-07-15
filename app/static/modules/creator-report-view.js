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

  global.CreatorReportView = Object.freeze({createRenderer});
})(window);
