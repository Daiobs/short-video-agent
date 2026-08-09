(function initRepresentativeSampleSelectorUi(globalScope) {
  "use strict";

  const SAFE_ID_RE = /^[A-Za-z0-9_-]{1,160}$/;
  const ROLE_ORDER = [
    "BREAKOUT_HIT",
    "COMMENT_MAGNET",
    "SAVE_SHARE_VALUE",
    "RECENT_WINNER",
    "DIVERSITY_ANCHOR",
    "BASELINE_TYPICAL",
  ];

  function list(value) {
    return Array.isArray(value) ? value : [];
  }

  function safeId(value) {
    const id = String(value || "").trim();
    return SAFE_ID_RE.test(id) ? id : "";
  }

  function normalizeSelection(payload) {
    const source = payload && typeof payload === "object" ? payload : {};
    const seen = new Set();
    const recommendations = list(source.recommendations)
      .slice(0, 10)
      .map((item) => {
        const sampleId = safeId(item?.sample_id);
        if (!sampleId || seen.has(sampleId)) return null;
        seen.add(sampleId);
        const roles = list(item.roles)
          .map(String)
          .filter((role) => ROLE_ORDER.includes(role));
        const primaryRole = ROLE_ORDER.includes(String(item?.primary_role || ""))
          ? String(item.primary_role)
          : roles[0] || "BASELINE_TYPICAL";
        return Object.freeze({
          sample_id: sampleId,
          rank: Math.max(1, Number(item?.rank || seen.size)),
          score: Math.max(0, Math.min(100, Number(item?.score || 0))),
          primary_role: primaryRole,
          roles: Object.freeze([...new Set([primaryRole, ...roles])]),
          reasons: Object.freeze(list(item?.reasons).map(String).filter(Boolean).slice(0, 3)),
          metrics: Object.freeze({...((item?.metrics && typeof item.metrics === "object") ? item.metrics : {})}),
        });
      })
      .filter(Boolean);
    const coverage = Object.fromEntries(
      ROLE_ORDER.map((role) => [role, Boolean(source.coverage?.[role])]),
    );
    return Object.freeze({
      algorithm_version: String(source.algorithm_version || "representative-v1"),
      target_count: Math.max(3, Math.min(10, Number(source.target_count || 6))),
      available_count: Math.max(0, Number(source.available_count || 0)),
      recommended_count: recommendations.length,
      recommendations: Object.freeze(recommendations),
      recommended_sample_ids: Object.freeze(recommendations.map((item) => item.sample_id)),
      coverage: Object.freeze(coverage),
      warnings: Object.freeze(list(source.warnings).map(String).filter(Boolean)),
      artifact_url: String(source.artifact_url || ""),
    });
  }

  function recommendationById(selection, sampleId) {
    const id = safeId(sampleId);
    return list(selection?.recommendations).find((item) => item.sample_id === id) || null;
  }

  function recommendedIds(selection) {
    return list(selection?.recommendations).map((item) => item.sample_id).filter(Boolean);
  }

  function matchingItems(selection, items, keyOf) {
    const byId = new Map(list(items).map((item) => [safeId(keyOf(item)), item]));
    return recommendedIds(selection).map((id) => byId.get(id)).filter(Boolean);
  }

  function nextManualSelection(selectedIds, sampleId, checked) {
    const next = new Set(list(selectedIds).map(safeId).filter(Boolean));
    const id = safeId(sampleId);
    if (!id) return Object.freeze([...next]);
    if (checked) next.add(id);
    else next.delete(id);
    return Object.freeze([...next]);
  }

  const api = Object.freeze({
    ROLE_ORDER: Object.freeze([...ROLE_ORDER]),
    matchingItems,
    nextManualSelection,
    normalizeSelection,
    recommendationById,
    recommendedIds,
  });
  globalScope.RepresentativeSampleSelectorUI = api;
})(typeof window !== "undefined" ? window : globalThis);
