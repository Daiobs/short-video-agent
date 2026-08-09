(function initializeCreatorExecutionPackView(global) {
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

  function rows(value) {
    return Array.isArray(value) ? value : [];
  }

  function renderList(items, emptyText = "暂无内容") {
    const values = rows(items).map((item) => String(item || "").trim()).filter(Boolean);
    if (!values.length) {
      return `<p class="muted compact-copy">${escapeHtml(emptyText)}</p>`;
    }
    return `<ul class="execution-pack-list">${values.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
  }

  function renderTopicChoices(topics) {
    const values = rows(topics).filter((item) => item && typeof item === "object");
    if (!values.length) {
      return '<p class="muted compact-copy">暂无可选选题。</p>';
    }
    return `
      <ol class="execution-topic-list">
        ${values.map((topic, index) => `
          <li>
            <div>
              <strong>${escapeHtml(topic.title || `选题 ${index + 1}`)}</strong>
              <p>${escapeHtml([topic.angle, topic.why, topic.expected_metric ? `预期指标：${topic.expected_metric}` : ""].filter(Boolean).join(" · "))}</p>
              ${topic.requires_review ? '<span class="strategy-plan-review">需人工复核</span>' : ""}
            </div>
            <button type="button" class="secondary-button execution-topic-action" data-execution-topic-index="${index}">用这个选题生成</button>
          </li>
        `).join("")}
      </ol>
    `;
  }

  function renderScript(script) {
    const value = objectValue(script);
    return `
      <p><strong>开场：</strong>${escapeHtml(value.opening || "")}</p>
      <ol class="execution-script-beats">
        ${rows(value.beats).map((beat) => {
          const item = objectValue(beat);
          return `<li><span>${escapeHtml(item.duration_hint || "")}</span><strong>${escapeHtml(item.purpose || "推进")}</strong><p>${escapeHtml(item.script || "")}</p></li>`;
        }).join("")}
      </ol>
      <p><strong>结尾：</strong>${escapeHtml(value.ending || "")}</p>
      <p><strong>CTA：</strong>${escapeHtml(value.cta || "")}</p>
      <p><strong>字幕 / 旁白：</strong>${escapeHtml(value.caption_or_voice_over || "")}</p>
    `;
  }

  function renderShotPlan(shots) {
    return `
      <div class="execution-shot-grid">
        ${rows(shots).map((shot, index) => {
          const item = objectValue(shot);
          return `
            <article class="execution-shot-card">
              <div><span>镜头 ${escapeHtml(item.order || index + 1)}</span><strong>${escapeHtml(item.duration_hint || "")}</strong></div>
              <h5>${escapeHtml(item.shot_type || "镜头")}</h5>
              <p><strong>动作：</strong>${escapeHtml(item.subject_action || "")}</p>
              <p><strong>机位：</strong>${escapeHtml(item.camera || "")}</p>
              <p><strong>构图：</strong>${escapeHtml(item.composition || "")}</p>
              <p><strong>光线 / 场景：</strong>${escapeHtml(item.lighting_or_scene || "")}</p>
              <p><strong>目的：</strong>${escapeHtml(item.purpose || "")}</p>
            </article>
          `;
        }).join("")}
      </div>
    `;
  }

  function renderEvidenceRefs(evidenceRefs) {
    return rows(evidenceRefs).map((reference) => {
      const item = objectValue(reference);
      const label = item.type === "sample"
        ? `${item.title || "代表样本"} · ${item.sample_id || ""}`
        : `${item.field || item.type || "依据"} · ${item.value || ""}`;
      return `<li><strong>${escapeHtml(label)}</strong><p>${escapeHtml(item.reason || "")}</p></li>`;
    }).join("");
  }

  function renderPack(packValue) {
    const pack = objectValue(packValue);
    const topic = objectValue(pack.topic);
    const hook = objectValue(pack.hook);
    const basis = objectValue(pack.creative_basis);
    const cover = objectValue(pack.cover);
    const editing = objectValue(pack.editing_notes);
    const lowConfidence = pack.confidence === "low" || rows(pack.warnings).length > 0;
    return `
      <section class="creator-execution-pack" data-execution-pack-version="${escapeHtml(pack.version || "1.0")}">
        ${lowConfidence ? `
          <div class="execution-pack-review-warning" role="status">
            <strong>建议人工复核</strong>
            <p>${escapeHtml(rows(pack.warnings)[0] || "当前报告证据不足，请核对镜头、文案和样本依据后再拍摄。")}</p>
          </div>
        ` : ""}
        <article class="execution-pack-topic-hero">
          <span>下一条内容 · ${escapeHtml(pack.confidence || "medium")} confidence</span>
          <h3>${escapeHtml(topic.title || "待确认选题")}</h3>
          <p>${escapeHtml(topic.angle || "")}</p>
          <dl>
            <dt>目标受众</dt><dd>${escapeHtml(topic.audience || "")}</dd>
            <dt>创作目标</dt><dd>${escapeHtml(topic.goal || "")}</dd>
            <dt>预期指标</dt><dd>${escapeHtml(topic.expected_metric || "")}</dd>
          </dl>
          <div class="execution-pack-basis-summary">
            <strong>为什么值得拍</strong>
            <p>${escapeHtml(basis.summary || "")}</p>
          </div>
        </article>
        <div class="execution-pack-primary-grid">
          <article class="execution-pack-section execution-pack-hook">
            <span>0-3 秒</span>
            <h4>前 3 秒 Hook</h4>
            <p><strong>画面：</strong>${escapeHtml(hook.visual || "")}</p>
            <blockquote>${escapeHtml(hook.spoken_or_caption || "")}</blockquote>
            <p><strong>目的：</strong>${escapeHtml(hook.purpose || "")} · ${escapeHtml(hook.duration_hint || "")}</p>
          </article>
          <article class="execution-pack-section">
            <span>Script</span>
            <h4>具体脚本</h4>
            ${renderScript(pack.script)}
          </article>
        </div>
        <article class="execution-pack-section execution-pack-shots">
          <span>Shot plan</span>
          <h4>实际镜头表</h4>
          ${renderShotPlan(pack.shot_plan)}
        </article>
        <div class="execution-pack-support-grid">
          <article class="execution-pack-section">
            <span>Cover</span>
            <h4>封面</h4>
            <p><strong>画面：</strong>${escapeHtml(cover.visual || "")}</p>
            <p><strong>构图：</strong>${escapeHtml(cover.composition || "")}</p>
            <p class="execution-cover-headline">${escapeHtml(cover.headline || "")}</p>
            <p><strong>依据：</strong>${escapeHtml(cover.reason || "")}</p>
          </article>
          <article class="execution-pack-section">
            <span>Titles</span>
            <h4>标题候选</h4>
            <ol class="execution-title-list">
              ${rows(pack.titles).map((title) => `<li><span>${escapeHtml(title.direction || "方向")}</span><strong>${escapeHtml(title.text || "")}</strong></li>`).join("")}
            </ol>
          </article>
          <article class="execution-pack-section">
            <span>Publish</span>
            <h4>发布文案</h4>
            <p>${escapeHtml(pack.publish_copy || "")}</p>
            <p class="execution-hashtags">${rows(pack.hashtags).map(escapeHtml).join(" ")}</p>
          </article>
        </div>
        <div class="execution-pack-support-grid">
          <article class="execution-pack-section">
            <span>Edit</span>
            <h4>剪辑建议</h4>
            ${renderList([
              `节奏：${editing.pace || ""}`,
              `剪切：${editing.cuts || ""}`,
              `字幕：${editing.subtitle || ""}`,
              `声音：${editing.music_or_sound_direction || ""}`,
              `转场：${editing.transition_notes || ""}`,
            ])}
          </article>
          <article class="execution-pack-section">
            <span>Check</span>
            <h4>发布前检查</h4>
            ${renderList(pack.production_checklist)}
          </article>
        </div>
        <details class="execution-pack-evidence-details">
          <summary>为什么这样生成</summary>
          <div class="execution-pack-evidence-grid">
            <section>
              <h5>创作依据</h5>
              <p>${escapeHtml(basis.summary || "")}</p>
              ${renderList([].concat(rows(basis.creator_rules), rows(basis.hook_patterns), rows(basis.formulas)))}
            </section>
            <section>
              <h5>可追溯证据</h5>
              <ul class="execution-pack-list">${renderEvidenceRefs(pack.evidence_refs)}</ul>
            </section>
            ${rows(pack.warnings).length ? `<section><h5>风险提示</h5>${renderList(pack.warnings)}</section>` : ""}
          </div>
        </details>
      </section>
    `;
  }

  function packText(packValue, section = "full") {
    const pack = objectValue(packValue);
    const topic = objectValue(pack.topic);
    const hook = objectValue(pack.hook);
    const script = objectValue(pack.script);
    const cover = objectValue(pack.cover);
    const editing = objectValue(pack.editing_notes);
    const scriptLines = [
      `开场：${script.opening || ""}`,
      ...rows(script.beats).map((beat, index) => `${index + 1}. ${beat.duration_hint || ""} ${beat.purpose || ""}：${beat.script || ""}`),
      `结尾：${script.ending || ""}`,
      `CTA：${script.cta || ""}`,
      `字幕/旁白：${script.caption_or_voice_over || ""}`,
    ];
    if (section === "script") {
      return scriptLines.join("\n");
    }
    if (section === "publish") {
      return `${pack.publish_copy || ""}\n${rows(pack.hashtags).join(" ")}`.trim();
    }
    const lines = [
      `# ${topic.title || "Creator Execution Pack"}`,
      "",
      `角度：${topic.angle || ""}`,
      `受众：${topic.audience || ""}`,
      `目标：${topic.goal || ""}`,
      `预期指标：${topic.expected_metric || ""}`,
      "",
      "## 为什么值得拍",
      objectValue(pack.creative_basis).summary || "",
      "",
      "## 前 3 秒",
      `画面：${hook.visual || ""}`,
      `台词/字幕：${hook.spoken_or_caption || ""}`,
      `目的：${hook.purpose || ""}`,
      "",
      "## 脚本",
      ...scriptLines,
      "",
      "## 镜头表",
      ...rows(pack.shot_plan).map((shot, index) => `${index + 1}. ${shot.duration_hint || ""}｜${shot.shot_type || ""}｜${shot.subject_action || ""}｜${shot.camera || ""}｜${shot.composition || ""}｜${shot.lighting_or_scene || ""}｜${shot.purpose || ""}`),
      "",
      "## 封面",
      `${cover.headline || ""}｜${cover.visual || ""}｜${cover.composition || ""}｜${cover.reason || ""}`,
      "",
      "## 标题",
      ...rows(pack.titles).map((title) => `- [${title.direction || "方向"}] ${title.text || ""}`),
      "",
      "## 发布文案",
      pack.publish_copy || "",
      rows(pack.hashtags).join(" "),
      "",
      "## 剪辑建议",
      `节奏：${editing.pace || ""}`,
      `剪切：${editing.cuts || ""}`,
      `字幕：${editing.subtitle || ""}`,
      `声音：${editing.music_or_sound_direction || ""}`,
      `转场：${editing.transition_notes || ""}`,
      "",
      "## 发布前检查",
      ...rows(pack.production_checklist).map((item) => `- ${item}`),
      ...(rows(pack.warnings).length ? ["", "## 人工复核提示", ...rows(pack.warnings).map((item) => `- ${item}`)] : []),
    ];
    return lines.join("\n").trim();
  }

  function hasPack(container) {
    if (!container) {
      return false;
    }
    if (typeof container.querySelector === "function") {
      return Boolean(container.querySelector(".creator-execution-pack"));
    }
    return String(container.innerHTML || "").includes("creator-execution-pack");
  }

  global.CreatorExecutionPackView = Object.freeze({
    renderPack,
    renderTopicChoices,
    packText,
    hasPack,
  });
})(window);
