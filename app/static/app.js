// BEGIN SINGLE_ITEM_JOB_STATUS
(function initializeSingleItemJobStatus(global) {
  "use strict";

  const stageDefinitions = Object.freeze([
    Object.freeze({id: "received", label: "已接收"}),
    Object.freeze({id: "acquisition", label: "获取素材"}),
    Object.freeze({id: "analysis", label: "生成分析"}),
    Object.freeze({id: "complete", label: "完成"}),
  ]);
  const displayStates = new Set(["pending", "active", "completed", "partial", "failed"]);
  const flowStatuses = new Set(["pending", "active", "completed", "partial", "failed"]);
  const jobStatuses = new Set(["pending", "running", "success", "failed", "recoverable", "stale"]);
  const analysisStatuses = new Set([
    "", "pending", "running", "success", "failed", "skipped",
    "completed", "not_configured", "not_analyzed", "artifact_incomplete",
  ]);
  const optionalStatuses = new Set([
    "", "pending", "success", "failed", "provider_missing", "missing",
    "no_speech", "no_text", "disabled", "not_configured", "skipped", "not_required",
  ]);
  const successfulOptionalStatuses = new Set(["success", "no_speech", "no_text"]);
  const failedOptionalStatuses = new Set(["failed", "provider_missing"]);
  const acquisitionErrorCodes = new Set([
    "INVALID_AWEME_URL", "AWEME_ID_NOT_FOUND", "PROVIDER_FAILED", "QUALITY_NOT_FOUND",
    "URL_EXPIRED", "HOST_NOT_ALLOWED", "REDIRECT_HOST_NOT_ALLOWED", "CONTENT_TYPE_INVALID",
    "CONTENT_LENGTH_TOO_LARGE", "DOWNLOAD_TIMEOUT", "DOWNLOAD_FAILED", "INVALID_VIDEO_FILE",
    "LOCAL_UPLOAD_FAILED",
  ]);
  const caseErrorCodes = new Set([
    "FFMPEG_NOT_FOUND", "FFPROBE_FAILED", "KEYFRAME_EXTRACT_FAILED", "CASE_BUILD_FAILED",
  ]);
  const stateLabels = Object.freeze({
    pending: "未开始",
    active: "进行中",
    completed: "已完成",
    partial: "部分完成",
    failed: "失败",
  });
  const stateIcons = Object.freeze({
    pending: "○",
    active: "●",
    completed: "✓",
    partial: "!",
    failed: "×",
  });
  const optionalResultDefinitions = Object.freeze([
    Object.freeze({id: "asr", label: "语音检查结果", category: "语音文本不可用"}),
    Object.freeze({id: "ocr", label: "画面文字检查结果", category: "画面文字不可用"}),
    Object.freeze({id: "comments", label: "评论摘要", category: "辅助证据不可用"}),
    Object.freeze({id: "metrics", label: "指标快照", category: "辅助证据不可用"}),
    Object.freeze({id: "index", label: "结构化索引", category: "辅助证据不可用"}),
  ]);

  function record(value) {
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  }

  function hasRecordContent(value) {
    return value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).length > 0;
  }

  function itemList(value, limit = 20) {
    return Array.isArray(value)
      ? value.filter((item) => item !== undefined && item !== null).slice(0, limit)
      : [];
  }

  function normalizedStatus(value) {
    return String(value || "").trim().toLowerCase().slice(0, 64);
  }

  function escapeMarkup(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function diagnoseUnknown(source) {
    const host = String(global.location?.hostname || "").toLowerCase();
    if (["localhost", "127.0.0.1", "::1"].includes(host) && global.console?.warn) {
      global.console.warn("[single-item-status] 未识别状态，已安全降级。", {source});
    }
  }

  function failureCategory(errorCode, source = "") {
    const code = String(errorCode || "").trim().toUpperCase().slice(0, 96);
    const kind = String(source || "").trim().toLowerCase().slice(0, 48);
    if (code.startsWith("ASR_") || kind === "asr") {
      return "语音文本不可用";
    }
    if (code.startsWith("OCR_") || kind === "ocr") {
      return "画面文字不可用";
    }
    if (
      code.startsWith("DOWNLOAD_")
      || code.startsWith("QUALITY_")
      || code.startsWith("PROVIDER_")
      || code.startsWith("URL_")
      || acquisitionErrorCodes.has(code)
      || kind === "download"
      || kind === "acquisition"
    ) {
      return "素材获取未完成";
    }
    if (
      code.startsWith("CASE_BUILD_")
      || code.startsWith("FFMPEG_")
      || code.startsWith("FFPROBE_")
      || code.startsWith("KEYFRAME_")
      || caseErrorCodes.has(code)
      || kind === "case"
    ) {
      return "素材包未完整";
    }
    if (code.startsWith("LLM_") || code === "AUTO_ANALYSIS_FAILED" || kind === "analysis") {
      return "自动拆解未生成";
    }
    if (code.startsWith("ENRICHMENT_") || code === "COMMENTS_IMPORT_FAILED" || kind === "enrichment") {
      return "证据补充未完成";
    }
    if (/SAVE|WRITE|PERSIST/.test(code) || kind === "storage") {
      return "结果保存未完成";
    }
    return "状态暂时不可确认";
  }

  function optionalStatus(caseData, manifestStatuses, id) {
    const enrichment = record(caseData.enrichment);
    if (id === "asr") {
      return normalizedStatus(record(enrichment.asr_status).status || manifestStatuses.asr);
    }
    if (id === "ocr") {
      return normalizedStatus(record(enrichment.ocr_status).status || manifestStatuses.ocr);
    }
    return normalizedStatus(manifestStatuses[id]);
  }

  function normalizedFlowStage(flow) {
    const raw = normalizedStatus(flow.stage || flow.phase || "idle");
    return {
      receiving: "received",
      acquiring: "acquisition",
      analyzing: "analysis",
      done: "complete",
    }[raw] || raw || "idle";
  }

  function makeStages() {
    return stageDefinitions.map((stage) => ({
      ...stage,
      state: "pending",
      statusLabel: stateLabels.pending,
    }));
  }

  function setStage(stages, id, state) {
    const stage = stages.find((item) => item.id === id);
    if (!stage || !displayStates.has(state)) {
      return;
    }
    stage.state = state;
    stage.statusLabel = stateLabels[state];
  }

  function markPreviousCompleted(stages, id) {
    const index = stageDefinitions.findIndex((stage) => stage.id === id);
    for (let position = 0; position < index; position += 1) {
      if (!["partial", "failed"].includes(stages[position].state)) {
        setStage(stages, stages[position].id, "completed");
      }
    }
  }

  function derive({job: rawJob = null, caseData: rawCase = null, flow: rawFlow = null} = {}) {
    const job = record(rawJob);
    const observedCase = record(rawCase);
    const flow = record(rawFlow);
    const result = record(job.result_json || job.result);
    const resultCase = record(result.case);
    const expectedCaseId = String(result.case_id || resultCase.case_id || "").trim();
    const observedCaseId = String(observedCase.case_id || "").trim();
    const caseIdentityMismatch = Boolean(
      expectedCaseId
      && observedCaseId
      && expectedCaseId !== observedCaseId,
    );
    const caseData = caseIdentityMismatch ? {} : observedCase;
    const analysisPayload = record(result.analysis);
    const workflow = record(caseData.primary_workflow);
    const enrichment = record(caseData.enrichment);
    const manifestStatuses = record(record(enrichment.manifest).statuses);
    const stages = makeStages();
    const availableResults = new Set();
    const failedCapabilities = new Set();
    const failureCategories = new Set();
    let analysisFailureKnown = false;
    let unknown = caseIdentityMismatch;

    if (caseIdentityMismatch) {
      diagnoseUnknown("case.identity");
    }

    function noteFailure(capability, category) {
      failedCapabilities.add(capability);
      failureCategories.add(category);
    }

    const jobStatus = normalizedStatus(job.status);
    const jobType = normalizedStatus(job.type || job.task_type);
    const jobErrorCode = String(job.error_code || "").trim();
    const jobErrorKnown = Boolean(
      jobErrorCode
      && failureCategory(jobErrorCode) !== "状态暂时不可确认",
    );
    const isWorkbenchProjection = Boolean(String(job.task_id || "").trim());
    const jobUnsettled = ["pending", "running", "stale"].includes(jobStatus);
    const flowStage = normalizedFlowStage(flow);
    const flowStatus = normalizedStatus(flow.status || (flowStage === "idle" ? "pending" : "active"));
    const caseId = String(expectedCaseId || caseData.case_id || "").trim();
    const downloadAvailable = Boolean(
      record(result.download).local_video_id
      || result.local_video_id
      || caseData.local_video_id,
    );
    const caseAvailable = Boolean(caseId);
    const resultCaseProvesArtifact = Boolean(
      resultCase.case_id
      && resultCase.local_video_id,
    );
    const caseAwaitingVerification = Boolean(
      expectedCaseId
      && !caseData.case_id
      && (
        (isWorkbenchProjection && !resultCaseProvesArtifact)
        || job.__singleItemCaseVerificationPending === true
      ),
    );
    if (caseAwaitingVerification) {
      unknown = true;
    }
    const workflowHasArtifactVerdict = typeof workflow.artifact_ready === "boolean";
    const baseReady = workflowHasArtifactVerdict
      ? workflow.artifact_ready === true
      : resultCaseProvesArtifact;
    const workflowAnalysisStatus = normalizedStatus(workflow.analysis_status);
    let analysisStatus = normalizedStatus(
      result.analysis_status
      || record(caseData.analysis_job).status
      || workflowAnalysisStatus,
    );
    const analysisSuccessClaimed = ["success", "completed"].includes(analysisStatus);
    if (analysisStatus === "completed") {
      analysisStatus = "success";
    } else if (analysisStatus === "not_configured") {
      analysisStatus = "skipped";
    } else if (analysisStatus === "not_analyzed" || analysisStatus === "artifact_incomplete") {
      analysisStatus = "pending";
    }
    const caseAnalysisAvailable = Boolean(
      hasRecordContent(caseData.analysis_result)
      || caseData.analysis_report
      || workflowAnalysisStatus === "completed"
    );
    const jobAnalysisAvailable = Boolean(
      hasRecordContent(analysisPayload.analysis_result)
      || analysisPayload.analysis_report
      || hasRecordContent(result.analysis_result)
      || result.analysis_report
    );
    const loadedCaseAnalysisUnavailable = Object.keys(caseData).length > 0
      && ["not_analyzed", "not_configured", "artifact_incomplete"].includes(workflowAnalysisStatus);
    if (caseAnalysisAvailable || jobAnalysisAvailable) {
      analysisStatus = "success";
    } else if (loadedCaseAnalysisUnavailable && analysisStatus === "success") {
      analysisStatus = workflowAnalysisStatus === "not_configured" ? "skipped" : "pending";
    }
    const analysisAvailable = Boolean(caseAnalysisAvailable || jobAnalysisAvailable);
    const unverifiedAnalysisSuccess = Boolean(
      analysisSuccessClaimed
      && !analysisAvailable
      && !loadedCaseAnalysisUnavailable,
    );
    if (unverifiedAnalysisSuccess) {
      unknown = true;
      diagnoseUnknown("analysis.success_without_result");
    }
    const unconfirmedWorkbenchFailure = Boolean(
      jobStatus === "failed"
      && isWorkbenchProjection
      && !jobErrorKnown,
    );
    const failureEvidenceDeferred = Boolean(
      jobUnsettled
      || caseAwaitingVerification
      || unverifiedAnalysisSuccess,
    );
    const analysisRequestActive = jobUnsettled
      || caseAwaitingVerification
      || unverifiedAnalysisSuccess
      || unconfirmedWorkbenchFailure
      || (flowStage === "analysis" && ["pending", "active"].includes(flowStatus));
    const analysisKnownMissing = !analysisRequestActive && !analysisAvailable && (
      workflowAnalysisStatus === "not_analyzed"
      || (jobStatus === "success" && baseReady && analysisStatus === "pending")
    );

    if (baseReady) {
      availableResults.add("基础素材包");
    }
    if (analysisAvailable) {
      availableResults.add("AI 拆解报告");
    }
    const missingArtifacts = itemList(workflow.missing_artifacts, 12);
    const artifactFailureKnown = !failureEvidenceDeferred && Boolean(
      missingArtifacts.length
      || workflow.artifact_ready === false
      || workflowAnalysisStatus === "artifact_incomplete",
    );
    if (artifactFailureKnown) {
      noteFailure("material-package", "素材包未完整");
    }

    for (const definition of optionalResultDefinitions) {
      const status = optionalStatus(caseData, manifestStatuses, definition.id);
      if (!optionalStatuses.has(status)) {
        unknown = true;
        diagnoseUnknown("case.enrichment." + definition.id);
        continue;
      }
      if (successfulOptionalStatuses.has(status)) {
        availableResults.add(definition.label);
      } else if (failedOptionalStatuses.has(status) && !failureEvidenceDeferred) {
        noteFailure("optional-" + definition.id, definition.category);
        analysisFailureKnown = true;
      }
    }

    if (!analysisStatuses.has(analysisStatus)) {
      unknown = true;
      diagnoseUnknown("analysis_status");
    } else if (analysisStatus === "failed" && !failureEvidenceDeferred) {
      noteFailure("analysis", failureCategory(record(result.analysis_error).error_code, "analysis"));
      analysisFailureKnown = true;
    } else if (analysisStatus === "skipped" && !failureEvidenceDeferred) {
      noteFailure("analysis", "分析产物缺失");
      analysisFailureKnown = true;
    } else if (analysisKnownMissing) {
      noteFailure("analysis", "分析产物缺失");
      analysisFailureKnown = true;
    }

    if (jobStatus && !jobStatuses.has(jobStatus)) {
      unknown = true;
      diagnoseUnknown("job.status");
    }
    const caseStatus = normalizedStatus(caseData.status);
    if (caseStatus && !["success", "failed", "missing"].includes(caseStatus)) {
      unknown = true;
      diagnoseUnknown("case.status");
    }
    if ((caseStatus === "failed" || caseStatus === "missing") && !failureEvidenceDeferred) {
      noteFailure("material-package", "素材包未完整");
    }

    const projectedFailureHasEvidence = Boolean(
      jobErrorKnown
      || (["failed", "skipped"].includes(analysisStatus) && !failureEvidenceDeferred)
      || artifactFailureKnown
      || ((caseStatus === "failed" || caseStatus === "missing") && !failureEvidenceDeferred),
    );
    const ambiguousWorkbenchFailure = Boolean(
      unconfirmedWorkbenchFailure
      && !projectedFailureHasEvidence,
    );
    if (ambiguousWorkbenchFailure) {
      unknown = true;
      diagnoseUnknown("workbench.failed_without_evidence");
    }

    const hasUsableResult = availableResults.size > 0;
    const analysisJobType = ["analyze-case", "enrich-case", "asr-case", "ocr-case"].includes(jobType);
    const jobFailureStage = analysisJobType || caseAvailable || downloadAvailable ? "analysis" : "acquisition";

    if (!flowStatuses.has(flowStatus)) {
      unknown = true;
      diagnoseUnknown("flow.status");
    }

    if (flowStage !== "idle" && !jobStatus) {
      if (["received", "acquisition", "analysis", "complete"].includes(flowStage)) {
        const unsupportedFlowTerminal = ["completed", "partial"].includes(flowStatus)
          && !hasUsableResult;
        if (unsupportedFlowTerminal) {
          unknown = true;
          diagnoseUnknown("flow.terminal_without_result");
        }
        markPreviousCompleted(stages, flowStage);
        setStage(
          stages,
          flowStage,
          flowStatus === "failed"
            ? "failed"
            : unsupportedFlowTerminal
              ? "active"
              : ["completed", "partial"].includes(flowStatus)
                ? flowStatus
                : "active",
        );
      } else {
        unknown = true;
        diagnoseUnknown("flow.stage");
        setStage(stages, "received", "active");
      }
    }

    if (caseAvailable || downloadAvailable || jobStatus) {
      setStage(stages, "received", "completed");
    }
    if (downloadAvailable || baseReady) {
      setStage(stages, "acquisition", "completed");
    }
    if (analysisAvailable) {
      setStage(stages, "analysis", "completed");
      if (!jobStatus || jobStatus === "success") {
        markPreviousCompleted(stages, "complete");
        setStage(stages, "complete", "completed");
      }
    }
    if (caseAwaitingVerification) {
      markPreviousCompleted(stages, "analysis");
      setStage(stages, "analysis", "active");
      setStage(stages, "complete", "pending");
    }

    if (jobStatus === "pending" || jobStatus === "running") {
      if (downloadAvailable || caseAvailable || baseReady || analysisJobType || analysisStatus === "pending") {
        markPreviousCompleted(stages, "analysis");
        setStage(stages, "analysis", "active");
      } else {
        markPreviousCompleted(stages, "acquisition");
        setStage(stages, "acquisition", "active");
      }
    } else if (jobStatus === "success") {
      if (!caseAvailable && !baseReady && !analysisAvailable && jobType !== "build-case") {
        unknown = true;
        diagnoseUnknown("job.success_result");
      }
      if (analysisAvailable && analysisStatus === "success" && !caseAwaitingVerification) {
        markPreviousCompleted(stages, "complete");
        setStage(stages, "analysis", "completed");
        setStage(stages, "complete", "completed");
      } else if (!failureEvidenceDeferred && (
        ["failed", "skipped"].includes(analysisStatus)
        || analysisKnownMissing
      )) {
        setStage(stages, "analysis", hasUsableResult ? "partial" : "failed");
        setStage(stages, "complete", hasUsableResult ? "partial" : "failed");
      }
    } else if (jobStatus === "failed" && !ambiguousWorkbenchFailure && !caseAwaitingVerification) {
      if (!failedCapabilities.size) {
        noteFailure(
          jobFailureStage === "analysis" ? "analysis" : "material-acquisition",
          failureCategory(job.error_code, jobFailureStage),
        );
      }
      if (hasUsableResult) {
        if (baseReady || caseAvailable) {
          setStage(stages, "analysis", "partial");
        } else if (downloadAvailable) {
          setStage(stages, "analysis", "failed");
        }
        setStage(stages, "complete", "partial");
      } else {
        markPreviousCompleted(stages, jobFailureStage);
        setStage(stages, jobFailureStage, "failed");
      }
    } else if (jobStatus === "recoverable") {
      if (hasUsableResult) {
        setStage(stages, analysisAvailable ? "complete" : "analysis", "partial");
      } else {
        unknown = true;
        diagnoseUnknown("job.recoverable_without_result");
      }
    } else if (jobStatus === "stale") {
      unknown = true;
      const uncertainStage = analysisAvailable
        ? "complete"
        : downloadAvailable || caseAvailable || baseReady
          ? "analysis"
          : "acquisition";
      setStage(stages, uncertainStage, "active");
    }

    if (
      artifactFailureKnown
      || ((caseStatus === "failed" || caseStatus === "missing") && !failureEvidenceDeferred)
    ) {
      setStage(stages, "acquisition", hasUsableResult ? "partial" : "failed");
      if (!hasUsableResult) {
        setStage(stages, "analysis", "pending");
      }
    }

    const failedCount = failedCapabilities.size;
    const partialSummary = hasUsableResult && failedCount > 0
      ? {
          successfulCount: availableResults.size,
          failedCount,
          categories: Array.from(failureCategories),
          availableResults: Array.from(availableResults),
        }
      : null;
    if (partialSummary) {
      if (analysisFailureKnown && !["failed", "partial"].includes(stages[2].state)) {
        setStage(stages, "analysis", "partial");
      }
      setStage(stages, "complete", "partial");
    }

    const explicitFailure = (!jobStatus && flowStatus === "failed")
      || (jobStatus === "failed" && !ambiguousWorkbenchFailure && !caseAwaitingVerification)
      || (["failed", "skipped"].includes(analysisStatus)
        && !failureEvidenceDeferred)
      || analysisKnownMissing
      || artifactFailureKnown
      || ((caseStatus === "failed" || caseStatus === "missing") && !failureEvidenceDeferred);
    const completeFailure = Boolean(explicitFailure && !hasUsableResult);
    if (completeFailure && !failureCategories.size) {
      const flowFailureSource = flowStage === "analysis" ? "analysis" : "acquisition";
      failureCategories.add(failureCategory(flow.error_code, flowFailureSource));
    }
    if (completeFailure && !stages.some((stage) => stage.state === "failed")) {
      setStage(stages, flowStage === "received" ? "received" : jobFailureStage, "failed");
    }
    if (completeFailure) {
      setStage(stages, "complete", "failed");
    }

    if (unknown) {
      const allCompleted = stages.every((stage) => stage.state === "completed");
      if (allCompleted) {
        setStage(stages, "complete", "active");
      } else if (!stages.some((stage) => ["active", "failed", "partial"].includes(stage.state))) {
        const uncertain = stages.find((stage) => stage.state !== "completed") || stages[3];
        setStage(stages, uncertain.id, "active");
      }
    }

    const failureCategoryLabel = Array.from(failureCategories)[0] || "状态暂时不可确认";
    const hasPartialStage = stages.some((stage) => stage.state === "partial");
    let overallLabel = "等待开始";
    if (unknown) {
      overallLabel = "状态更新中";
    } else if (completeFailure) {
      overallLabel = "任务未完成 · " + failureCategoryLabel;
    } else if (partialSummary || hasPartialStage) {
      overallLabel = "部分结果可用";
    } else if (stages.every((stage) => stage.state === "completed")) {
      overallLabel = "已完成";
    } else if (stages.some((stage) => stage.state === "active")) {
      overallLabel = "处理中";
    } else if (hasUsableResult) {
      overallLabel = "可继续";
    }

    return Object.freeze({
      stages: Object.freeze(stages.map((stage) => Object.freeze({...stage}))),
      overallLabel,
      partialSummary: partialSummary ? Object.freeze({
        successfulCount: partialSummary.successfulCount,
        failedCount: partialSummary.failedCount,
        categories: Object.freeze([...partialSummary.categories]),
        availableResults: Object.freeze([...partialSummary.availableResults]),
      }) : null,
      completeFailure,
      failureCategory: completeFailure ? failureCategoryLabel : "",
      hasUsableResult,
      unknown,
    });
  }

  function stageItemsMarkup(viewModel) {
    return viewModel.stages.map((stage, index) => {
      const current = stage.state === "active" ? ' aria-current="step"' : "";
      return [
        '<li class="single-item-stage ' + escapeMarkup(stage.state) + '"',
        ' data-single-item-stage="' + escapeMarkup(stage.id) + '"',
        ' data-stage-state="' + escapeMarkup(stage.state) + '"' + current + ">",
        '<span class="single-item-stage-icon" aria-hidden="true">' + escapeMarkup(stateIcons[stage.state]) + "</span>",
        '<span class="single-item-stage-copy">',
        '<span class="single-item-stage-name">' + (index + 1) + ". " + escapeMarkup(stage.label) + "</span>",
        "<strong>" + escapeMarkup(stage.statusLabel) + "</strong>",
        "</span></li>",
      ].join("");
    }).join("");
  }

  function partialMarkup(summary) {
    if (!summary) {
      return "";
    }
    return [
      "<strong>现有结果仍可继续查看</strong>",
      "<p>已确认 " + summary.successfulCount + " 项结果可用，" + summary.failedCount + " 项失败或缺失。</p>",
      "<dl>",
      "<dt>未完成原因</dt><dd>" + escapeMarkup(summary.categories.join("、") || "状态暂时不可确认") + "</dd>",
      "<dt>可查看结果</dt><dd>" + escapeMarkup(summary.availableResults.join("、") || "已保留结果") + "</dd>",
      "</dl>",
    ].join("");
  }

  function renderMarkup(viewModel) {
    const safeView = viewModel && Array.isArray(viewModel.stages) ? viewModel : derive();
    const summary = safeView.partialSummary
      ? '<div class="single-item-partial-summary">' + partialMarkup(safeView.partialSummary) + "</div>"
      : "";
    return [
      '<section class="single-item-status-card" aria-labelledby="single-item-status-title">',
      '<h3 id="single-item-status-title">任务进度</h3>',
      '<span class="single-item-overall-status">' + escapeMarkup(safeView.overallLabel) + "</span>",
      '<ol class="task-status-grid single-item-stage-list" aria-label="单作品任务进度">',
      stageItemsMarkup(safeView),
      "</ol>",
      summary,
      "</section>",
    ].join("");
  }

  function render(viewModel, elements = {}) {
    const safeView = viewModel && Array.isArray(viewModel.stages) ? viewModel : derive();
    if (elements.overall) {
      elements.overall.textContent = safeView.overallLabel;
    }
    if (elements.root) {
      const hasPartialStage = safeView.stages.some((stage) => stage.state === "partial");
      elements.root.dataset.overallStatus = safeView.unknown
        ? "unknown"
        : safeView.completeFailure
          ? "failed"
          : safeView.partialSummary || hasPartialStage
            ? "partial"
            : "normal";
      elements.root.setAttribute(
        "aria-busy",
        safeView.stages.some((stage) => stage.state === "active") ? "true" : "false",
      );
    }
    if (elements.stageList) {
      safeView.stages.forEach((stage) => {
        const item = elements.stageList.querySelector('[data-single-item-stage="' + stage.id + '"]');
        if (!item) {
          return;
        }
        item.className = "single-item-stage " + stage.state;
        item.dataset.stageState = stage.state;
        if (stage.state === "active") {
          item.setAttribute("aria-current", "step");
        } else {
          item.removeAttribute("aria-current");
        }
        const icon = item.querySelector(".single-item-stage-icon");
        const status = item.querySelector("strong");
        if (icon) {
          icon.textContent = stateIcons[stage.state];
        }
        if (status) {
          status.textContent = stage.statusLabel;
        }
      });
    }
    if (elements.partialSummary) {
      elements.partialSummary.classList.toggle("hidden", !safeView.partialSummary);
      elements.partialSummary.innerHTML = partialMarkup(safeView.partialSummary);
    }
    if (elements.announcement) {
      const activeStage = safeView.stages.find((stage) => stage.state === "active");
      const announcement = safeView.partialSummary
        ? safeView.overallLabel
          + "：" + safeView.partialSummary.successfulCount + " 项可用，"
          + safeView.partialSummary.failedCount + " 项未完成；"
          + safeView.partialSummary.categories.join("、") + "。"
        : activeStage
          ? safeView.overallLabel + "：" + activeStage.label + "，" + activeStage.statusLabel + "。"
          : safeView.overallLabel;
      if (elements.announcement.textContent !== announcement) {
        elements.announcement.textContent = announcement;
      }
    }
    return safeView;
  }

  global.SingleItemJobStatus = Object.freeze({derive, failureCategory, render, renderMarkup});
})(window);
// END SINGLE_ITEM_JOB_STATUS

// Settings
const settingsToggle = document.getElementById("settings-toggle");
const settingsModal = document.getElementById("settings-modal");
const settingsClose = document.getElementById("settings-close");
const singleForm = document.getElementById("single-form");
const singleButton = document.getElementById("single-button");
const singleResult = document.getElementById("single-result");
const qualityPreference = document.getElementById("quality-preference");
const singleItemStatusCard = document.getElementById("single-item-status-card");
const singleItemStageList = document.getElementById("single-item-stage-list");
const singleItemOverallStatus = document.getElementById("single-item-overall-status");
const singleItemPartialSummary = document.getElementById("single-item-partial-summary");
const singleItemStatusAnnouncement = document.getElementById("single-item-status-announcement");
const llmStatusBadge = document.getElementById("llm-status-badge");
const llmStatusList = document.getElementById("llm-status-list");
const llmConfigHint = document.getElementById("llm-config-hint");
const llmSettingsForm = document.getElementById("llm-settings-form");
const llmProviderInput = document.getElementById("llm-provider-input");
const llmApiBaseInput = document.getElementById("llm-api-base-input");
const llmModelInput = document.getElementById("llm-model-input");
const llmApiKeyInput = document.getElementById("llm-api-key-input");
const llmTimeoutInput = document.getElementById("llm-timeout-input");
const llmCreatorDistillTimeoutInput = document.getElementById("llm-creator-distill-timeout-input");
const llmFinalReduceTimeoutInput = document.getElementById("llm-final-reduce-timeout-input");
const llmQuickDistillBudgetInput = document.getElementById("llm-quick-distill-budget-input");
const llmDeepDistillBudgetInput = document.getElementById("llm-deep-distill-budget-input");
const llmBatchJobBudgetInput = document.getElementById("llm-batch-job-budget-input");
const llmFinalReduceReserveInput = document.getElementById("llm-final-reduce-reserve-input");
const llmCompactRetryMinInput = document.getElementById("llm-compact-retry-min-input");
const llmTemperatureInput = document.getElementById("llm-temperature-input");
const llmClearKeyInput = document.getElementById("llm-clear-key-input");
const saveLlmSettingsButton = document.getElementById("save-llm-settings-button");
const llmSaveResult = document.getElementById("llm-save-result");
const testLlmButton = document.getElementById("test-llm-button");
const llmTestResult = document.getElementById("llm-test-result");
const refreshPreflightButton = document.getElementById("refresh-preflight-button");
const preflightSummary = document.getElementById("preflight-summary");
const preflightList = document.getElementById("preflight-list");
const dataSourceStatusBadge = document.getElementById("data-source-status-badge");
const dataSourceStatusList = document.getElementById("data-source-status-list");
const loginStateStatusBadge = document.getElementById("login-state-status-badge");
const loginStateStatusList = document.getElementById("login-state-status-list");
const startLoginStatePairButton = document.getElementById("start-login-state-pair-button");
const refreshLoginStateButton = document.getElementById("refresh-login-state-button");
const loginStatePairResult = document.getElementById("login-state-pair-result");
const douyinSettingsForm = document.getElementById("douyin-settings-form");
const douyinCookieInput = document.getElementById("douyin-cookie-input");
const douyinUserAgentInput = document.getElementById("douyin-user-agent-input");
const douyinRefererInput = document.getElementById("douyin-referer-input");
const douyinClearCookieInput = document.getElementById("douyin-clear-cookie-input");
const saveDouyinSettingsButton = document.getElementById("save-douyin-settings-button");
const douyinSaveResult = document.getElementById("douyin-save-result");
const testDouyinCookieButton = document.getElementById("test-douyin-cookie-button");
const douyinCookieTestResult = document.getElementById("douyin-cookie-test-result");
const resultCard = document.getElementById("result-card");
const caseSummary = document.getElementById("case-summary");
const homeCaseView = document.getElementById("home-case-view");
const homeContactSheet = document.getElementById("home-contact-sheet");
const homeCaseMeta = document.getElementById("home-case-meta");
const homeAiStatus = document.getElementById("home-ai-status");
const homeAiReport = document.getElementById("home-ai-report");
const openFullCaseLink = document.getElementById("open-full-case-link");
const copyHomePromptButton = document.getElementById("copy-home-prompt-button");
const downloadHomeAnalysisInputButton = document.getElementById("download-home-analysis-input-button");
const uploadResult = document.getElementById("upload-result");
const buildCaseButton = document.getElementById("build-case-button");
const jobCard = document.getElementById("job-card");
const progressBar = document.getElementById("progress-bar");
const jobMessage = document.getElementById("job-message");
const jobPhase = document.getElementById("job-phase");
const jobResult = document.getElementById("job-result");
const homeRouteButtons = Array.from(document.querySelectorAll("[data-home-route]"));
const homePanels = Array.from(document.querySelectorAll("[data-home-panel]"));
const workbenchStatusPills = Array.from(document.querySelectorAll("[data-workbench-status]"));
const aiAssistantToggle = document.getElementById("ai-assistant-toggle");
const aiAssistantPanel = document.getElementById("ai-assistant-panel");
const aiAssistantClose = document.getElementById("ai-assistant-close");
const assistantCurrentStage = document.getElementById("assistant-current-stage");
const assistantMacroStep = document.getElementById("assistant-macro-step");
const assistantNextStep = document.getElementById("assistant-next-step");
const assistantHint = document.getElementById("assistant-hint");
const assistantCopyPromptButton = document.getElementById("assistant-copy-prompt-button");
const assistantStrategyPlanButton = document.getElementById("assistant-strategy-plan-button");

const profileForm = document.getElementById("profile-form");

// Creator Clone: import
const profileImportModeButtons = Array.from(document.querySelectorAll("[data-profile-import-mode]"));
const profileImportPanels = Array.from(document.querySelectorAll("[data-profile-import-panel]"));
const creatorCloneFlowSteps = Array.from(document.querySelectorAll("[data-profile-stage-nav]"));
const profileStageSections = Array.from(document.querySelectorAll("[data-profile-stage-section]"));
const creatorCloneNextBar = document.getElementById("creator-clone-next-bar");
const creatorCloneCurrentStep = document.getElementById("creator-clone-current-step");
const creatorCloneNextSummary = document.getElementById("creator-clone-next-summary");
const creatorCloneNextButton = document.getElementById("creator-clone-next-button");
const creatorCloneRecommendation = document.getElementById("creator-clone-recommendation");
const profilePublicSection = document.getElementById("profile-public-section");
const profileSort = document.getElementById("profile-sort");
const profileMediaFilter = document.getElementById("profile-media-filter");
const profileEvidenceFilter = document.getElementById("profile-evidence-filter");
const profileScanButton = document.getElementById("profile-scan-button");
const profileBrowserHelperButton = document.getElementById("profile-browser-helper-button");
const profileChromeStatus = document.getElementById("profile-chrome-status");
const profileChromeConfirm = document.getElementById("profile-chrome-confirm");
const profileSelectedBuildButton = document.getElementById("profile-selected-build-button");
const profileSelectAllButton = document.getElementById("profile-select-all-button");
const profileClearSelectionButton = document.getElementById("profile-clear-selection-button");
const profilePresetKind = document.getElementById("profile-preset-kind");
const profileContinueChromeButton = document.getElementById("profile-continue-chrome-button");
const profileAutoDistill = document.getElementById("profile-auto-distill");
const profileScanStatus = document.getElementById("profile-scan-status");
const profileFallbackHint = document.getElementById("profile-fallback-hint");
const profileManualSection = document.getElementById("profile-manual-section");
const profileManualLinks = document.getElementById("profile-manual-links");
const profileHandoffFile = document.getElementById("profile-handoff-file");
const profileHandoffManifest = document.getElementById("profile-handoff-manifest");
const profileResultsCard = document.getElementById("profile-results-card");
const profileProviderBadge = document.getElementById("profile-provider-badge");
const profileWarnings = document.getElementById("profile-warnings");
const profileQuickInput = document.getElementById("profile-quick-input");
const profileScanPanel = document.querySelector(".profile-scan-panel");
const profileCaptureAudit = document.getElementById("profile-capture-audit");
const profileSummary = document.getElementById("profile-summary");
const profileNextAction = document.getElementById("profile-next-action");
const profileDecisionBoard = document.getElementById("profile-decision-board");
const profileSegmentsPreview = document.getElementById("profile-segments-preview");
const profileResultsBody = document.getElementById("profile-results-body");
const profileEnrichmentSection = document.getElementById("profile-enrichment-section");
const profileDistillationSection = document.getElementById("profile-distillation-section");
const profileQueueCard = document.getElementById("profile-queue-card");
const profileQueueSummary = document.getElementById("profile-queue-summary");
const profileQueueItems = document.getElementById("profile-queue-items");
const creatorCloneDistillButton = document.getElementById("creator-clone-distill-button");
const creatorCloneBatchDistillButton = document.getElementById("creator-clone-batch-distill-button");
const profileContentProfile = document.getElementById("profile-content-profile");
const profileDistillMode = document.getElementById("profile-distill-mode");
const creatorCloneSelectionStatus = document.getElementById("creator-clone-selection-status");
const profileEvidenceStatus = document.getElementById("profile-evidence-status");
const profileDistillReadinessStatus = document.getElementById("profile-distill-readiness");
const creatorCloneResultCard = document.getElementById("creator-clone-result-card");
const creatorCloneResult = document.getElementById("creator-clone-result");
const creatorCloneConfidence = document.getElementById("creator-clone-confidence");
const creatorCloneExportActions = document.getElementById("creator-clone-export-actions");
const copyCreatorCloneSpecButton = document.getElementById("copy-creator-clone-spec-button");
const copyDistillPromptButton = document.getElementById("copy-distill-prompt-button");
const downloadCreatorCloneJson = document.getElementById("download-creator-clone-json");
const downloadCreatorCloneMd = document.getElementById("download-creator-clone-md");
const creatorStrategyPlanCard = document.getElementById("creator-strategy-plan-card");
const generateCreatorStrategyButton = document.getElementById("generate-creator-strategy-button");
const creatorStrategyPlanStatus = document.getElementById("creator-strategy-plan-status");
const creatorStrategyPlanResult = document.getElementById("creator-strategy-plan-result");
const PROFILE_BUILD_MAX_ITEMS = Math.max(1, Number(document.body.dataset.profileBuildMaxItems || 10));
const CREATOR_CLONE_MAX_DISTILL_SAMPLES = Math.max(1, Number(document.body.dataset.creatorCloneMaxDistillSamples || 20));
const HANDOFF_MANIFEST_MAX_BYTES = 2 * 1024 * 1024;
const WORKBENCH_TASK_STALE_SECONDS = 30 * 60;

document.querySelectorAll(".summary-actions").forEach((container) => {
  container.addEventListener("click", (event) => {
    const action = event.target.closest("button, a");
    if (!action) {
      return;
    }
    if (action.tagName === "BUTTON") {
      event.preventDefault();
    }
    const submitter = event.target.closest('button[type="submit"]');
    event.stopPropagation();
    if (submitter?.form) {
      event.preventDefault();
      if (submitter.form.requestSubmit) {
        submitter.form.requestSubmit(submitter);
      } else {
        submitter.form.dispatchEvent(new Event("submit", {bubbles: true, cancelable: true}));
      }
    }
  });
});

let currentLocalVideoId = "";
let currentAwemeId = "";
let selectedCandidate = null;
let loadedHomeCase = null;
let currentSingleJob = null;
let singleItemFlow = {stage: "idle", status: "pending", error_code: ""};
let singleItemObservationGeneration = 0;
let singleItemActiveJobId = "";
let currentJobCardScope = "profile";
let activeHomeRoute = "";
let runtimeSampleRows = [];
let profileSelectedKeys = new Set();
let profileScanPayload = null;
let currentCloneSetId = "";
let currentDistillPrompt = "";
let currentCreatorRuntimeReport = null;
let currentCreatorIntelligenceProject = null;
let currentCreatorIntelligenceStrategy = null;
let currentCreatorIntelligenceResult = null;
let currentCreatorRuntimeState = null;
let currentRepresentativeSampleSelection = null;
let representativeRecommendationState = "idle";
let representativeRecommendationMessage = "";
let representativeRecommendationGeneration = 0;
let chromeHelperStatusLoaded = false;
let profileLastChromeProfileValue = "";
let profileChromeLaunchCommand = "";
let profileChromeAvailable = false;
let creatorCloneEnrichmentRunning = false;
let creatorCloneDistillRunning = false;
let creatorCloneNextActionRunning = false;
let activeProfileBuildJobId = "";
let activeProfileBuildJobStatus = "";
let activeProfileBuildJobUpdatedAt = "";
let activeProfileBuildLastResult = null;
let creatorCloneSelectionSyncTimer = 0;
let profileStageView = "import";
let currentCloneProfileFingerprint = "";
let profileQuickInputRestoredValue = "";
let preflightCopySnippets = [];
let recentCreatorCloneRestoreAttempted = false;

const RECENT_CREATOR_CLONE_SET_STORAGE_KEY = "shortVideoAgent.recentCreatorCloneSetId";
const RECENT_PROFILE_BUILD_STATE_STORAGE_KEY = "shortVideoAgent.recentProfileBuildState";
const RECENT_PROFILE_STAGE_STORAGE_KEY = "shortVideoAgent.recentProfileStage";
const REPRESENTATIVE_SAMPLE_TARGET_COUNT = 6;
const REPRESENTATIVE_ROLE_LABELS = Object.freeze({
  BREAKOUT_HIT: "爆款代表",
  COMMENT_MAGNET: "高讨论",
  SAVE_SHARE_VALUE: "收藏/转发",
  RECENT_WINNER: "近期高表现",
  DIVERSITY_ANCHOR: "内容差异",
  BASELINE_TYPICAL: "普通基线",
});
const representativeSampleSelectorUi = window.RepresentativeSampleSelectorUI || null;

const creatorReportView = window.CreatorReportView?.createRenderer({
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
}) || null;

function renderSingleItemStatus({job = currentSingleJob, caseData = loadedHomeCase, flow = singleItemFlow} = {}) {
  const statusView = window.SingleItemJobStatus?.derive({job, caseData, flow});
  if (!statusView) {
    return null;
  }
  return window.SingleItemJobStatus.render(statusView, {
    root: singleItemStatusCard,
    stageList: singleItemStageList,
    overall: singleItemOverallStatus,
    partialSummary: singleItemPartialSummary,
    announcement: singleItemStatusAnnouncement,
  });
}

function startSingleItemObservation(jobId = "") {
  singleItemObservationGeneration += 1;
  singleItemActiveJobId = String(jobId || "").trim();
  return singleItemObservationGeneration;
}

function isCurrentSingleItemObservation(jobId, generation) {
  return generation === singleItemObservationGeneration
    && String(jobId || "").trim() === singleItemActiveJobId;
}

function bindSingleItemObservation(jobId, generation) {
  const nextJobId = String(jobId || "").trim();
  if (!nextJobId || !isCurrentSingleItemObservation("", generation)) {
    return false;
  }
  singleItemActiveJobId = nextJobId;
  return true;
}

function stopSingleItemObservation() {
  startSingleItemObservation();
  singleButton.disabled = false;
  singleButton.textContent = "解析";
  buildCaseButton.disabled = false;
}

function setSingleItemFlow(stage, status = "active", errorCode = "") {
  singleItemFlow = {stage, status, error_code: errorCode};
  return renderSingleItemStatus();
}

function singleItemFailureCategory(error, source = "") {
  return window.SingleItemJobStatus?.failureCategory(error?.error_code, source)
    || "状态暂时不可确认";
}

function singleItemJobMessage(job, fallbackMessage = "") {
  if (job?.status === "failed") {
    return singleItemFailureCategory(job, "");
  }
  if (["stale", "recoverable"].includes(job?.status)) {
    return "状态暂时无法确认，已保留结果仍可查看";
  }
  return fallbackMessage || {
    pending: "任务已接收",
    running: "正在处理单作品",
    success: "任务处理完成",
  }[job?.status] || "状态更新中";
}

renderSingleItemStatus();

function setHomeRoute(route, updateHash = true) {
  const activeRoute = window.WorkbenchShell?.normalizeRoute(route)
    || (["workbench", "single", "profile"].includes(route) ? route : "workbench");
  if (activeHomeRoute === "single" && activeRoute !== "single") {
    stopSingleItemObservation();
  }
  activeHomeRoute = activeRoute;
  const visiblePanelRoute = activeRoute;
  homePanels.forEach((panel) => {
    panel.classList.toggle("hidden", panel.dataset.homePanel !== visiblePanelRoute);
  });
  homeRouteButtons.forEach((button) => {
    const isNavItem = button.classList.contains("workbench-nav-item");
    const active = isNavItem && button.dataset.homeRoute === activeRoute && !button.dataset.workbenchFocus;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "page" : "false");
  });
  const hashRoute = window.location.hash.replace(/^#/, "").trim().toLowerCase();
  const shouldRepairHash = Boolean(window.location.hash) && !["workbench", "single", "profile"].includes(hashRoute);
  if (updateHash || shouldRepairHash) {
    history.replaceState(null, "", `#${activeRoute}`);
  }
  if (visiblePanelRoute === "profile" && !chromeHelperStatusLoaded) {
    chromeHelperStatusLoaded = true;
    loadChromeHelperStatus({silent: true}).catch(() => {
      if (profileChromeStatus) {
        profileChromeStatus.textContent = "本机 Chrome 辅助状态：检测失败，可直接使用公开扫描或兜底导入。";
      }
    });
  }
  if (visiblePanelRoute === "profile") {
    restoreRecentCreatorCloneSet().catch(() => {});
  }
  updateAssistantContext(activeRoute);
}

function routeFromHash() {
  return window.WorkbenchShell?.routeFromHash(window.location.hash)
    || window.location.hash.replace("#", "")
    || "workbench";
}

function isSafeCreatorCloneSetId(value) {
  return /^clone_[a-f0-9]{32}$/i.test(String(value || ""));
}

function isSafeJobId(value) {
  return /^job_[a-f0-9-]+$/i.test(String(value || ""));
}

function readRecentCreatorCloneSetId() {
  try {
    const value = window.localStorage?.getItem(RECENT_CREATOR_CLONE_SET_STORAGE_KEY) || "";
    return isSafeCreatorCloneSetId(value) ? value : "";
  } catch {
    return "";
  }
}

function rememberRecentCreatorCloneSetId(setId) {
  if (!isSafeCreatorCloneSetId(setId)) {
    return;
  }
  try {
    window.localStorage?.setItem(RECENT_CREATOR_CLONE_SET_STORAGE_KEY, setId);
  } catch {
    // Browser storage can be disabled; restoring the recent pool is optional.
  }
}

function readRecentProfileBuildState() {
  try {
    const raw = window.localStorage?.getItem(RECENT_PROFILE_BUILD_STATE_STORAGE_KEY) || "";
    const value = raw ? JSON.parse(raw) : {};
    const setId = isSafeCreatorCloneSetId(value.set_id) ? value.set_id : "";
    const jobId = isSafeJobId(value.job_id) ? value.job_id : "";
    const selectedSampleIds = normalizeItems(value.selected_sample_ids)
      .map((item) => String(item || ""))
      .filter(Boolean);
    return setId ? {set_id: setId, job_id: jobId, selected_sample_ids: selectedSampleIds} : null;
  } catch {
    return null;
  }
}

function readRecentProfileStage() {
  try {
    return normalizeProfileStage(window.localStorage?.getItem(RECENT_PROFILE_STAGE_STORAGE_KEY) || "pool");
  } catch {
    return "pool";
  }
}

function rememberRecentProfileStage(stage) {
  try {
    window.localStorage?.setItem(RECENT_PROFILE_STAGE_STORAGE_KEY, normalizeProfileStage(stage));
  } catch {
    // Stage restore is optional.
  }
}

function rememberRecentProfileBuildState({setId = "", jobId = "", selectedSampleIds = []} = {}) {
  if (!isSafeCreatorCloneSetId(setId)) {
    return;
  }
  try {
    window.localStorage?.setItem(RECENT_PROFILE_BUILD_STATE_STORAGE_KEY, JSON.stringify({
      set_id: setId,
      job_id: isSafeJobId(jobId) ? jobId : "",
      selected_sample_ids: normalizeItems(selectedSampleIds).map((item) => String(item || "")).filter(Boolean),
      saved_at: new Date().toISOString(),
    }));
  } catch {
    // Restoring an in-flight queue is optional.
  }
}

function forgetRecentProfileBuildState() {
  try {
    window.localStorage?.removeItem(RECENT_PROFILE_BUILD_STATE_STORAGE_KEY);
  } catch {
    // Ignore storage failures.
  }
}

function forgetRecentProfileStage() {
  try {
    window.localStorage?.removeItem(RECENT_PROFILE_STAGE_STORAGE_KEY);
  } catch {
    // Ignore storage failures.
  }
}

function forgetRecentCreatorCloneSetId() {
  try {
    window.localStorage?.removeItem(RECENT_CREATOR_CLONE_SET_STORAGE_KEY);
  } catch {
    // Ignore storage failures; they should not affect the main workflow.
  }
  forgetRecentProfileBuildState();
  forgetRecentProfileStage();
}

async function restoreRecentCreatorCloneSet(options = {}) {
  if (recentCreatorCloneRestoreAttempted || currentCloneSetId || activeCreatorSampleViewItems().length) {
    return false;
  }
  recentCreatorCloneRestoreAttempted = true;
  const setId = readRecentCreatorCloneSetId();
  if (!setId) {
    return false;
  }
  if (profileScanStatus) {
    profileScanStatus.textContent = "正在恢复上次素材池...";
  }
  try {
    const response = await fetch(`/api/creator-clone/sets/${encodeURIComponent(setId)}`, {cache: "no-store"});
    const payload = await readJsonResponse(response);
    const profilePayload = payload.set ? payload : profilePayloadFromCreatorIntelligenceProject(payload);
    renderProfileResults(profilePayload);
    setCreatorCloneRestoredInput(creatorCloneSourceInputFromPayload(profilePayload));
    if (payload.result && Object.keys(payload.result).length) {
      forgetRecentProfileBuildState();
      renderCreatorCloneResult(payload.result, payload.set, payload.prompt || "", payload.exports || {}, {scroll: false});
      setProfileStageView("export");
      if (profileScanStatus) {
        profileScanStatus.textContent = "已恢复上次创作者蒸馏报告。";
      }
      return true;
    }
    const restoredQueue = options.restoreQueue === false
      ? false
      : await restoreRecentProfileBuildJob(setId, {
          pollActive: options.pollActive !== false,
        });
    if (!restoredQueue) {
      const selected = selectedCreatorSampleViewItems();
      const restoredStage = readRecentProfileStage();
      const fallbackStage = selected.length
        ? (["select", "enrich", "distill", "export"].includes(restoredStage) ? restoredStage : "select")
        : "pool";
      setProfileStageView(fallbackStage);
      if (profileScanStatus) {
        const itemCount = activeCreatorSampleViewItems().length;
        profileScanStatus.textContent = selected.length
          ? `已恢复上次素材池和 ${formatNumber(selected.length)} 条已选样本。`
          : `已恢复上次素材池：${formatNumber(itemCount)} 条素材。`;
      }
    }
    return true;
  } catch {
    forgetRecentCreatorCloneSetId();
    if (profileScanStatus) {
      profileScanStatus.textContent = "上次素材池无法恢复，请重新导入或扫描。";
    }
    return false;
  }
}

async function restoreRecentProfileBuildJob(setId, options = {}) {
  const state = readRecentProfileBuildState();
  const shouldUseStoredJob = state && state.set_id === setId && state.job_id;
  const selectedKeys = new Set(shouldUseStoredJob ? state.selected_sample_ids : []);
  if (!selectedKeys.size && state && state.set_id === setId) {
    normalizeItems(state.selected_sample_ids).forEach((key) => {
      if (key) selectedKeys.add(key);
    });
  }
  if (selectedKeys.size) {
    setProfileSelection(activeCreatorSampleViewItems().filter((item) => sampleViewItemMatchesKeySet(item, selectedKeys)));
  }
  try {
    if (options.safeStatus && !shouldUseStoredJob) {
      return false;
    }
    let job = null;
    if (options.safeStatus) {
      job = await fetchWorkbenchJob(state.job_id);
    } else {
      const jobUrl = shouldUseStoredJob
        ? `/api/jobs/${encodeURIComponent(state.job_id)}`
        : `/api/jobs/profile-build-cases/recent?sample_set_id=${encodeURIComponent(setId)}`;
      const response = await fetch(jobUrl, {cache: "no-store"});
      const payload = await readJsonResponse(response);
      job = payload.job || null;
    }
    job = job || {};
    if (job.type !== "profile-build-cases") {
      forgetRecentProfileBuildState();
      return false;
    }
    const resultItems = normalizeItems(job.result_json?.items);
    if (!selectedKeys.size && resultItems.length) {
      const queueKeys = new Set(resultItems.map(sampleViewItemKey).filter(Boolean));
      setProfileSelection(activeCreatorSampleViewItems().filter((item) => sampleViewItemMatchesKeySet(item, queueKeys)));
    }
    rememberRecentProfileBuildState({
      setId,
      jobId: job.id,
      selectedSampleIds: selectedCreatorSampleViewItems().map(sampleViewItemKey),
    });
    if (!placeJobCard("profile")) {
      return false;
    }
    renderJobStatus(job, "恢复素材包队列");
    if (job.result_json && Object.keys(job.result_json).length) {
      renderProfileQueue(job.result_json);
    } else {
      renderProfileQueue({items: selectedCreatorSampleViewItems().map((item) => ({
        ...queueItemPayload(item),
        status: "pending",
        message: "等待后端写入队列状态",
      }))});
    }
    if (options.safeStatus && job.status === "stale") {
      clearActiveProfileBuildJob(job.id);
      setProfileStageView("enrich", {scroll: false});
      profileScanStatus.textContent = "证据富化任务可能已停止更新。当前只展示保存状态，不会自动轮询、重试或进入大模型蒸馏。";
      return true;
    }
    if (job.status === "running" || job.status === "pending") {
      if (options.pollActive === false) {
        clearActiveProfileBuildJob(job.id);
        setProfileStageView("enrich", {scroll: false});
        profileScanStatus.textContent = "已恢复任务最后一次保存的证据富化队列。当前只展示状态，不会自动轮询、重试或修改任务。";
        return true;
      }
      setActiveProfileBuildJob(job);
      setProfileStageView("enrich", {scroll: false});
      setCreatorCloneEnrichmentLocked(true);
      profileScanStatus.textContent = isProfileBuildJobStale(job)
        ? "已恢复上次证据富化队列，但任务较长时间没有更新；如果进度不再变化，可重新点击富化，已有素材包会复用。"
        : "已恢复正在运行的证据富化队列；刷新页面不会取消后台任务，请等待进度更新，不需要重新点击。";
      pollProfileQueue(job.id, {
        allowAutoDistill: options.allowAutoDistill !== false,
        safeStatus: options.safeStatus === true,
        setId,
      }).finally(() => {
        setCreatorCloneEnrichmentLocked(false);
        updateCreatorCloneSelectionStatus();
        renderCreatorCloneNextAction();
      });
      return true;
    }
    clearActiveProfileBuildJob(job.id);
    if (job.status === "success") {
      if (options.safeStatus) {
        await refreshProfilePoolFromPersistedSet(setId);
      } else if (job.result_json?.set) {
        refreshProfilePoolFromSet(job.result_json.set);
      }
      setProfileStageView("distill", {scroll: false});
      profileScanStatus.textContent = "已恢复上次完成的证据富化队列，可继续进入大模型蒸馏。";
      return true;
    }
    if (job.status === "failed") {
      setProfileStageView("enrich", {scroll: false});
      profileScanStatus.textContent = `${job.error_code || "ERROR"}：${job.message || "上次证据富化失败"}`;
      return true;
    }
    return false;
  } catch {
    forgetRecentProfileBuildState();
    return false;
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function firstUrlFromText(value) {
  const match = String(value || "").match(/https?:\/\/[^\s]+/i);
  return match ? match[0] : "";
}

function urlsFromText(value) {
  return String(value || "").match(/https?:\/\/[^\s]+/gi) || [];
}

function firstDouyinProfileTargetFromText(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return "";
  }
  const urls = urlsFromText(raw);
  const profileUrl = urls.find((url) => /douyin\.com\/user\//i.test(url));
  if (profileUrl) {
    return profileUrl;
  }
  const likelyProfileShortLink = urls.find((url) => /v\.douyin\.com/i.test(url));
  if (likelyProfileShortLink && urls.length === 1 && /更多作品|TA的更多作品|主页|账号|博主/i.test(raw)) {
    return likelyProfileShortLink;
  }
  const secMatch = raw.match(/\bMS4w[A-Za-z0-9_.-]+\b/);
  if (secMatch) {
    return secMatch[0];
  }
  return "";
}

function douyinProfileFingerprint(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return "";
  }
  const firstUrl = firstUrlFromText(raw) || raw;
  const secMatch = firstUrl.match(/MS4w[A-Za-z0-9_.-]+/);
  if (secMatch) {
    return `sec:${secMatch[0]}`;
  }
  try {
    const parsed = new URL(firstUrl);
    const host = parsed.hostname.toLowerCase();
    if (host === "douyin.com" || host.endsWith(".douyin.com")) {
      const pathMatch = parsed.pathname.match(/\/user\/([^/?#]+)/i);
      if (pathMatch?.[1]) {
        return `path:/user/${decodeURIComponent(pathMatch[1])}`;
      }
    }
  } catch {
    // The input may be a raw sec_user_id; the regex above already handles that path.
  }
  return "";
}

function profileFingerprintFromPayload(payload) {
  const set = payload?.set || payload || {};
  const meta = set.profile_metadata || payload?.summary?.profile_metadata || {};
  const audit = payload?.capture_audit || set.capture_audit || {};
  return douyinProfileFingerprint(meta.sec_user_id)
    || douyinProfileFingerprint(meta.profile_url)
    || douyinProfileFingerprint(audit.requested_profile)
    || "";
}

function collectCreatorCloneProfileInputCandidates(payload = {}) {
  const set = payload?.set || payload || {};
  const meta = set.profile_metadata || payload?.summary?.profile_metadata || {};
  const audit = payload?.capture_audit || set.capture_audit || {};
  const handoff = payload?.handoff_manifest || set.handoff_manifest || {};
  const handoffMeta = handoff.profile_metadata || {};
  const projectProfile = payload?.creator_intelligence?.project?.profile || payload?.project?.profile || {};
  const rawProfile = projectProfile.raw_profile || {};
  return [
    meta.source_input,
    meta.profile_url,
    meta.source_url,
    audit.requested_profile,
    audit.profile_url,
    audit.profile_metadata?.profile_url,
    handoff.requested_profile,
    handoff.profile_url,
    handoffMeta.profile_url,
    projectProfile.source_url,
    rawProfile.profile_url,
    meta.sec_user_id,
    handoffMeta.sec_user_id,
    rawProfile.sec_user_id,
    projectProfile.creator_id,
  ].map((value) => String(value || "").trim()).filter(Boolean);
}

function creatorCloneSourceInputFromPayload(payload = {}) {
  const set = payload?.set || payload || {};
  const candidates = collectCreatorCloneProfileInputCandidates(payload);
  const profileValue = candidates.find((value) => /douyin\.com\/user\//i.test(value))
    || candidates.find((value) => /^MS4w[A-Za-z0-9_.-]+/.test(value))
    || candidates.find((value) => /douyin\.com/i.test(value) && !/\/video\//i.test(value))
    || "";
  if (profileValue) {
    return profileValue;
  }
  const sourceUrls = [];
  normalizeItems(payload.items || set.samples).forEach((item) => {
    const sourceUrl = String(item?.source_url || item?.webpage_url || "").trim();
    if (sourceUrl && !sourceUrls.includes(sourceUrl)) {
      sourceUrls.push(sourceUrl);
    }
  });
  if (sourceUrls.length > 20) {
    return "";
  }
  return sourceUrls.slice(0, 150).join("\n");
}

function clearCreatorCloneRenderedReport({clearPrompt = true} = {}) {
  currentCreatorRuntimeReport = null;
  currentCreatorIntelligenceResult = null;
  if (clearPrompt) {
    currentDistillPrompt = "";
  }
  if (creatorCloneResult) {
    creatorCloneResult.innerHTML = "";
  }
  if (creatorCloneConfidence) {
    creatorCloneConfidence.textContent = "";
  }
  if (downloadCreatorCloneMd) {
    downloadCreatorCloneMd.href = "#";
    downloadCreatorCloneMd.textContent = "打开网页报告";
  }
  if (downloadCreatorCloneJson) {
    downloadCreatorCloneJson.href = "#";
  }
  creatorCloneResultCard?.classList.add("hidden");
}

function resetCreatorClonePoolForNewProfile({clearInput = true} = {}) {
  currentCloneSetId = "";
  currentCloneProfileFingerprint = "";
  runtimeSampleRows = [];
  profileSelectedKeys = new Set();
  profileScanPayload = null;
  clearActiveProfileBuildJob();
  clearCreatorCloneRenderedReport();
  currentCreatorIntelligenceProject = null;
  currentCreatorIntelligenceStrategy = null;
  currentCreatorRuntimeState = null;
  currentRepresentativeSampleSelection = null;
  representativeRecommendationState = "idle";
  representativeRecommendationMessage = "";
  representativeRecommendationGeneration += 1;
  profileLastChromeProfileValue = "";
  if (clearInput) {
    clearCreatorCloneUnifiedInput();
  } else {
    profileQuickInputRestoredValue = "";
  }
  forgetRecentCreatorCloneSetId();
  if (profileResultsBody) {
    profileResultsBody.innerHTML = "";
  }
  if (profileSummary) {
    profileSummary.innerHTML = "";
  }
  if (profileQueueSummary) {
    profileQueueSummary.innerHTML = "";
  }
  if (profileQueueItems) {
    profileQueueItems.innerHTML = "";
  }
  if (creatorCloneSelectionStatus) {
    creatorCloneSelectionStatus.textContent = "已选 0 条。";
  }
  renderCreatorCloneRecommendation();
  if (profileProviderBadge) {
    profileProviderBadge.textContent = "未导入";
  }
  if (profileWarnings) {
    profileWarnings.textContent = "";
    profileWarnings.classList.add("hidden");
  }
  profileQueueCard?.classList.add("hidden");
  profileResultsCard?.classList.add("hidden");
}

function enterCreatorCloneFreshImport({preserveInput = true, scroll = true} = {}) {
  resetCreatorClonePoolForNewProfile({clearInput: !preserveInput});
  setProfileStageView("import", {scroll});
  profileQuickInput?.focus();
  renderCreatorCloneNextAction();
}

function enterCreatorCloneImportView({scroll = true} = {}) {
  setProfileStageView("import", {scroll});
  profileQuickInput?.focus();
  renderCreatorCloneNextAction();
}

function resetCreatorClonePoolIfProfileChanged(profileValue) {
  const nextFingerprint = douyinProfileFingerprint(profileValue);
  if (!nextFingerprint || !currentCloneProfileFingerprint || nextFingerprint === currentCloneProfileFingerprint) {
    return false;
  }
  resetCreatorClonePoolForNewProfile();
  return true;
}

function showJson(element, payload) {
  element.textContent = JSON.stringify(payload, null, 2);
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("zh-CN");
}

function formatSeconds(value) {
  const number = Number(value || 0);
  return number ? `${number.toFixed(2)} 秒` : "未知";
}

function formatBytes(value) {
  const number = Number(value || 0);
  if (!number) {
    return "未知";
  }
  if (number >= 1024 * 1024) {
    return `${(number / 1024 / 1024).toFixed(2)} MB`;
  }
  return `${Math.round(number / 1024)} KB`;
}

function renderDefinitionList(element, rows) {
  element.innerHTML = `
    <dl>
      ${rows
        .filter(([, value]) => value !== undefined && value !== null && value !== "")
        .map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`)
        .join("")}
    </dl>
  `;
}

function placeJobCard(scope = "profile") {
  if (
    (scope === "single" && activeHomeRoute !== "single")
    || (scope === "profile" && activeHomeRoute !== "profile")
  ) {
    return false;
  }
  currentJobCardScope = scope;
  if (!jobCard) {
    return true;
  }
  if (scope === "single" && resultCard) {
    resultCard.insertAdjacentElement("afterend", jobCard);
    return true;
  }
  if (creatorCloneNextBar) {
    creatorCloneNextBar.insertAdjacentElement("afterend", jobCard);
  }
  return true;
}

function scrollProfileTaskPanel() {
  profileScanPanel?.scrollIntoView({behavior: "smooth", block: "start"});
}

function resetJobCard(message = "") {
  if (!jobCard || !progressBar || !jobMessage) {
    return;
  }
  jobCard.classList.remove("hidden");
  progressBar.style.width = "0%";
  jobMessage.className = "job-message";
  jobMessage.textContent = message;
  renderJobPhase(null);
  if (jobResult) {
    jobResult.textContent = "";
  }
}

function renderJobPhase(job) {
  if (!jobPhase) {
    return;
  }
  const result = job?.result_json || {};
  const phase = result.distill_phase || null;
  if (!phase) {
    jobPhase.classList.add("hidden");
    jobPhase.innerHTML = "";
    return;
  }
  const plan = phase.execution_plan || result.execution_plan || {};
  const timeoutPolicy = plan.timeout_policy || {};
  const timeout = phase.timeout_seconds || timeoutPolicy.recommended_batch_timeout_seconds || timeoutPolicy.configured_batch_timeout_seconds || "";
  const totalBudget = Number(phase.total_budget_seconds || timeoutPolicy.total_request_budget_seconds || 0);
  const budgetStartedAt = Date.parse(phase.budget_started_at || "");
  const deadlineAt = Date.parse(phase.deadline_at || "");
  const isRunningPhase = (phase.status || "running") === "running";
  const liveElapsed = isRunningPhase && Number.isFinite(budgetStartedAt)
    ? Math.max(Number(phase.elapsed_seconds || 0), Math.floor((Date.now() - budgetStartedAt) / 1000))
    : Number(phase.elapsed_seconds || 0);
  const liveRemaining = isRunningPhase && Number.isFinite(deadlineAt)
    ? Math.max(0, Math.ceil((deadlineAt - Date.now()) / 1000))
    : Number(phase.remaining_seconds || 0);
  const attemptLine = Number(phase.attempt_count || 0) && Number(phase.attempt_index || 0)
    ? `外部请求 ${formatNumber(phase.attempt_index || 0)} / ${formatNumber(phase.attempt_count)}`
    : "";
  const httpAttemptLine = Number(phase.http_attempt_count || 0)
    ? `HTTP 请求 ${formatNumber(phase.http_attempt_index || phase.http_attempt_count)} / ${formatNumber(phase.http_attempt_count)}`
    : "";
  const fallbackLine = phase.response_format_fallback_used
    ? "已使用 response_format 兼容回退"
    : "";
  const retryableLine = typeof phase.retryable === "boolean"
    ? `允许重试：${phase.retryable ? "是" : "否"}`
    : "";
  const failureLine = phase.failure_class
    ? `失败分类：${phase.failure_class}`
    : "";
  const recommendedBatchTimeout = timeoutPolicy.recommended_batch_timeout_seconds || "";
  const recommendedFinalTimeout = timeoutPolicy.recommended_final_reduce_timeout_seconds || "";
  const recommendedEnrichmentTimeout = timeoutPolicy.recommended_enrichment_timeout_seconds || "";
  const batchLine = Number(phase.batch_count || plan.batch_count || 0)
    ? `批次 ${phase.phase_index ? `${formatNumber(phase.phase_index)} / ` : ""}${formatNumber(phase.batch_count || plan.batch_count)}`
    : "";
  const timeoutLine = timeout
    ? `本次请求最多等待 ${formatNumber(timeout)} 秒`
    : "";
  const runtimeBudgetLine = totalBudget
    ? `总预算 ${formatNumber(totalBudget)} 秒 · 已等待 ${formatNumber(liveElapsed)} 秒 · 剩余约 ${formatNumber(liveRemaining)} 秒`
    : "";
  const budgetLine = [recommendedEnrichmentTimeout ? `富化建议 ${formatNumber(recommendedEnrichmentTimeout)} 秒` : "", recommendedBatchTimeout ? `单批建议 ${formatNumber(recommendedBatchTimeout)} 秒` : "", recommendedFinalTimeout ? `汇总建议 ${formatNumber(recommendedFinalTimeout)} 秒` : ""].filter(Boolean).join(" · ");
  const duration = plan.duration || {};
  const durationLine = Number(duration.known_count || 0)
    ? `已知视频时长 ${formatNumber(duration.known_count)} 条 · 总计 ${formatNumber(duration.total_seconds || 0)} 秒`
    : "";
  const basis = timeoutPolicy.basis || {};
  const promptLine = Number(basis.prompt_chars || plan.prompt_chars || 0)
    ? `Prompt 约 ${formatNumber(basis.prompt_chars || plan.prompt_chars)} 字符`
    : "";
  const components = basis.components_seconds || {};
  const componentLine = Object.keys(components).length
    ? `预算贡献：批次 ${formatNumber(components.batch_complexity || 0)}s · Prompt ${formatNumber(components.prompt_complexity || 0)}s · 样本 ${formatNumber(components.sample_complexity || 0)}s · 时长 ${formatNumber(components.duration_complexity || 0)}s`
    : "";
  const diagnostics = normalizeItems(plan.timeout_policy?.phase_diagnostics)
    .map((item) => item && typeof item === "object" ? `${item.phase}: ${item.meaning}` : formatReportValue(item))
    .filter(isMeaningfulReportText)
    .slice(0, 4);
  const chips = [
    plan.strategy_label || "",
    phase.current_phase_label || "",
    attemptLine,
    httpAttemptLine,
    fallbackLine,
    retryableLine,
    failureLine,
    batchLine,
    timeoutLine,
    runtimeBudgetLine,
    budgetLine,
    durationLine,
    promptLine,
    componentLine,
  ].filter(isMeaningfulReportText);
  jobPhase.classList.remove("hidden");
  jobPhase.innerHTML = `
    <div class="job-phase-header">
      <span>${escapeHtml(phase.current_phase_label || "运行阶段")}</span>
      ${phase.status ? `<strong>${escapeHtml(phase.status)}</strong>` : ""}
    </div>
    ${chips.length ? `<div class="job-phase-chips">${chips.map((chip) => `<span>${escapeHtml(chip)}</span>`).join("")}</div>` : ""}
    ${phase.diagnostic ? `<p>${escapeHtml(phase.diagnostic)}</p>` : ""}
    ${diagnostics.length ? `
      <details class="job-phase-diagnostics">
        <summary>超时诊断阶段</summary>
        <ul>${diagnostics.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      </details>
    ` : ""}
  `;
}

function renderJobStatus(job, fallbackMessage = "") {
  if (!progressBar || !jobMessage || !job) {
    return false;
  }
  if (
    (currentJobCardScope === "single" && activeHomeRoute !== "single")
    || (currentJobCardScope === "profile" && activeHomeRoute !== "profile")
  ) {
    return false;
  }
  if (currentJobCardScope === "single") {
    const previousJobId = String(currentSingleJob?.id || currentSingleJob?.task_id || "");
    const nextJobId = String(job.id || job.task_id || "");
    if (nextJobId !== singleItemActiveJobId) {
      return false;
    }
    const terminalRegression = Boolean(
      previousJobId
      && previousJobId === nextJobId
      && ["success", "failed"].includes(currentSingleJob?.status)
      && ["pending", "running", "stale"].includes(job.status),
    );
    if (terminalRegression) {
      return false;
    }
    const switchedJob = Boolean(previousJobId && nextJobId && previousJobId !== nextJobId);
    const reachedTerminal = Boolean(
      previousJobId
      && previousJobId === nextJobId
      && ["pending", "running", "stale"].includes(currentSingleJob?.status)
      && ["success", "failed"].includes(job.status),
    );
    if (switchedJob || reachedTerminal) {
      loadedHomeCase = null;
    }
    const result = job.result_json || job.result || {};
    const terminalCaseId = getCaseId(result);
    const loadedCaseId = String(loadedHomeCase?.case_id || "");
    const terminalCaseNeedsVerification = Boolean(
      job.type === "download-build-analyze-case"
      && ["success", "failed"].includes(job.status)
      && terminalCaseId
      && terminalCaseId !== loadedCaseId,
    );
    currentSingleJob = terminalCaseNeedsVerification
      ? {...job, __singleItemCaseVerificationPending: true}
      : job;
    renderSingleItemStatus();
  }
  progressBar.style.width = `${job.progress || 0}%`;
  jobMessage.className = `job-message ${job.status === "failed" ? "failed" : job.status === "success" ? "success" : ""}`;
  const message = currentJobCardScope === "single"
    ? singleItemJobMessage(job, fallbackMessage)
    : job.message || fallbackMessage || "";
  jobMessage.textContent = `${job.status || "running"} · ${job.progress || 0}% · ${message}`;
  renderJobPhase(job);
  return true;
}

function isProfileBuildJobActive() {
  return Boolean(activeProfileBuildJobId && ["pending", "running"].includes(activeProfileBuildJobStatus));
}

function parseBackendJobTimestampMilliseconds(value) {
  const candidate = String(value || "").trim();
  if (!candidate) {
    return 0;
  }
  const hasExplicitTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(candidate);
  const isNaiveBackendTimestamp = /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(candidate);
  const normalized = hasExplicitTimezone || !isNaiveBackendTimestamp
    ? candidate
    : `${candidate.replace(" ", "T")}Z`;
  const parsed = Date.parse(normalized);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function profileBuildJobAgeSeconds(job = {}, nowMilliseconds = Date.now()) {
  const updatedAt = job.updated_at || activeProfileBuildJobUpdatedAt || "";
  const updatedTime = parseBackendJobTimestampMilliseconds(updatedAt);
  if (!updatedTime) {
    return 0;
  }
  const currentTime = Number.isFinite(nowMilliseconds) ? nowMilliseconds : Date.now();
  return Math.max(0, Math.floor((currentTime - updatedTime) / 1000));
}

function isProfileBuildJobStale(job = {}, nowMilliseconds = Date.now()) {
  return ["pending", "running"].includes(job.status || activeProfileBuildJobStatus)
    && profileBuildJobAgeSeconds(job, nowMilliseconds) >= WORKBENCH_TASK_STALE_SECONDS;
}

function setActiveProfileBuildJob(job = {}) {
  activeProfileBuildJobId = isSafeJobId(job.id) ? job.id : activeProfileBuildJobId;
  activeProfileBuildJobStatus = job.status || activeProfileBuildJobStatus || "running";
  activeProfileBuildJobUpdatedAt = job.updated_at || activeProfileBuildJobUpdatedAt || new Date().toISOString();
}

function clearActiveProfileBuildJob(jobId = "") {
  if (jobId && activeProfileBuildJobId && jobId !== activeProfileBuildJobId) {
    return;
  }
  activeProfileBuildJobId = "";
  activeProfileBuildJobStatus = "";
  activeProfileBuildJobUpdatedAt = "";
  activeProfileBuildLastResult = null;
}

function setCreatorCloneDistillButtonsLocked(locked) {
  creatorCloneDistillRunning = Boolean(locked);
  if (creatorCloneDistillButton) {
    creatorCloneDistillButton.disabled = Boolean(locked);
  }
  if (creatorCloneBatchDistillButton) {
    creatorCloneBatchDistillButton.disabled = Boolean(locked);
  }
  renderCreatorCloneStageChrome();
}

function setCreatorCloneEnrichmentLocked(locked) {
  creatorCloneEnrichmentRunning = Boolean(locked);
  if (profileSelectedBuildButton) {
    profileSelectedBuildButton.disabled = Boolean(locked);
  }
  renderCreatorCloneStageChrome();
}

function normalizeItems(value) {
  if (!value) {
    return [];
  }
  if (Array.isArray(value)) {
    return value.filter((item) => item !== undefined && item !== null && item !== "");
  }
  return [value];
}

function sampleViewItemFromCreatorSample(sample = {}) {
  const metrics = sample.metrics || {};
  const evidence = sample.evidence || {};
  const raw = sample.raw || {};
  return {
    sample_id: sample.sample_id || raw.sample_id || "",
    source_type: sample.source || raw.source_type || "unknown",
    source_url: sample.source_url || raw.source_url || "",
    webpage_url: sample.source_url || raw.webpage_url || raw.source_url || "",
    aweme_id: sample.platform_item_id || raw.aweme_id || "",
    title: sample.title || raw.title || "",
    desc: sample.description || raw.desc || "",
    author: sample.author || raw.author || "",
    cover_url: sample.cover_url || raw.cover_url || "",
    media_type: sample.media_kind || raw.media_type || "unknown",
    duration: Number(raw.duration || 0),
    content_category: raw.content_category || "",
    like_count: Number(metrics.like_count || raw.like_count || 0),
    comment_count: Number(metrics.comment_count || raw.comment_count || 0),
    share_count: Number(metrics.share_count || raw.share_count || 0),
    collect_count: Number(metrics.collect_count || raw.collect_count || 0),
    view_count: Number(metrics.view_count || raw.view_count || 0),
    engagement_score: Number(metrics.engagement_score || raw.engagement_score || 0),
    create_time: sample.created_at || raw.create_time || "",
    case_id: sample.case_id || raw.case_id || "",
    understanding_level: evidence.level || raw.understanding_level || "metadata_only",
    has_video: Boolean(evidence.has_video || raw.has_video),
    has_frames: Boolean(evidence.has_frames || raw.has_frames),
    has_asr: Boolean(evidence.has_asr || raw.has_asr),
    has_ocr: Boolean(evidence.has_ocr || raw.has_ocr),
    has_comments: Boolean(evidence.has_comments || raw.has_comments),
    enrichment_status: evidence.enrichment_status || raw.enrichment_status || "pending",
    asr_status: evidence.asr_status || raw.asr_status || "pending",
    ocr_status: evidence.ocr_status || raw.ocr_status || "pending",
    analysis_status: evidence.analysis_status || raw.analysis_status || "not_analyzed",
    selected: Boolean(sample.selected || raw.selected),
    tags: normalizeItems(sample.tags || raw.tags),
    notes: raw.notes || "",
  };
}

function creatorSampleFromViewItem(item = {}) {
  const key = sampleViewItemKey(item);
  const evidenceLevel = item.understanding_level || (item.has_frames || item.has_asr || item.has_ocr || item.has_comments ? "partial" : "metadata_only");
  return {
    sample_id: key,
    source: item.source_type || "douyin",
    source_url: item.source_url || item.webpage_url || "",
    platform_item_id: item.aweme_id || "",
    title: item.title || item.desc || "",
    description: item.desc || "",
    author: item.author || "",
    cover_url: item.cover_url || "",
    media_kind: item.media_type || "unknown",
    metrics: {
      like_count: Number(item.like_count || 0),
      comment_count: Number(item.comment_count || 0),
      share_count: Number(item.share_count || 0),
      collect_count: Number(item.collect_count || 0),
      view_count: Number(item.view_count || 0),
      engagement_score: Number(item.engagement_score || 0),
    },
    evidence: {
      level: evidenceLevel,
      has_video: Boolean(item.has_video),
      has_frames: Boolean(item.has_frames),
      has_asr: Boolean(item.has_asr),
      has_ocr: Boolean(item.has_ocr),
      has_comments: Boolean(item.has_comments),
      enrichment_status: item.enrichment_status || "pending",
      asr_status: item.asr_status || "pending",
      ocr_status: item.ocr_status || "pending",
      analysis_status: item.analysis_status || "not_analyzed",
    },
    case_id: item.case_id || "",
    tags: normalizeItems(item.tags),
    created_at: item.create_time || "",
    selected: Boolean(item.selected),
    raw: {...item},
  };
}

function creatorProjectFromCloneSet(set = {}) {
  if (!set?.set_id) {
    return null;
  }
  const profile = set.profile_metadata || {};
  const samples = normalizeItems(set.samples).map(creatorSampleFromViewItem);
  const selected = normalizeItems(set.selected_sample_ids);
  return {
    project_id: set.set_id,
    title: set.title || "创作者蒸馏素材池",
    profile: {
      creator_id: profile.sec_user_id || set.creator_name || set.set_id,
      display_name: set.creator_name || profile.nickname || "",
      platform: set.source_platform || profile.source_platform || "unknown",
      source_url: profile.profile_url || "",
      bio: profile.bio || "",
      audience: profile.audience || "",
      content_direction: set.content_profile || profile.content_direction || "",
      style_bias: profile.style_bias || "",
      raw_profile: {...profile},
    },
    samples,
    selected_sample_ids: selected,
    warnings: normalizeItems(set.warnings),
    sample_count: samples.length,
    selected_count: selected.length || samples.filter((sample) => sample.selected).length,
    created_at: set.created_at || "",
    updated_at: set.updated_at || "",
  };
}

function creatorProjectSampleViewItems() {
  return normalizeItems(currentCreatorIntelligenceProject?.samples).map(sampleViewItemFromCreatorSample);
}

function activeCreatorSampleViewItems() {
  const projectItems = creatorProjectSampleViewItems();
  const localItems = normalizeItems(runtimeSampleRows);
  if (!projectItems.length) {
    return localItems;
  }
  if (!localItems.length) {
    return projectItems;
  }
  const localByKey = new Map(
    localItems
      .map((item) => [sampleViewItemKey(item), item])
      .filter(([key]) => Boolean(key)),
  );
  const merged = projectItems.map((item) => {
    const local = localByKey.get(sampleViewItemKey(item));
    return local ? {...item, ...local} : item;
  });
  const projectKeys = new Set(merged.map(sampleViewItemKey).filter(Boolean));
  localItems.forEach((item) => {
    const key = sampleViewItemKey(item);
    if (key && !projectKeys.has(key)) {
      merged.push(item);
    }
  });
  return merged;
}

function syncCreatorProjectSamplesFromViewItems(items = runtimeSampleRows) {
  if (!currentCreatorIntelligenceProject?.project_id) {
    return;
  }
  const rows = normalizeItems(items);
  const existingSelected = profileSelectedKeys.size
    ? new Set(profileSelectedKeys)
    : new Set(normalizeItems(currentCreatorIntelligenceProject.selected_sample_ids).map(String));
  const samples = rows.map((item) => {
    const key = sampleViewItemKey(item);
    return creatorSampleFromViewItem({
      ...item,
      selected: Boolean(key && existingSelected.has(String(key))),
    });
  });
  const availableKeys = new Set(samples.map((sample) => sample.sample_id).filter(Boolean));
  const selectedSampleIds = [...existingSelected].filter((key) => availableKeys.has(String(key)));
  currentCreatorIntelligenceProject = {
    ...currentCreatorIntelligenceProject,
    samples,
    selected_sample_ids: selectedSampleIds,
    sample_count: samples.length,
    selected_count: selectedSampleIds.length || samples.filter((sample) => sample.selected).length,
    updated_at: new Date().toISOString(),
  };
  if (currentCreatorRuntimeState) {
    currentCreatorRuntimeState = {
      ...currentCreatorRuntimeState,
      project: currentCreatorIntelligenceProject,
    };
  }
}

function invalidateCreatorRuntimeReportForSelectionChange() {
  clearCreatorCloneRenderedReport();
  currentCreatorIntelligenceStrategy = null;
  if (currentCreatorRuntimeState?.strategy_output) {
    currentCreatorRuntimeState = {
      ...currentCreatorRuntimeState,
      strategy_output: {},
    };
  }
  creatorCloneResultCard?.classList.add("hidden");
}

function cloneSetFromCreatorIntelligenceProject(payload = {}) {
  const project = payload.project || {};
  if (!project.project_id) {
    return null;
  }
  const profile = project.profile || {};
  const rawProfile = profile.raw_profile || {};
  return {
    set_id: project.project_id,
    title: project.title || "创作者蒸馏素材池",
    creator_name: profile.display_name || "",
    source_platform: profile.platform || "unknown",
    content_profile: rawProfile.content_profile || "auto",
    profile_metadata: {
      ...rawProfile,
      sec_user_id: rawProfile.sec_user_id || profile.creator_id || "",
      profile_url: rawProfile.profile_url || profile.source_url || "",
      bio: rawProfile.bio || profile.bio || "",
      source_platform: rawProfile.source_platform || profile.platform || "unknown",
    },
    samples: normalizeItems(project.samples).map(sampleViewItemFromCreatorSample),
    selected_sample_ids: normalizeItems(project.selected_sample_ids),
    warnings: normalizeItems(project.warnings),
    created_at: project.created_at || "",
    sample_count: project.sample_count || normalizeItems(project.samples).length,
    selected_count: project.selected_count || normalizeItems(project.selected_sample_ids).length,
    performance_segments: payload.behavior_model?.performance_segments || {},
  };
}

function profilePayloadFromCreatorIntelligenceProject(payload = {}) {
  return {
    set: cloneSetFromCreatorIntelligenceProject(payload),
    creator_intelligence: {
      project: payload.project || null,
      workflow: payload.workflow || null,
      behavior_model: payload.behavior_model || null,
      strategy_output: payload.strategy_output || null,
      result: payload.result || null,
      runtime_state: payload.runtime_state || null,
    },
    exports: payload.exports || {},
    provider: "creator intelligence project",
  };
}

function creatorStrategyFromResult(result = {}) {
  return result?.creator_clone_strategy || currentCreatorIntelligenceStrategy || null;
}

function creatorCloneResultFromStrategyOutput(strategy = {}) {
  if (!strategy || typeof strategy !== "object") {
    return null;
  }
  return {
    summary: strategy.positioning || "创作者策略输出已恢复。",
    creator_clone_strategy: strategy,
    creator_positioning: {
      what_the_creator_sells: strategy.positioning || "",
    },
    topic_buckets: normalizeItems(strategy.content_strategy).map((item) => ({name: formatReportValue(item)})),
    expression_patterns: {
      opening_hooks: normalizeItems(strategy.hooks),
    },
    transferable_formulas: normalizeItems(strategy.templates),
    creator_clone_spec: {
      anti_patterns: normalizeItems(strategy.anti_patterns),
      self_check_rubric: normalizeItems(strategy.validation_rules),
    },
    candidate_ideas: normalizeItems(strategy.idea_bank),
    evidence_gaps: [],
    next_actions: normalizeItems(strategy.validation_rules),
  };
}

function qualityLabelFromScore(score) {
  if (score === undefined || score === null || score === "") {
    return "待评估";
  }
  const numeric = Number(score);
  if (Number.isNaN(numeric)) {
    return "待评估";
  }
  if (numeric >= 85) return "高可信";
  if (numeric >= 70) return "可用，建议复核";
  if (numeric >= 50) return "低置信，需要补证据";
  return "占位/降级报告";
}

function creatorReportDiagnosticsFromResult(result = {}, overview = {}) {
  const quality = result.report_quality || {};
  const batch = result.batch_distill || {};
  const counts = overview.understanding_counts || result.sample_overview?.understanding_counts || {};
  const evidence = result.creator_report_view_model?.evidence_counts || {};
  const selectedCount = Number(evidence.selected_count ?? overview.selected_count ?? result.sample_overview?.selected_count ?? 0);
  const sampleCount = Number(evidence.sample_count ?? overview.sample_count ?? result.sample_overview?.sample_count ?? 0);
  const score = quality.quality_score ?? quality.score;
  const warnings = compactReportList(result.warnings, overview.warnings, result.sample_overview?.warnings).map(formatReportValue);
  const batchCount = Number(batch.batch_count || 0);
  const finalRecovery = batch.final_reduce_recovery || "";
  const isPromptOnly = !result.summary || result.summary === "创作者蒸馏完成。";
  const isFallback = Boolean(finalRecovery) || warnings.some((item) => item.includes("本地汇总") || item.includes("Reduce 未完成") || item.includes("最终汇总失败"));
  let sourceLabel = "大模型单次拆解";
  if (isFallback) {
    sourceLabel = "本地批次汇总 / 降级";
  } else if (batchCount) {
    sourceLabel = `分批大模型汇总（${batchCount} 批）`;
  } else if (selectedCount >= 2) {
    sourceLabel = "大模型 Map-Reduce";
  } else if (isPromptOnly) {
    sourceLabel = "Prompt-only / 待分析";
  }
  const coverage = {
    video: Number(evidence.with_video ?? overview.with_video ?? 0),
    keyframes: Number(evidence.with_keyframes ?? overview.with_keyframes ?? 0),
    asr: Number(evidence.with_asr ?? overview.with_asr ?? 0),
    ocr: Number(evidence.with_ocr ?? overview.with_ocr ?? 0),
    comments: Number(evidence.with_comments ?? overview.with_comments ?? 0),
  };
  const missing = [
    ["video", "视频"],
    ["keyframes", "关键帧"],
    ["asr", "ASR"],
    ["ocr", "OCR"],
    ["comments", "评论"],
  ].filter(([key]) => selectedCount && !coverage[key]).map(([, label]) => label);
  return {
    source_label: sourceLabel,
    is_fallback: isFallback || isPromptOnly,
    fallback_reason: isFallback
      ? (batch.final_reduce_error_code ? `最终 Reduce 失败：${batch.final_reduce_error_code}` : "最终汇总未完整返回，已使用批次摘要或本地规则兜底。")
      : isPromptOnly
        ? "未拿到可用大模型结果。"
        : "",
    quality_label: qualityLabelFromScore(score),
    quality_score: score ?? 0,
    selected_count: selectedCount,
    sample_count: sampleCount,
    understanding: {
      full: Number(counts.full || evidence.understanding_full || 0),
      partial: Number(counts.partial || evidence.understanding_partial || 0),
      metadata_only: Number(counts.metadata_only || evidence.understanding_metadata_only || 0),
    },
    coverage,
    coverage_text: selectedCount
      ? `视频 ${formatNumber(coverage.video)}/${formatNumber(selectedCount)} · 关键帧 ${formatNumber(coverage.keyframes)}/${formatNumber(selectedCount)} · ASR ${formatNumber(coverage.asr)}/${formatNumber(selectedCount)} · OCR ${formatNumber(coverage.ocr)}/${formatNumber(selectedCount)} · 评论 ${formatNumber(coverage.comments)}/${formatNumber(selectedCount)}`
      : "尚未选择样本",
    missing_evidence_labels: missing,
    notes: warnings.slice(0, 4),
  };
}

function formatReportValue(value) {
  if (typeof value === "string") {
    const text = value.trim();
    if (/^[{[]/.test(text)) {
      try {
        return formatReportValue(JSON.parse(text));
      } catch {
        // Keep the original text when a model returned a truncated JSON-looking fragment.
      }
    }
    return text;
  }
  if (Array.isArray(value)) {
    return value.map(formatReportValue).filter(isMeaningfulReportText).join(" / ");
  }
  if (value && typeof value === "object") {
    const title = value.name || value.title || value.pattern || value.formula || value.template || value.idea || value.dimension || value.summary || value.point || value.text || value.content || "";
    const detailMap = [
      ["description", ""],
      ["why_it_works", "有效原因"],
      ["when_to_use", "适用"],
      ["formula_used", "使用公式"],
      ["reason", "理由"],
      ["beat_structure", "结构"],
      ["beats", "结构"],
      ["structure", "结构"],
      ["production_requirements", "制作要求"],
      ["expected_metric_strength", "强项"],
      ["likely_strength", "强度"],
      ["action", "动作"],
      ["evidence", "证据"],
      ["metric", "指标"],
      ["metric_value", "数值"],
      ["evidence_level", "证据等级"],
      ["risks", "风险"],
    ];
    const details = detailMap
      .filter(([key]) => publicValueHasContent(value[key]))
      .map(([key, label]) => {
        const text = formatReportValue(value[key]);
        return label ? `${label}：${text}` : text;
      })
      .filter(isMeaningfulReportText);
    if (title || details.length) {
      return [title, details.join("；")].filter(isMeaningfulReportText).join("：");
    }
    return Object.entries(value)
      .filter(([, item]) => publicValueHasContent(item))
      .map(([key, item]) => {
        const text = formatReportValue(item);
        return /^(text|content)$/i.test(key) ? text : `${key}：${text}`;
      })
      .join("；");
  }
  return String(value ?? "");
}

function cleanPublicReportText(value) {
  return String(value ?? "")
    .replace(/(^|[；;\n])\s*[-*]?\s*text\s*[:：]\s*/gi, "$1")
    .replace(/^text\s*[:：]\s*/gi, "")
    .replace(/^dimension\s*[:：]\s*/gi, "")
    .replace(/([；;，,]\s*)action\s*[:：]\s*/gi, "：")
    .replace(/^action\s*[:：]\s*/gi, "")
    .replace(/^["']?\{\\?["']?pattern\\?["']?\s*[:：]\s*\\?["']?/i, "")
    .replace(/^["']?\{\\?["']?dimension\\?["']?\s*[:：]\s*\\?["']?/i, "")
    .replace(/\\?["']?\s*,\s*\\?["']?evidence\\?["']?\s*[:：].*$/i, "")
    .replace(/\s+/g, " ")
    .trim();
}

function reportItemPrimaryText(item) {
  if (typeof item === "string") {
    return formatReportValue(item);
  }
  if (!item || typeof item !== "object" || Array.isArray(item)) {
    return formatReportValue(item);
  }
  return (
    item.name
    || item.title
    || item.pattern
    || item.formula
    || item.summary
    || item.description
    || item.point
    || item.text
    || item.content
    || item.template
    || item.idea
    || item.dimension
    || item.why_it_works
    || formatReportValue(item)
  );
}

function isMeaningfulReportText(value) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!text) {
    return false;
  }
  if (/^(undefined|null|NaN)$/i.test(text)) {
    return false;
  }
  if (/^暂无/.test(text)) {
    return false;
  }
  const compact = text.replace(/[：:；;,，。、\s/·|｜\-—_]/g, "");
  if (!compact) {
    return false;
  }
  const placeholderPatterns = [
    /^公式适用结构风险$/,
    /^选题强度制作要求$/,
    /^模板$/,
    /^规则$/,
    /^风险$/,
    /^低置信度规则$/,
  ];
  return !placeholderPatterns.some((pattern) => pattern.test(compact));
}

function renderPublicList(items, emptyText = "暂无明确结论。") {
  const seen = new Set();
  const values = normalizeItems(items)
    .map(formatReportValue)
    .map(cleanPublicReportText)
    .filter(isMeaningfulReportText)
    .filter((item) => {
      if (seen.has(item)) {
        return false;
      }
      seen.add(item);
      return true;
    });
  if (!values.length) {
    return `<p class="muted compact-copy">${escapeHtml(emptyText)}</p>`;
  }
  return `<ul class="public-report-list">${values.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function publicValueHasContent(value) {
  if (value === undefined || value === null) {
    return false;
  }
  if (Array.isArray(value)) {
    return value.some((item) => publicValueHasContent(item));
  }
  if (typeof value === "object") {
    return Object.values(value).some((item) => publicValueHasContent(item));
  }
  return isMeaningfulReportText(value);
}

function renderSegmentSampleList(items, metricKey, metricLabel, emptyText = "暂无样本。") {
  const values = normalizeItems(items)
    .map((item) => {
      if (!item || typeof item !== "object") {
        return formatReportValue(item);
      }
      const title = item.title || item.desc || item.nickname || item.author || item.source_url || "未命名样本";
      const metricValue = item.metric_value ?? item[metricKey];
      const metrics = [
        metricValue !== undefined && metricValue !== null && metricValue !== "" ? `${metricLabel} ${formatNumber(metricValue)}` : "",
        Number(item.like_count || 0) && metricKey !== "like_count" ? `赞 ${formatNumber(item.like_count)}` : "",
        Number(item.comment_count || 0) && metricKey !== "comment_count" ? `评 ${formatNumber(item.comment_count)}` : "",
        Number(item.share_count || 0) && metricKey !== "share_count" ? `分享 ${formatNumber(item.share_count)}` : "",
        Number(item.collect_count || 0) && metricKey !== "collect_count" ? `收藏 ${formatNumber(item.collect_count)}` : "",
      ].filter(Boolean).slice(0, 3).join(" · ");
      return metrics ? `${title}（${metrics}）` : title;
    })
    .filter(Boolean);
  return renderPublicList(values, emptyText);
}

function renderPublicFields(rows) {
  const values = rows.filter(([, value]) => value !== undefined && value !== null && value !== "");
  if (!values.length) {
    return '<p class="muted compact-copy">暂无明确结论。</p>';
  }
  return `
    <dl class="public-report-fields">
      ${values
        .map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(formatReportValue(value))}</dd>`)
        .join("")}
    </dl>
  `;
}

function renderPublicCard(title, body, tone = "") {
  return `
    <article class="public-report-card ${escapeHtml(tone)}">
      <h4>${escapeHtml(title)}</h4>
      ${body}
    </article>
  `;
}

function renderPublicAnalysisReport(result) {
  const hook = result.hook_analysis || {};
  const visual = result.visual_analysis || {};
  const replication = result.replication || {};
  const publish = result.publish_package || {};
  const category = result.content_category_label || result.content_category || "短视频";
  const confidence = result.confidence ? `置信度 ${result.confidence}` : "";
  return `
    <section class="public-analysis-hero">
      <span>${escapeHtml(category)}${confidence ? ` · ${escapeHtml(confidence)}` : ""}</span>
      <strong>${escapeHtml(result.summary || "AI 已完成拆解，但没有返回摘要。")}</strong>
    </section>
    <div class="public-report-grid">
      ${renderPublicCard(
        "0-3 秒抓人点",
        `
          ${renderPublicFields([
            ["第一眼", hook.first_impression],
            ["停留理由", hook.why_stop_scrolling],
            ["优化方向", hook.optimization],
          ])}
          ${renderPublicList(hook.first_3_seconds, "暂无逐秒观察。")}
        `,
        "featured",
      )}
      ${renderPublicCard(
        "画面 / 人设 / 氛围",
        `
          ${renderPublicFields([
            ["主体", visual.subject],
            ["构图", visual.composition],
            ["光线色彩", visual.lighting_color],
            ["动作节奏", visual.movement_rhythm],
          ])}
          ${renderPublicList(visual.style_keywords, "暂无风格关键词。")}
        `,
      )}
      ${renderPublicCard(
        "可复刻点",
        `
          ${renderPublicFields([
            ["复刻角度", replication.remake_angle],
            ["开头 3 秒", replication.opening_3s],
          ])}
          ${renderPublicList(replication.copyable_points, "暂无可复刻动作。")}
        `,
        "featured",
      )}
      ${renderPublicCard(
        "风险与改编边界",
        `
          <h5>不要照搬</h5>
          ${renderPublicList(replication.avoid_copying, "暂无明确边界。")}
          <h5>风险提醒</h5>
          ${renderPublicList(result.risks, "暂无风险提醒。")}
        `,
      )}
      ${renderPublicCard(
        "标题与发布灵感",
        `
          ${renderPublicFields([["发布文案", publish.caption]])}
          <h5>标题方向</h5>
          ${renderPublicList(publish.titles, "暂无标题建议。")}
          <h5>标签</h5>
          ${renderPublicList(publish.hashtags, "暂无标签建议。")}
        `,
      )}
      ${renderPublicCard("下一步", renderPublicList(result.next_actions, "暂无下一步建议。"))}
    </div>
  `;
}

function sortCreatorSampleViewItems(items, sortBy) {
  const key = ["like_count", "comment_count", "share_count", "collect_count", "engagement_score", "create_time"].includes(sortBy)
    ? sortBy
    : "like_count";
  return [...items].sort((left, right) => {
    const leftValue = left[key] || 0;
    const rightValue = right[key] || 0;
    return rightValue > leftValue ? 1 : rightValue < leftValue ? -1 : 0;
  });
}

function filterCreatorSampleViewItems(items, filterBy) {
  const filter = ["all", "buildable", "metadata_only", "has_frames", "ready_evidence"].includes(filterBy)
    ? filterBy
    : "all";
  if (filter === "all") {
    return [...items];
  }
  return items.filter((item) => {
    if (filter === "buildable") return isSampleViewItemBuildable(item);
    if (filter === "metadata_only") return !item.understanding_level || item.understanding_level === "metadata_only";
    if (filter === "has_frames") return Boolean(item.has_frames);
    if (filter === "ready_evidence") return profileEvidenceScore(item) >= 2;
    return true;
  });
}

function filterCreatorSampleViewItemsByMedia(items, mediaType) {
  const filter = ["all", "video", "image", "unknown"].includes(mediaType) ? mediaType : "all";
  if (filter === "all") {
    return [...items];
  }
  return items.filter((item) => {
    const type = item.media_type || "unknown";
    if (filter === "unknown") {
      return !["video", "image"].includes(type);
    }
    return type === filter;
  });
}

function visibleCreatorSampleViewItems() {
  const mediaFiltered = filterCreatorSampleViewItemsByMedia(activeCreatorSampleViewItems(), profileMediaFilter?.value || "all");
  return sortCreatorSampleViewItems(filterCreatorSampleViewItems(mediaFiltered, profileEvidenceFilter?.value || "all"), profileSort?.value || "like_count");
}

function selectedCreatorSampleViewItems() {
  return activeCreatorSampleViewItems().filter((item) => profileSelectedKeys.has(sampleViewItemKey(item)));
}

function sampleViewItemKey(item) {
  return item?.sample_id || item?.aweme_id || item?.case_id || item?.source_url || "";
}

function sampleViewItemMatchesKeySet(item, keySet) {
  return [
    item?.sample_id,
    item?.aweme_id,
    item?.case_id,
    item?.source_url,
    item?.webpage_url,
  ].some((key) => key && keySet.has(String(key)));
}

// Creator Clone: import
function setActiveImportMode(mode = "browser") {
  const activeMode = ["browser", "manual", "structured", "case", "handoff"].includes(mode) ? mode : "browser";
  profileImportModeButtons.forEach((button) => {
    const active = button.dataset.profileImportMode === activeMode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  profileImportPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.profileImportPanel === activeMode);
  });
  renderCreatorCloneNextAction();
}

function activeProfileImportMode() {
  return profileImportModeButtons.find((button) => button.classList.contains("active"))?.dataset.profileImportMode || "browser";
}

function creatorCloneUnifiedInputValue() {
  return String(profileQuickInput?.value || "").trim();
}

function setCreatorCloneRestoredInput(value = "") {
  const restoredValue = String(value || "").trim();
  profileQuickInputRestoredValue = restoredValue;
  if (profileQuickInput) {
    profileQuickInput.value = restoredValue;
  }
}

function commitCreatorCloneUnifiedInput() {
  profileQuickInputRestoredValue = creatorCloneUnifiedInputValue();
}

function clearCreatorCloneUnifiedInput() {
  if (profileQuickInput) {
    profileQuickInput.value = "";
  }
  profileQuickInputRestoredValue = "";
}

function hasPendingQuickImportInput() {
  const value = creatorCloneUnifiedInputValue();
  return Boolean(value && value !== profileQuickInputRestoredValue);
}

function hasCreatorCloneImportInput() {
  const quick = creatorCloneUnifiedInputValue();
  if (quick) return true;
  if (!profileForm) return false;
  const formData = new FormData(profileForm);
  return Boolean(
    String(formData.get("profile_url") || "").trim()
      || String(formData.get("manual_links") || "").trim()
      || String(formData.get("structured_items") || "").trim()
      || String(formData.get("case_ids") || "").trim()
      || String(formData.get("handoff_manifest") || "").trim(),
  );
}

function inferCreatorCloneImportMode() {
  const quick = creatorCloneUnifiedInputValue();
  if (quick) {
    const firstUrl = firstUrlFromText(quick);
    const target = firstUrl || quick;
    if (/^\s*[\[{]/.test(quick) || /^aweme_id\s*,/im.test(quick)) return "structured";
    if (/^case_[A-Za-z0-9_,-\s]+$/.test(quick)) return "case";
    if (/douyin\.com\/user\//i.test(target) || /^MS4w[A-Za-z0-9_.-]+/.test(target)) return "browser";
    return "manual";
  }
  const formData = new FormData(profileForm);
  if (String(formData.get("handoff_manifest") || "").trim()) return "handoff";
  if (String(formData.get("structured_items") || "").trim()) return "structured";
  if (String(formData.get("case_ids") || "").trim()) return "case";
  if (String(formData.get("manual_links") || "").trim()) return "manual";
  if (String(formData.get("profile_url") || "").trim()) return "browser";
  return activeProfileImportMode();
}

function syncUnifiedInputToImportFields(mode) {
  const quick = creatorCloneUnifiedInputValue();
  if (!quick || !profileForm) return;
  if (mode === "browser") {
    profileForm.elements.profile_url.value = firstUrlFromText(quick) || quick;
    return;
  }
  if (mode === "manual" && profileManualLinks) {
    profileManualLinks.value = quick;
    return;
  }
  if (mode === "structured") {
    profileForm.elements.structured_items.value = quick;
    return;
  }
  if (mode === "case") {
    profileForm.elements.case_ids.value = quick;
  }
}

function isSampleViewItemBuildable(item) {
  return Boolean(item?.aweme_id) && item?.can_build_case !== false && !["image", "text"].includes(item?.media_type || "");
}

function hasPendingEnrichment(items = selectedCreatorSampleViewItems()) {
  return normalizeItems(items).some((item) => isSampleViewItemBuildable(item) && !item.case_id && !item.has_frames);
}

function applyCreatorIntelligencePayload(payload = {}) {
  const intelligence = payload?.creator_intelligence || payload?.set?.creator_intelligence || null;
  const runtimeState = intelligence?.runtime_state || payload?.runtime_state || null;
  const nextProject = intelligence?.project || payload?.project || creatorProjectFromCloneSet(payload?.set) || currentCreatorIntelligenceProject;
  const previousProjectId = currentCreatorIntelligenceProject?.project_id || "";
  const nextProjectId = nextProject?.project_id || "";
  const projectChanged = previousProjectId && nextProjectId && previousProjectId !== nextProjectId;
  currentCreatorIntelligenceProject = nextProject;
  const incomingStrategy = intelligence?.strategy_output || payload?.strategy_output || null;
  currentCreatorIntelligenceStrategy = incomingStrategy || (projectChanged ? null : currentCreatorIntelligenceStrategy);
  const incomingResult = intelligence?.result || payload?.result || null;
  currentCreatorIntelligenceResult = incomingResult || (projectChanged ? null : currentCreatorIntelligenceResult);
  const legacyWorkflow = intelligence?.workflow || payload?.workflow || null;
  const legacyBehavior = intelligence?.behavior_model || payload?.behavior_model || null;
  currentCreatorRuntimeState = runtimeState || (projectChanged ? null : currentCreatorRuntimeState);
  if (!runtimeState && (legacyWorkflow || legacyBehavior)) {
    currentCreatorRuntimeState = {
      ...(currentCreatorRuntimeState || {}),
      workflow: legacyWorkflow || currentCreatorRuntimeState?.workflow || null,
      behavior_model: legacyBehavior || currentCreatorRuntimeState?.behavior_model || null,
    };
  }
}

function creatorRuntimeCurrentStep() {
  return currentCreatorRuntimeState?.current_step || {};
}

function creatorRuntimePrimaryAction() {
  const action = currentCreatorRuntimeState?.primary_action || {};
  if (action.command || action.label || action.summary) {
    return action;
  }
  const workflow = currentCreatorRuntimeState?.workflow || {};
  const ui = workflow?.ui || {};
  return ui.next_action || workflow?.next_action || {};
}

function creatorRuntimeStage() {
  return normalizeProfileStage(creatorRuntimeCurrentStep().stage || "import");
}

function creatorRuntimeActionState() {
  return creatorRuntimePrimaryAction().state || "";
}

function creatorRuntimeMetaFallback() {
  if (hasCreatorCloneImportInput()) {
    return {
      step: "当前步骤：导入素材",
      button: "下一步：开始导入素材",
      command: "import_input",
      summary: "输入主页 URL、作品链接、aweme_id 或分享文案后，点击主按钮开始。",
      disabled: false,
    };
  }
  return {
    step: "当前步骤：导入素材",
    button: "下一步：开始导入素材",
    command: "import_input",
    summary: "等待输入主页 URL、作品链接、aweme_id 或分享文案。",
    disabled: false,
  };
}

function creatorCloneDistillCommandForSelectedCount(selectedCount = selectedCreatorSampleViewItems().length) {
  return Number(selectedCount || 0) > CREATOR_CLONE_MAX_DISTILL_SAMPLES
    ? "start_batch_distillation"
    : "start_distillation";
}

function creatorCloneStageLabel(stage) {
  return {
    import: "当前步骤：导入素材",
    pool: "当前步骤：构建素材池",
    select: "当前步骤：选择 N 条样本",
    enrich: "当前步骤：富化证据",
    distill: "当前步骤：大模型蒸馏",
    export: "当前步骤：可视化输出",
  }[normalizeProfileStage(stage)] || "当前步骤：导入素材";
}

function creatorRuntimeMetaFromState() {
  const step = creatorRuntimeCurrentStep();
  const action = creatorRuntimePrimaryAction();
  if (!step.label && !action.command && !action.label && !action.summary) {
    return null;
  }
  const command = action.command || "";
  return {
    step: step.label || creatorCloneStageLabel(step.stage || "import"),
    button: action.label || "下一步",
    command,
    summary: action.summary || "",
    disabled: Boolean(action.disabled) || command === "wait",
  };
}

function hasCreatorCloneReportValue(value) {
  return Boolean(value && typeof value === "object" && Object.keys(value).length);
}

function currentCreatorCloneSetId() {
  return (
    currentCloneSetId
    || currentCreatorIntelligenceProject?.project_id
    || profileScanPayload?.set?.set_id
    || profileScanPayload?.creator_intelligence?.project?.project_id
    || ""
  );
}

function hasCreatorCloneReportLinkReady() {
  const reportHref = downloadCreatorCloneMd?.getAttribute("href") || "";
  return Boolean(reportHref && reportHref !== "#");
}

function hasRecoverableCreatorCloneReport() {
  const workflowState = currentCreatorRuntimeState?.workflow?.state || "";
  return Boolean(
    currentCreatorCloneSetId()
    && workflowState === "DONE"
  );
}

function hasCreatorCloneReportReady() {
  return (
    hasCreatorCloneReportValue(currentCreatorRuntimeReport)
    || hasCreatorCloneReportValue(currentCreatorIntelligenceResult)
    || Boolean(creatorCloneResult?.querySelector(".creator-distillation-report"))
    || hasCreatorCloneReportLinkReady()
    || hasRecoverableCreatorCloneReport()
  );
}

function hasCreatorCloneOutputReady() {
  return hasCreatorCloneReportReady() || Boolean(currentDistillPrompt || creatorCloneResult?.querySelector(".prompt-preview"));
}

function stageIndexFromName(stage) {
  return {
    import: 0,
    pool: 1,
    select: 2,
    enrich: 3,
    distill: 4,
    export: 5,
  }[stage] ?? 0;
}

function normalizeProfileStage(stage) {
  return ["import", "pool", "select", "enrich", "distill", "export"].includes(stage) ? stage : "import";
}

function setProfileStageView(stage, {scroll = false} = {}) {
  profileStageView = resolveProfileStageForView(stage);
  rememberRecentProfileStage(profileStageView);
  renderProfileStageView();
  renderCreatorCloneStageChrome();
  if (scroll) {
    document.querySelector(".profile-main-flow")?.scrollIntoView({behavior: "smooth", block: "start"});
  }
}

function activeProfileStage() {
  if (hasPendingQuickImportInput()) {
    return "import";
  }
  return normalizeProfileStage(profileStageView || creatorRuntimeStage());
}

function creatorWorkflowProgressStage() {
  if (hasPendingQuickImportInput()) {
    return "import";
  }
  const runtimeStage = creatorRuntimeCurrentStep().stage;
  if (runtimeStage) {
    return normalizeProfileStage(runtimeStage);
  }
  return activeProfileStage();
}

function lockedProfileNavigationStage() {
  if (creatorCloneEnrichmentRunning) {
    return "enrich";
  }
  if (creatorCloneDistillRunning) {
    return "distill";
  }
  return "";
}

function hasCreatorCloneActiveSession() {
  return Boolean(currentCloneSetId || activeCreatorSampleViewItems().length || currentCreatorRuntimeState);
}

function hasCreatorCloneSamplePool() {
  return Boolean(currentCloneSetId || activeCreatorSampleViewItems().length);
}

function hasCreatorCloneSelectedSamples() {
  return selectedCreatorSampleViewItems().length > 0;
}

function creatorCloneStageUnavailableReason(stage, {includeRuntimeLock = true} = {}) {
  const normalizedStage = normalizeProfileStage(stage);
  const runningLockedStage = includeRuntimeLock ? lockedProfileNavigationStage() : "";
  if (runningLockedStage && normalizedStage !== runningLockedStage) {
    return creatorCloneEnrichmentRunning
      ? "证据富化正在运行，完成后会自动进入下一步；当前先保持队列视图。"
      : "大模型蒸馏正在运行，完成后会自动进入报告页；当前先保持任务视图。";
  }
  if (normalizedStage === "import") {
    return "";
  }
  if (!hasCreatorCloneSamplePool()) {
    return "请先完成导入素材，再进入后续步骤。";
  }
  if (["enrich", "distill"].includes(normalizedStage) && !hasCreatorCloneSelectedSamples()) {
    return "请先在“选择 N 条样本”中勾选代表样本。";
  }
  if (normalizedStage === "export" && !hasCreatorCloneOutputReady()) {
    return "请先完成大模型蒸馏生成报告或 Prompt。";
  }
  return "";
}

function resolveProfileStageForView(stage) {
  const normalizedStage = normalizeProfileStage(stage);
  if (normalizedStage === "import") {
    return "import";
  }
  if (!hasCreatorCloneSamplePool()) {
    return "import";
  }
  if (["pool", "select"].includes(normalizedStage)) {
    return normalizedStage;
  }
  if (["enrich", "distill"].includes(normalizedStage) && !hasCreatorCloneSelectedSamples()) {
    return "select";
  }
  if (normalizedStage === "export" && !hasCreatorCloneOutputReady()) {
    return hasCreatorCloneSelectedSamples() ? "distill" : "select";
  }
  return normalizedStage;
}

function profileStageNavigationLockMessage(stage) {
  return creatorCloneStageUnavailableReason(stage);
}

function isProfileStageNavigationLocked(stage) {
  return Boolean(creatorCloneStageUnavailableReason(stage));
}

function canNavigateProfileStage(stage) {
  return !isProfileStageNavigationLocked(stage);
}

function renderProfileStageView() {
  const activeStage = activeProfileStage();
  profileStageSections.forEach((section) => {
    const stages = String(section.dataset.profileStageSection || "").split(/\s+/).filter(Boolean);
    const isActive = stages.includes(activeStage);
    section.classList.toggle("stage-hidden", !isActive);
    if (isActive) {
      section.classList.remove("hidden");
    }
  });
  if (profileResultsCard) {
    const shouldShowResultContainer = !["import", "export"].includes(activeStage)
      && (activeCreatorSampleViewItems().length || currentCloneSetId || currentCreatorRuntimeReport);
    profileResultsCard.classList.toggle("hidden", !shouldShowResultContainer);
  }
}

function revealProfileQueueCard() {
  profileEnrichmentSection?.classList.remove("hidden");
  profileEnrichmentSection?.classList.remove("stage-hidden");
  profileQueueCard?.classList.remove("hidden");
}

function syncProfileStageToWizard({scroll = false} = {}) {
  setProfileStageView(creatorRuntimeStage(), {scroll});
}

function creatorCloneViewMetaForStage(stage = activeProfileStage()) {
  const normalizedStage = normalizeProfileStage(stage);
  const selectedCount = selectedCreatorSampleViewItems().length;
  if (normalizedStage === "import" || hasPendingQuickImportInput()) {
    return creatorRuntimeMetaFallback();
  }
  if (normalizedStage === "pool") {
    return {
      step: creatorCloneStageLabel("pool"),
      button: "下一步：选择样本",
      command: "show_select",
      summary: "素材池已构建，可进入样本选择并按互动数据筛选。",
      disabled: !hasCreatorCloneSamplePool(),
    };
  }
  if (normalizedStage === "select") {
    if (!selectedCount) {
      return {
        step: creatorCloneStageLabel("select"),
        button: "请先选择样本",
        command: "select_samples",
        summary: "在素材列表中勾选代表样本，或使用快捷入口。",
        disabled: true,
      };
    }
    return {
      step: creatorCloneStageLabel("select"),
      button: "下一步：开始富化证据",
      command: "build_evidence",
      summary: `已选择 ${formatNumber(selectedCount)} 条样本，下一步补齐视频、关键帧、OCR、ASR 等证据。`,
      disabled: false,
    };
  }
  if (normalizedStage === "enrich") {
    if (creatorCloneEnrichmentRunning) {
      return {
        step: creatorCloneStageLabel("enrich"),
        button: "正在富化证据",
        command: "wait",
        summary: "证据富化正在后台运行，完成后会更新素材包队列。",
        disabled: true,
      };
    }
    if (!selectedCount) {
      return {
        step: creatorCloneStageLabel("enrich"),
        button: "返回选择样本",
        command: "show_select",
        summary: "还没有选中的代表样本。",
        disabled: false,
      };
    }
    if (hasPendingEnrichment()) {
      return {
        step: creatorCloneStageLabel("enrich"),
        button: "下一步：开始富化证据",
        command: "build_evidence",
        summary: `已选择 ${formatNumber(selectedCount)} 条样本，仍有素材需要补齐证据。`,
        disabled: false,
      };
    }
    return {
      step: creatorCloneStageLabel("enrich"),
      button: "下一步：进入大模型蒸馏",
      command: "show_distill",
      summary: "选中样本已有可用证据，可进入大模型蒸馏。",
      disabled: false,
    };
  }
  if (normalizedStage === "distill") {
    if (creatorCloneDistillRunning) {
      return {
        step: creatorCloneStageLabel("distill"),
        button: "正在大模型蒸馏",
        command: "wait",
        summary: "当前任务由后台执行，完成后会展示创作者蒸馏报告。",
        disabled: true,
      };
    }
    if (!selectedCount) {
      return {
        step: creatorCloneStageLabel("distill"),
        button: "返回选择样本",
        command: "show_select",
        summary: "还没有可蒸馏样本，请先选择代表样本。",
        disabled: false,
      };
    }
    const command = creatorCloneDistillCommandForSelectedCount(selectedCount);
    return {
      step: creatorCloneStageLabel("distill"),
      button: command === "start_batch_distillation" ? "下一步：开始分批蒸馏" : "下一步：开始大模型蒸馏",
      command,
      summary: command === "start_batch_distillation"
        ? `已选择 ${formatNumber(selectedCount)} 条样本，将按批次蒸馏后汇总。`
        : `已选择 ${formatNumber(selectedCount)} 条样本，开始账号级创作者蒸馏。`,
      disabled: false,
    };
  }
  if (normalizedStage === "export") {
    const runtimeMeta = creatorRuntimeMetaFromState();
    if (runtimeMeta?.command === "export_report") {
      return runtimeMeta;
    }
    return {
      step: creatorCloneStageLabel("export"),
      button: "下一步：下载报告",
      command: "export_report",
      summary: hasCreatorCloneOutputReady() ? "创作者蒸馏报告已生成，可打开网页报告。" : "请先完成大模型蒸馏生成报告。",
      disabled: !hasCreatorCloneOutputReady(),
    };
  }
  return creatorRuntimeMetaFallback();
}

function creatorCloneStageMeta(stage = activeProfileStage()) {
  return creatorCloneViewMetaForStage(stage);
}

function creatorCloneStateMeta(state = creatorRuntimeActionState()) {
  void state;
  return creatorCloneStageMeta();
}

function creatorCloneActionStateForCurrentView(state = creatorRuntimeActionState()) {
  return creatorRuntimePrimaryAction().state || state;
}

function renderCreatorCloneRecommendation() {
  if (!creatorCloneRecommendation) {
    return;
  }
  if (!activeCreatorSampleViewItems().length && representativeRecommendationState === "idle") {
    creatorCloneRecommendation.classList.add("hidden");
    creatorCloneRecommendation.innerHTML = "";
    return;
  }
  creatorCloneRecommendation.classList.remove("hidden");
  if (representativeRecommendationState === "loading") {
    creatorCloneRecommendation.innerHTML = `
      <div class="recommendation-heading">
        <div><strong>代表样本推荐</strong><p>正在本地计算，不调用大模型或外部服务...</p></div>
      </div>
    `;
    return;
  }
  if (representativeRecommendationState === "error") {
    creatorCloneRecommendation.innerHTML = `
      <div class="recommendation-heading">
        <div><strong>代表样本推荐</strong><p>${escapeHtml(representativeRecommendationMessage || "推荐计算失败，可继续手动选样。")}</p></div>
        <button type="button" class="secondary-button" data-representative-action="refresh">重新计算</button>
      </div>
    `;
    return;
  }
  const selection = currentRepresentativeSampleSelection;
  if (!selection?.recommendations?.length) {
    creatorCloneRecommendation.innerHTML = `
      <div class="recommendation-heading">
        <div><strong>代表样本推荐</strong><p>当前素材缺少可用于推荐的安全元数据，可继续手动选择。</p></div>
        <button type="button" class="secondary-button" data-representative-action="refresh">重新计算</button>
      </div>
    `;
    return;
  }
  const coverage = Object.entries(REPRESENTATIVE_ROLE_LABELS)
    .map(([role, label]) => {
      const covered = Boolean(selection.coverage?.[role]);
      return `<span class="representative-coverage ${covered ? "covered" : "unavailable"}">${escapeHtml(label)} ${covered ? "✓" : "数据不足"}</span>`;
    })
    .join("");
  const warningMarkup = normalizeItems(selection.warnings).length
    ? `<details class="representative-warnings"><summary>数据说明</summary><ul>${normalizeItems(selection.warnings).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></details>`
    : "";
  creatorCloneRecommendation.innerHTML = `
    <div class="recommendation-heading">
      <div>
        <strong>代表样本推荐</strong>
        <p>系统从 ${formatNumber(selection.available_count)} 条作品中推荐 ${formatNumber(selection.recommended_count)} 条作为 Creator 蒸馏样本。</p>
        <small>算法：代表性 v1 · 本地确定性计算 · 不调用 LLM</small>
      </div>
      <div class="representative-actions">
        <button type="button" class="text-button" data-representative-action="refresh">重新计算</button>
        <button type="button" class="primary-button" data-representative-action="apply">使用推荐组合</button>
      </div>
    </div>
    <div class="representative-coverage-list" aria-label="推荐角色覆盖">${coverage}</div>
    <p class="representative-score-note">代表性评分表示“适合进入分析样本集”的程度，不是爆款概率或内容质量分。</p>
    ${warningMarkup}
  `;
}

function representativeRecommendationForItem(item) {
  if (!representativeSampleSelectorUi || !currentRepresentativeSampleSelection) {
    return null;
  }
  return representativeSampleSelectorUi.recommendationById(
    currentRepresentativeSampleSelection,
    sampleViewItemKey(item),
  );
}

function representativeSampleMarkup(item) {
  const recommendation = representativeRecommendationForItem(item);
  if (!recommendation) {
    return "";
  }
  const label = REPRESENTATIVE_ROLE_LABELS[recommendation.primary_role] || "代表样本";
  const secondaryRoleCount = Math.max(0, normalizeItems(recommendation.roles).length - 1);
  const reasons = normalizeItems(recommendation.reasons).slice(0, 3);
  return `
    <div class="representative-row-note">
      <div class="representative-row-badges">
        <span class="representative-role-badge">${escapeHtml(label)}</span>
        ${secondaryRoleCount ? `<span class="representative-role-more">+${formatNumber(secondaryRoleCount)}</span>` : ""}
        <span class="representative-score">代表性评分 ${formatNumber(recommendation.score)}</span>
      </div>
      ${reasons.length ? `<details><summary>推荐理由</summary><ul>${reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}</ul></details>` : ""}
    </div>
  `;
}

async function refreshRepresentativeSampleRecommendations() {
  const items = activeCreatorSampleViewItems();
  if (!items.length) {
    currentRepresentativeSampleSelection = null;
    representativeRecommendationState = "idle";
    renderCreatorCloneRecommendation();
    return null;
  }
  const requestGeneration = ++representativeRecommendationGeneration;
  const sampleSetId = currentCloneSetId;
  representativeRecommendationState = "loading";
  representativeRecommendationMessage = "";
  renderCreatorCloneRecommendation();
  try {
    const response = await fetch("/api/creator-clone/sample-recommendations", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        sample_set_id: sampleSetId,
        samples: sampleSetId ? [] : items.slice(0, 200).map(creatorCloneSamplePayload),
        target_count: REPRESENTATIVE_SAMPLE_TARGET_COUNT,
      }),
    });
    const payload = await readJsonResponse(response);
    if (requestGeneration !== representativeRecommendationGeneration || sampleSetId !== currentCloneSetId) {
      return null;
    }
    currentRepresentativeSampleSelection = representativeSampleSelectorUi
      ? representativeSampleSelectorUi.normalizeSelection(payload)
      : payload;
    representativeRecommendationState = "ready";
    renderCreatorCloneRecommendation();
    renderProfileTable();
    return currentRepresentativeSampleSelection;
  } catch (error) {
    if (requestGeneration !== representativeRecommendationGeneration || sampleSetId !== currentCloneSetId) {
      return null;
    }
    currentRepresentativeSampleSelection = null;
    representativeRecommendationState = "error";
    representativeRecommendationMessage = `${error.error_code || "RECOMMENDATION_FAILED"}：${error.message || "代表样本推荐计算失败"}`;
    renderCreatorCloneRecommendation();
    return null;
  }
}

function applyRepresentativeSampleSelection() {
  if (!representativeSampleSelectorUi || !currentRepresentativeSampleSelection) {
    profileScanStatus.textContent = "代表样本推荐尚未生成，请先重新计算。";
    return false;
  }
  const items = representativeSampleSelectorUi.matchingItems(
    currentRepresentativeSampleSelection,
    activeCreatorSampleViewItems(),
    sampleViewItemKey,
  );
  if (!items.length) {
    profileScanStatus.textContent = "推荐样本已不在当前素材池，请重新计算。";
    return false;
  }
  setProfileSelection(items);
  if (profilePresetKind) {
    profilePresetKind.value = "recommended_mix";
  }
  profileScanStatus.textContent = `已应用代表样本推荐：${items.length} 条。你仍可手动增删，系统不会自动勾回。`;
  return true;
}

function renderWizardPrimaryAction(state = creatorCloneActionStateForCurrentView()) {
  const meta = creatorCloneStateMeta(state);
  const command = meta.command || "";
  if (creatorCloneNextButton) {
    creatorCloneNextButton.textContent = creatorCloneNextActionRunning ? "处理中..." : meta.button;
    creatorCloneNextButton.dataset.creatorCloneAction = command;
    creatorCloneNextButton.disabled = creatorCloneNextActionRunning || command === "wait" || Boolean(meta.disabled);
  }
}

function renderCreatorCloneStageChrome() {
  const state = creatorCloneActionStateForCurrentView();
  const meta = creatorCloneStateMeta(state);
  const activeStage = creatorWorkflowProgressStage();
  const viewedStage = activeProfileStage();
  const activeStageIndex = stageIndexFromName(activeStage);
  creatorCloneFlowSteps.forEach((step) => {
    const stage = normalizeProfileStage(step.dataset.profileStageNav || "");
    const index = stageIndexFromName(stage);
    const locked = isProfileStageNavigationLocked(stage);
    step.classList.toggle("active", index === activeStageIndex);
    step.classList.toggle("completed", index < activeStageIndex);
    step.classList.toggle("viewing", stage === viewedStage && index !== activeStageIndex);
    step.classList.toggle("locked", locked);
    step.disabled = locked;
    step.title = locked ? profileStageNavigationLockMessage(stage) : "";
    step.setAttribute("aria-current", index === activeStageIndex ? "step" : "false");
  });
  if (creatorCloneCurrentStep) {
    creatorCloneCurrentStep.textContent = meta.step;
  }
  if (creatorCloneNextSummary) {
    creatorCloneNextSummary.textContent = meta.summary;
  }
  if (profileNextAction) {
    profileNextAction.textContent = meta.step;
  }
  renderWizardPrimaryAction(state);
  renderCreatorCloneRecommendation();
}

function renderCreatorCloneNextAction() {
  renderCreatorCloneStageChrome();
  renderProfileStageView();
}

// Creator Clone: sample pool
function setCreatorCloneStep(step = creatorRuntimeActionState()) {
  void step;
  profileEnrichmentSection?.classList.remove("hidden");
  profileDistillationSection?.classList.remove("hidden");
  renderCreatorCloneNextAction();
}

function renderCreatorCloneOverview(summary = {}) {
  if (!profileSummary) {
    return;
  }
  const items = activeCreatorSampleViewItems();
  const selected = selectedCreatorSampleViewItems();
  const buildable = items.filter(isSampleViewItemBuildable);
  const coverage = profileEvidenceCoverageSummary(items);
  const nextAction = creatorCloneStateMeta().summary || "等待当前步骤完成。";
  const total = summary.scanned_count || items.length;
  profileSummary.innerHTML = `
    <article><span>素材数量</span><strong>${formatNumber(total)}</strong></article>
    <article><span>已选样本</span><strong>${formatNumber(selected.length)}</strong></article>
    <article><span>可富化视频</span><strong>${formatNumber(buildable.length)}</strong></article>
    <article class="wide"><span>证据覆盖</span><strong>${escapeHtml(coverage)}</strong></article>
    <article class="wide"><span>下一步建议</span><strong>${escapeHtml(nextAction)}</strong></article>
  `;
  setCreatorCloneStep();
}

// Creator Clone: selection
function updateCreatorCloneSelectionStatus() {
  const selected = selectedCreatorSampleViewItems();
  const buildable = selected.filter(isSampleViewItemBuildable);
  const unbuildableCount = selected.length - buildable.length;
  const counts = selected.reduce(
    (acc, item) => {
      const level = item.understanding_level || "metadata_only";
      acc[level] = (acc[level] || 0) + 1;
      return acc;
    },
    {full: 0, partial: 0, metadata_only: 0},
  );
  if (creatorCloneSelectionStatus) {
    const enrichLimitText = buildable.length > PROFILE_BUILD_MAX_ITEMS
      ? `；超过本轮富化上限 ${PROFILE_BUILD_MAX_ITEMS} 条`
      : `；本轮富化上限 ${PROFILE_BUILD_MAX_ITEMS} 条`;
    creatorCloneSelectionStatus.textContent = `已选 ${selected.length} 条；可富化视频 ${buildable.length} 条${enrichLimitText}；参考样本 ${unbuildableCount} 条。单次蒸馏最多 ${CREATOR_CLONE_MAX_DISTILL_SAMPLES} 条，分批蒸馏建议单批 ${CREATOR_CLONE_MAX_DISTILL_SAMPLES} 条。完整 ${counts.full || 0}，部分 ${counts.partial || 0}，仅元数据 ${counts.metadata_only || 0}。`;
  }
  if (profileSelectedBuildButton) {
    const disabledReason = creatorCloneEnrichmentRunning
      ? "证据富化任务正在运行。"
      : !selected.length
      ? "请先选择代表样本。"
      : buildable.length > PROFILE_BUILD_MAX_ITEMS
        ? `可下载视频超过当前富化上限 ${PROFILE_BUILD_MAX_ITEMS} 条。`
        : "";
    profileSelectedBuildButton.disabled = Boolean(disabledReason);
    profileSelectedBuildButton.title = disabledReason || (buildable.length
      ? `将富化 ${buildable.length} 条可解析视频，并保留 ${unbuildableCount} 条参考样本`
      : `保存 ${selected.length} 条参考样本，不执行视频下载`);
  }
  const shouldBatchDistill = selected.length > CREATOR_CLONE_MAX_DISTILL_SAMPLES;
  if (creatorCloneDistillButton) {
    creatorCloneDistillButton.classList.toggle("hidden", shouldBatchDistill);
    creatorCloneDistillButton.textContent = "高级：执行蒸馏";
    const distillDisabledReason = creatorCloneDistillRunning
      ? "大模型蒸馏任务正在运行。"
      : !selected.length
      ? "请先选择要蒸馏的样本。"
      : shouldBatchDistill
        ? `超过 ${CREATOR_CLONE_MAX_DISTILL_SAMPLES} 条时请使用分批蒸馏。`
        : "";
    creatorCloneDistillButton.disabled = Boolean(distillDisabledReason);
    creatorCloneDistillButton.title = distillDisabledReason || `将蒸馏 ${selected.length} 条样本`;
  }
  if (creatorCloneBatchDistillButton) {
    creatorCloneBatchDistillButton.classList.toggle("hidden", !shouldBatchDistill);
    creatorCloneBatchDistillButton.textContent = "高级：分批蒸馏";
    const batchDisabledReason = creatorCloneDistillRunning
      ? "大模型蒸馏任务正在运行。"
      : !selected.length
      ? "请先选择要分批蒸馏的样本。"
      : selected.length <= CREATOR_CLONE_MAX_DISTILL_SAMPLES
        ? `${CREATOR_CLONE_MAX_DISTILL_SAMPLES} 条以内请使用执行蒸馏。`
      : selected.length > PROFILE_BUILD_MAX_ITEMS
        ? `分批蒸馏最多支持 ${PROFILE_BUILD_MAX_ITEMS} 条样本。`
        : "";
    creatorCloneBatchDistillButton.disabled = Boolean(batchDisabledReason);
    creatorCloneBatchDistillButton.title = batchDisabledReason || `将 ${selected.length} 条样本按每 ${CREATOR_CLONE_MAX_DISTILL_SAMPLES} 条一批蒸馏并汇总`;
  }
  if (isProfileBuildJobActive()) {
    if (activeProfileBuildLastResult) {
      renderProfileEvidenceQueueProgress(activeProfileBuildLastResult);
    }
  } else {
    renderProfileEnrichmentPlan(selected, buildable);
  }
  renderProfileDistillReadiness(selected);
  renderCreatorCloneOverview(profileScanPayload?.summary || cloneSummaryFromSet(profileScanPayload?.set) || {});
}

function selectedSampleReason(item) {
  const key = sampleViewItemKey(item);
  if (!key) {
    return "手动选择";
  }
  const highestLikes = topCreatorSampleViewItemsBy("like_count", 3).some((candidate) => sampleViewItemKey(candidate) === key);
  const highestComments = topCreatorSampleViewItemsBy("comment_count", 3).some((candidate) => sampleViewItemKey(candidate) === key);
  const highestShares = topCreatorSampleViewItemsBy("share_count", 3).some((candidate) => sampleViewItemKey(candidate) === key);
  const highestCollects = topCreatorSampleViewItemsBy("collect_count", 3).some((candidate) => sampleViewItemKey(candidate) === key);
  const newest = topCreatorSampleViewItemsBy("create_time", 3).some((candidate) => sampleViewItemKey(candidate) === key);
  const reasons = [];
  if (highestLikes) reasons.push("高赞");
  if (highestComments) reasons.push("高评");
  if (highestShares) reasons.push("高分享");
  if (highestCollects) reasons.push("高收藏");
  if (newest) reasons.push("最新");
  if (isSampleViewItemBuildable(item) && !item.has_frames) reasons.push("待富化");
  return reasons.join(" / ") || "手动选择";
}

function profileMetricText(item) {
  return [
    Number(item.like_count || 0) ? `赞 ${formatNumber(item.like_count)}` : "",
    Number(item.comment_count || 0) ? `评 ${formatNumber(item.comment_count)}` : "",
    Number(item.share_count || 0) ? `分享 ${formatNumber(item.share_count)}` : "",
    Number(item.collect_count || 0) ? `收藏 ${formatNumber(item.collect_count)}` : "",
  ].filter(Boolean).join(" · ");
}

function profileEvidenceText(item) {
  return [
    item.case_id ? "已有素材包" : "",
    item.has_frames ? "关键帧" : "",
    item.has_asr ? "ASR" : "",
    item.has_ocr ? "OCR" : "",
    item.has_comments ? "评论" : "",
    item.understanding_level || "metadata_only",
  ].filter(Boolean).join(" · ");
}

function profileSampleMetaLine(item) {
  const typeLabel = {video: "视频", image: "图文", unknown: "未知"}[item.media_type] || "未知";
  const evidence = `证据 ${profileEvidenceScore(item)}/5`;
  const buildable = isSampleViewItemBuildable(item) ? "可富化" : "参考样本";
  return [
    selectedSampleReason(item),
    profileMetricText(item),
    typeLabel,
    evidence,
    buildable,
    profileEvidenceText(item),
  ].filter(Boolean).join(" · ");
}

function profileEvidenceCounts(selected) {
  return normalizeItems(selected).reduce(
    (acc, item) => {
      acc.video += item.has_video ? 1 : 0;
      acc.frames += item.has_frames ? 1 : 0;
      acc.asr += item.has_asr ? 1 : 0;
      acc.ocr += item.has_ocr ? 1 : 0;
      acc.comments += item.has_comments ? 1 : 0;
      if (item.asr_status && item.asr_status !== "pending") acc.asrChecked += 1;
      if (item.ocr_status && item.ocr_status !== "pending") acc.ocrChecked += 1;
      if (item.asr_status === "provider_missing") acc.asrProviderMissing += 1;
      if (item.ocr_status === "provider_missing") acc.ocrProviderMissing += 1;
      return acc;
    },
    {video: 0, frames: 0, asr: 0, ocr: 0, comments: 0, asrChecked: 0, ocrChecked: 0, asrProviderMissing: 0, ocrProviderMissing: 0},
  );
}

function renderProfileEnrichmentPlan(selected, buildable) {
  if (!profileEvidenceStatus) {
    return;
  }
  const selectedItems = normalizeItems(selected);
  const buildableItems = normalizeItems(buildable);
  const referenceOnlyCount = Math.max(0, selectedItems.length - buildableItems.length);
  const counts = profileEvidenceCounts(selectedItems);
  const missingFrames = buildableItems.filter((item) => !item.has_frames).length;
  const missingAsr = buildableItems.filter((item) => !item.has_asr).length;
  const missingOcr = buildableItems.filter((item) => !item.has_ocr).length;
  const warning = buildableItems.length > PROFILE_BUILD_MAX_ITEMS;
  profileEvidenceStatus.classList.toggle("warning", warning);
  if (!selectedItems.length) {
    profileEvidenceStatus.innerHTML = "先从素材池选择代表样本；富化后会回填视频、关键帧、OCR、ASR 等证据，再进入大模型蒸馏。";
    return;
  }
  const limitNote = buildableItems.length > PROFILE_BUILD_MAX_ITEMS
    ? `可下载视频超过当前富化上限 ${PROFILE_BUILD_MAX_ITEMS} 条，请减少视频样本，避免误批量下载。`
    : "";
  const distillLimitNote = selectedItems.length > CREATOR_CLONE_MAX_DISTILL_SAMPLES
    ? `本轮可先富化全部样本；单次蒸馏上限 ${CREATOR_CLONE_MAX_DISTILL_SAMPLES} 条，超过后请使用“高级：分批蒸馏”做账号级汇总。`
    : "";
  const providerNote = [
    counts.asrProviderMissing ? `ASR provider 未配置 ${counts.asrProviderMissing} 条` : "",
    counts.ocrProviderMissing ? `OCR provider 未配置 ${counts.ocrProviderMissing} 条` : "",
  ].filter(Boolean).join("；");
  const headline = limitNote
    || (buildableItems.length
      ? `点击主按钮“开始富化证据”后，将处理 ${buildableItems.length} 条可下载视频，并保留 ${referenceOnlyCount} 条参考样本。`
      : `已选择 ${referenceOnlyCount} 条参考样本，不执行视频下载，可直接进入大模型蒸馏。`);
  const steps = buildableItems.length
    ? ["下载视频", "生成素材包", "抽关键帧", "OCR 画面文字", "ASR 语音", "写入蒸馏输入"]
    : ["保存参考样本", "整理标题/封面/指标", "写入蒸馏输入"];
  profileEvidenceStatus.innerHTML = `
    <div class="enrichment-plan-head">
      <strong>富化计划</strong>
      <p>${escapeHtml(headline)}</p>
    </div>
    <dl class="enrichment-plan-metrics">
      <div><dt>可下载视频</dt><dd>${formatNumber(buildableItems.length)}</dd></div>
      <div><dt>参考样本</dt><dd>${formatNumber(referenceOnlyCount)}</dd></div>
      <div><dt>待补关键帧</dt><dd>${formatNumber(missingFrames)}</dd></div>
      <div><dt>待补 OCR</dt><dd>${formatNumber(missingOcr)}</dd></div>
      <div><dt>待补 ASR</dt><dd>${formatNumber(missingAsr)}</dd></div>
    </dl>
    <div class="enrichment-plan-steps" aria-label="本轮富化步骤">
      ${steps.map((step) => `<span>${escapeHtml(step)}</span>`).join("")}
    </div>
    <p class="enrichment-plan-note">当前证据：视频 ${counts.video}/${selectedItems.length}，关键帧 ${counts.frames}/${selectedItems.length}，OCR ${counts.ocr}/${selectedItems.length}，ASR ${counts.asr}/${selectedItems.length}，评论 ${counts.comments}/${selectedItems.length}。${providerNote ? `${escapeHtml(providerNote)}。` : ""}${distillLimitNote ? `${escapeHtml(distillLimitNote)}。` : ""}</p>
  `;
}

function renderProfileEvidenceQueueProgress(result = {}) {
  if (!profileEvidenceStatus) {
    return;
  }
  const pipelineSummary = result.pipeline_summary || {};
  const selectedCount = Number(pipelineSummary.selected_count || selectedCreatorSampleViewItems().length || 0);
  const downloadableCount = Number(pipelineSummary.downloadable_count || 0);
  const referenceOnlyCount = Number(pipelineSummary.reference_only_count || 0);
  const downloadedCount = Number(pipelineSummary.downloaded_count || 0);
  const caseCount = Number(pipelineSummary.case_count || result.completed_count || 0);
  const enrichedCount = Number(pipelineSummary.enriched_count || 0);
  const asrCount = Number(pipelineSummary.asr_success_count || 0);
  const ocrCount = Number(pipelineSummary.ocr_success_count || 0);
  const readyCount = Number(pipelineSummary.ready_for_distill_count || 0);
  const failedCount = Number(result.failed_count || 0);
  const totalTarget = downloadableCount || selectedCount || 0;
  const notes = normalizeItems(pipelineSummary.notes).slice(-2);
  const runningNote = isProfileBuildJobActive()
    ? "页面刷新不会取消正在运行的后台富化任务；刷新后会自动恢复队列轮询。"
    : "";
  const staleNote = isProfileBuildJobActive() && isProfileBuildJobStale()
    ? "任务已较长时间没有进度更新，可能是服务重启或后台任务中断；可重新点击富化，已生成的素材包会优先复用。"
    : "";
  profileEvidenceStatus.classList.toggle("warning", Boolean(failedCount));
  profileEvidenceStatus.innerHTML = `
    <div class="enrichment-plan-head">
      <strong>富化进度</strong>
      <p>已选 ${formatNumber(selectedCount)} 条；视频 ${formatNumber(downloadableCount)} 条，参考 ${formatNumber(referenceOnlyCount)} 条。素材包 ${formatNumber(caseCount)}/${formatNumber(totalTarget)}，失败 ${formatNumber(failedCount)}。</p>
    </div>
    <dl class="enrichment-plan-metrics">
      <div><dt>下载</dt><dd>${formatNumber(downloadedCount)}</dd></div>
      <div><dt>素材包</dt><dd>${formatNumber(caseCount)}</dd></div>
      <div><dt>富化</dt><dd>${formatNumber(enrichedCount)}</dd></div>
      <div><dt>ASR</dt><dd>${formatNumber(asrCount)}</dd></div>
      <div><dt>OCR</dt><dd>${formatNumber(ocrCount)}</dd></div>
      <div><dt>可蒸馏</dt><dd>${formatNumber(readyCount)}</dd></div>
    </dl>
    ${runningNote ? `<p class="compact-copy">${escapeHtml(runningNote)}</p>` : ""}
    ${staleNote ? `<p class="compact-copy warning-text">${escapeHtml(staleNote)}</p>` : ""}
    ${notes.length ? `<ul class="profile-queue-note-list">${notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul>` : ""}
  `;
}

function updateProfileChromeContinueButton() {
  if (!profileContinueChromeButton) {
    return;
  }
  const canContinue = Boolean(currentCloneSetId && profileLastChromeProfileValue);
  profileContinueChromeButton.classList.toggle("hidden", !canContinue);
  profileContinueChromeButton.disabled = !canContinue;
}

function profileItemStatus(item) {
  if (item.case_id) {
    const bits = ["已生成素材包"];
    if (item.has_frames) bits.push("关键帧");
    if (item.asr_status && item.asr_status !== "pending") bits.push(`ASR ${item.asr_status}`);
    if (item.ocr_status && item.ocr_status !== "pending") bits.push(`OCR ${item.ocr_status}`);
    return bits.join(" · ");
  }
  if (item.can_build_case === false || item.media_type === "image") {
    return "暂不支持生成视频素材包";
  }
  if (item.media_type === "unknown") {
    return "待解析确认";
  }
  return "可解析";
}

function profileEvidenceBadges(item) {
  const evidence = [
    {id: "case", label: "素材包", ready: Boolean(item.case_id), checked: Boolean(item.case_id)},
    {id: "video", label: "视频", ready: Boolean(item.has_video), checked: Boolean(item.has_video)},
    {id: "frames", label: "关键帧", ready: Boolean(item.has_frames), checked: Boolean(item.has_frames)},
    {
      id: "asr",
      label: "ASR",
      ready: Boolean(item.has_asr),
      checked: Boolean(item.asr_status && item.asr_status !== "pending"),
      status: item.asr_status || "pending",
    },
    {
      id: "ocr",
      label: "OCR",
      ready: Boolean(item.has_ocr),
      checked: Boolean(item.ocr_status && item.ocr_status !== "pending"),
      status: item.ocr_status || "pending",
    },
    {id: "comments", label: "评论", ready: Boolean(item.has_comments), checked: Boolean(item.has_comments)},
    {
      id: "analysis",
      label: "AI",
      ready: item.analysis_status === "success",
      checked: Boolean(item.analysis_status && item.analysis_status !== "not_analyzed" && item.analysis_status !== "pending"),
      status: item.analysis_status || "not_analyzed",
    },
  ];
  return `
    <div class="profile-evidence-badges" aria-label="样本证据完整度">
      ${evidence
        .map((entry) => {
          const state = entry.ready ? "ready" : entry.checked ? "checked" : "missing";
          const title = entry.status ? `${entry.label}: ${entry.status}` : entry.ready ? `${entry.label}: 已具备` : `${entry.label}: 缺失`;
          return `<span class="evidence-chip ${state}" title="${escapeHtml(title)}">${escapeHtml(entry.label)}</span>`;
        })
        .join("")}
    </div>
  `;
}

function profileEvidenceCoverageSummary(items) {
  const rows = normalizeItems(items);
  const counts = rows.reduce(
    (acc, item) => {
      acc.total += 1;
      acc.video += item.has_video ? 1 : 0;
      acc.frames += item.has_frames ? 1 : 0;
      acc.asr += item.has_asr ? 1 : 0;
      acc.ocr += item.has_ocr ? 1 : 0;
      acc.comments += item.has_comments ? 1 : 0;
      acc.full += item.understanding_level === "full" ? 1 : 0;
      acc.partial += item.understanding_level === "partial" ? 1 : 0;
      acc.metadataOnly += !item.understanding_level || item.understanding_level === "metadata_only" ? 1 : 0;
      return acc;
    },
    {total: 0, video: 0, frames: 0, asr: 0, ocr: 0, comments: 0, full: 0, partial: 0, metadataOnly: 0},
  );
  if (!counts.total) {
    return "暂无素材";
  }
  return `完整 ${counts.full} / 部分 ${counts.partial} / 仅元数据 ${counts.metadataOnly}；视频 ${counts.video}，关键帧 ${counts.frames}，ASR ${counts.asr}，OCR ${counts.ocr}，评论 ${counts.comments}`;
}

function renderProfileSummary(summary) {
  if (!summary || !profileSummary) {
    return;
  }
  renderCreatorCloneOverview(summary);
}

function renderProfileDecisionBoard(payload) {
  if (!profileDecisionBoard) {
    return;
  }
  const items = activeCreatorSampleViewItems();
  if (!items.length) {
    profileDecisionBoard.classList.add("hidden");
    profileDecisionBoard.innerHTML = "";
    return;
  }
  const buildable = items.filter(isSampleViewItemBuildable);
  const videoCount = items.filter((item) => item.media_type === "video").length;
  const imageCount = items.filter((item) => item.media_type === "image").length;
  const unknownCount = items.filter((item) => item.media_type === "unknown").length;
  const referenceCount = Math.max(0, items.length - buildable.length);
  const metricCount = items.filter((item) => Number(item.like_count || 0) || Number(item.comment_count || 0) || Number(item.share_count || 0) || Number(item.collect_count || 0)).length;
  const profileMeta = payload?.set?.profile_metadata || payload?.summary?.profile_metadata || {};
  const creatorName = profileMeta.nickname || payload?.set?.creator_name || "当前账号";
  const evidenceText = profileEvidenceCoverageSummary(items);
  const topLike = topCreatorSampleViewItemsBy("like_count", 1)[0];
  const topComment = topCreatorSampleViewItemsBy("comment_count", 1)[0];
  const topShare = topCreatorSampleViewItemsBy("share_count", 1)[0];
  const latest = topCreatorSampleViewItemsBy("create_time", 1)[0];
  const qualityText = metricCount
    ? `${formatNumber(metricCount)}/${formatNumber(items.length)} 条带互动数据，可按点赞、评论、分享、收藏排序。`
    : "互动指标不足，建议改用 JSON / CSV 或本机 Chrome 辅助补充。";
  profileDecisionBoard.classList.remove("hidden");
  profileDecisionBoard.innerHTML = `
    <div class="section-heading-row compact-row">
      <div>
        <div class="entry-label">Decision Board</div>
        <h3>素材池决策概览</h3>
      </div>
      <span class="status-badge muted-badge">${escapeHtml(creatorName)}</span>
    </div>
    <div class="profile-decision-grid">
      <article class="profile-decision-card">
        <span>样本结构</span>
        <strong>${formatNumber(items.length)} 条素材 · ${formatNumber(buildable.length)} 条可富化</strong>
        <p>视频 ${formatNumber(videoCount)} / 图文 ${formatNumber(imageCount)} / 未知 ${formatNumber(unknownCount)} / 参考样本 ${formatNumber(referenceCount)}</p>
      </article>
      <article class="profile-decision-card">
        <span>互动数据</span>
        <strong>${escapeHtml(qualityText)}</strong>
        <p>排序和筛选集中在下一步“选择样本”中完成。</p>
      </article>
      <article class="profile-decision-card">
        <span>证据覆盖</span>
        <strong>${escapeHtml(evidenceText)}</strong>
        <p>富化后会补齐视频、关键帧、ASR、OCR，供大模型蒸馏使用。</p>
      </article>
      <article class="profile-decision-card wide">
        <span>代表样本线索</span>
        <strong>${escapeHtml([
          topLike ? `高赞：${topLike.title || topLike.aweme_id || topLike.sample_id}` : "",
          topComment ? `高评：${topComment.title || topComment.aweme_id || topComment.sample_id}` : "",
          topShare ? `高分享：${topShare.title || topShare.aweme_id || topShare.sample_id}` : "",
          latest ? `最新：${latest.title || latest.aweme_id || latest.sample_id}` : "",
        ].filter(Boolean).join(" / ") || "暂无可排序样本")}</strong>
        <p>下一步进入样本选择，用推荐组合或表头筛选手动确认 N 条代表样本。</p>
      </article>
      <article class="profile-decision-card featured">
        <span>下一步</span>
        <strong>进入样本选择，按表头筛选确认代表样本。</strong>
        <div class="decision-card-actions">
          <button type="button" data-profile-stage-go="select">进入样本选择</button>
        </div>
      </article>
    </div>
  `;
}

function renderProfileSegmentsPreview(segments) {
  if (!profileSegmentsPreview) {
    return;
  }
  const items = activeCreatorSampleViewItems();
  const latestItems = items.length
    ? sortCreatorSampleViewItems(items, "create_time").slice(0, 5).map((item) => ({
        ...item,
        metric_value: item.create_time || "",
      }))
    : [];
  const sectionDefs = [
    ["高赞样本", "like_count", segments?.highest_like_samples, "top_likes"],
    ["高评论样本", "comment_count", segments?.highest_comment_samples, "top_comments"],
    ["高分享样本", "share_count", segments?.highest_share_samples, "top_shares"],
    ["高收藏样本", "collect_count", segments?.highest_collect_samples, "top_collects"],
    ["最新样本", "create_time", latestItems, "latest"],
    ["低表现 / 对照样本", "engagement_score", segments?.weak_or_reference_samples, "low_performance"],
  ];
  const hasAny = sectionDefs.some(([, , items]) => normalizeItems(items).length);
  if (!hasAny) {
    profileSegmentsPreview.classList.add("hidden");
    profileSegmentsPreview.innerHTML = "";
    return;
  }
  profileSegmentsPreview.classList.remove("hidden");
  profileSegmentsPreview.innerHTML = `
    <div class="section-heading-row compact-row">
      <div>
        <div class="entry-label">Performance Segments</div>
        <h3>表现分层预览</h3>
      </div>
      <span class="status-badge muted-badge">蒸馏前参考</span>
    </div>
    <div class="profile-segment-grid">
      ${sectionDefs
        .map(([title, metricKey, items, preset]) => renderProfileSegmentColumn(title, metricKey, items, preset))
        .join("")}
    </div>
  `;
}

function renderProfileSegmentColumn(title, metricKey, items, preset) {
  const rows = normalizeItems(items).slice(0, 3);
  const metricLabel = {
    like_count: "赞",
    comment_count: "评",
    share_count: "分享",
    collect_count: "收藏",
    engagement_score: "综合",
    create_time: "时间",
  }[metricKey] || "指标";
  return `
    <article class="profile-segment-column">
      <div class="profile-segment-column-head">
        <strong>${escapeHtml(title)}</strong>
      </div>
      ${
        rows.length
          ? `<ol>${rows
              .map((item) => {
                const value = item.metric_value ?? item[metricKey] ?? 0;
                return `<li><span>${escapeHtml(item.title || item.aweme_id || item.sample_id || "未命名样本")}</span><em>${escapeHtml(metricLabel)} ${formatNumber(value)}</em></li>`;
              })
              .join("")}</ol>`
          : `<p class="muted compact-copy">暂无可用数据。</p>`
      }
    </article>
  `;
}

function renderProfileResults(payload) {
  profileScanPayload = payload;
  currentRepresentativeSampleSelection = null;
  representativeRecommendationState = "idle";
  representativeRecommendationMessage = "";
  representativeRecommendationGeneration += 1;
  clearCreatorCloneRenderedReport();
  currentCreatorIntelligenceStrategy = null;
  applyCreatorIntelligencePayload(payload);
  const cloneSet = payload.set || null;
  currentCloneSetId = cloneSet?.set_id || "";
  if (profileContentProfile && cloneSet?.content_profile) {
    profileContentProfile.value = cloneSet.content_profile;
  }
  currentCloneProfileFingerprint = profileFingerprintFromPayload(payload);
  if (currentCloneSetId) {
    rememberRecentCreatorCloneSetId(currentCloneSetId);
  }
  runtimeSampleRows = normalizeItems(payload.items || cloneSet?.samples);
  const persistedSelected = normalizeItems(cloneSet?.selected_sample_ids);
  profileSelectedKeys = persistedSelected.length
    ? new Set(persistedSelected)
    : new Set([...profileSelectedKeys].filter((key) => runtimeSampleRows.some((item) => sampleViewItemKey(item) === key)));
  profileResultsCard.classList.remove("hidden");
  profileQueueCard.classList.add("hidden");
  profileProviderBadge.textContent = cloneSet ? "creator clone lab" : (payload.provider || "profile");
  const warnings = normalizeItems(payload.warnings || cloneSet?.warnings);
  profileWarnings.classList.toggle("hidden", !warnings.length);
  profileWarnings.textContent = warnings.join(" ");
  renderProfileCaptureAudit(payload.capture_audit || cloneSet?.capture_audit || null);
  renderProfileSummary(payload.summary || cloneSummaryFromSet(cloneSet) || {});
  renderProfileDecisionBoard(payload);
  renderProfileSegmentsPreview(payload.performance_segments || cloneSet?.performance_segments || null);
  renderProfileTable();
  updateCreatorCloneSelectionStatus();
  void refreshRepresentativeSampleRecommendations();
  updateProfileChromeContinueButton();
  commitCreatorCloneUnifiedInput();
  if (profileStageView === "import") {
    setProfileStageView("select");
  } else {
    renderProfileStageView();
  }
  const restoredResult = payload.creator_intelligence?.result || currentCreatorIntelligenceResult || null;
  const restoredStrategy = payload.creator_intelligence?.strategy_output || creatorStrategyFromResult(restoredResult || {}) || null;
  const workflowState = payload.creator_intelligence?.workflow?.state || "";
  if ((restoredResult || restoredStrategy) && workflowState === "DONE") {
    renderCreatorCloneResult(
      restoredResult || creatorCloneResultFromStrategyOutput(restoredStrategy),
      cloneSet,
      currentDistillPrompt,
      payload.exports || {},
      {scroll: false},
    );
  }
}

function renderProfileCaptureAudit(audit) {
  if (!profileCaptureAudit) {
    return;
  }
  if (!audit || typeof audit !== "object" || !audit.capture_method) {
    profileCaptureAudit.classList.add("hidden");
    profileCaptureAudit.innerHTML = "";
    return;
  }
  const safety = audit.safety || {};
  const contract = audit.security_contract || {};
  const authorization = audit.authorization || {};
  const mediaSummary = audit.media_summary || {};
  const fieldCoverage = audit.field_coverage || {};
  const fieldTotal = Number(fieldCoverage.total || audit.final_sample_count || audit.captured_count || 0);
  const safetyItems = [
    ["本机访问", safety.loopback_only],
    ["一次性 token", safety.one_time_token_required],
    ["页面确认", safety.page_confirmation_required],
    ["未读取 Cookie", safety.cookie_read === false],
    ["未返回 Cookie", safety.cookie_returned === false],
    ["未写 Cookie 日志", safety.cookie_logged === false],
    ["只读 DOM 元数据", safety.dom_visible_metadata_only],
    ["敏感字段过滤", safety.sensitive_fields_redacted],
  ];
  const contractItems = [
    ["请求来源", contract.requests_from_user_machine ? "用户本机 Chrome / 本机 IP" : "未知"],
    ["公开站接收", contract.public_site_cookie_free ? "仅净化元数据" : "需复核"],
    ["Cookie", contract.cookie_read === false && contract.cookie_returned === false && contract.cookie_logged === false ? "不读 / 不传 / 不记" : "需复核"],
    ["签名媒体 URL", contract.signed_media_url_returned === false ? "不返回" : "需复核"],
  ];
  const authorizationItems = [
    ["页面确认", authorization.page_confirmed === true ? "已确认" : "未记录"],
    ["一次性 token", authorization.one_time_token_consumed === true ? "已消费" : "未记录"],
    ["触发来源", authorization.trigger || "unknown"],
  ];
  const returnedScope = normalizeItems(contract.returned_data_scope)
    .map((item) => String(item))
    .filter(Boolean);
  const coverageItems = [
    ["标题", fieldCoverage.with_title],
    ["来源链接", fieldCoverage.with_source_url],
    ["封面", fieldCoverage.with_cover_url],
    ["作者", fieldCoverage.with_author],
    ["发布时间", fieldCoverage.with_create_time],
    ["标签", fieldCoverage.with_tags],
    ["互动指标", fieldCoverage.with_any_visible_metric],
  ];
  const boundaryOk = safetyItems.every(([, ok]) => Boolean(ok))
    && contract.public_site_cookie_free === true
    && contract.requests_from_user_machine === true
    && contract.cookie_read === false
    && contract.cookie_returned === false
    && contract.cookie_logged === false
    && contract.signed_media_url_returned === false;
  const nextStep = Number(mediaSummary.buildable_item_count || 0) > 0
    ? "下一步：按点赞、评论、时间等维度选择代表视频，点击主按钮开始富化证据。"
    : "下一步：当前多为图文/元数据参考，可直接选样蒸馏，或继续采集更多可富化视频。";
  profileCaptureAudit.classList.remove("hidden");
  profileCaptureAudit.innerHTML = `
    <div class="capture-audit-heading">
      <strong>最近采集审计</strong>
      <span>${escapeHtml(audit.capture_method || "unknown")}</span>
    </div>
    <div class="capture-audit-verdict ${boundaryOk ? "safe" : "warning"}">
      <strong>${boundaryOk ? "本机辅助采集边界通过" : "本机辅助采集边界需复核"}</strong>
      <p>${boundaryOk ? "请求由用户本机 Chrome / 本机 IP 发起；页面只接收净化后的作品列表和元数据，不接收 Cookie、登录 token、签名媒体 URL 或原始请求头。" : "请先复核安全契约：本轮采集必须只返回可见作品元数据，且不读取、不上传、不记录 Cookie。"}</p>
      <p>${escapeHtml(nextStep)}</p>
    </div>
    <dl class="capture-audit-metrics">
      <dt>采集时间</dt><dd>${escapeHtml(audit.captured_at || "未知")}</dd>
      <dt>滚动轮数</dt><dd>${formatNumber(audit.scroll_count)}</dd>
      <dt>采集样本</dt><dd>${formatNumber(audit.captured_count)}</dd>
      <dt>当前素材池</dt><dd>${formatNumber(audit.final_sample_count)}</dd>
      <dt>合并采集</dt><dd>${audit.merged_into_existing_set ? "是" : "否"}</dd>
      <dt>可富化素材</dt><dd>${formatNumber(mediaSummary.buildable_item_count)}</dd>
      <dt>图文/照片</dt><dd>${formatNumber(mediaSummary.image_count)}</dd>
      <dt>仅元数据</dt><dd>${formatNumber(mediaSummary.metadata_only_count)}</dd>
    </dl>
    <div class="capture-field-coverage" aria-label="字段覆盖率">
      <strong>字段覆盖</strong>
      <div class="capture-field-grid">
        ${coverageItems
          .map(([label, value]) => {
            const count = Number(value || 0);
            const ratio = fieldTotal ? Math.round((count / fieldTotal) * 100) : 0;
            return `<span title="${escapeHtml(label)}覆盖 ${formatNumber(count)}/${formatNumber(fieldTotal)}">${escapeHtml(label)} ${formatNumber(count)}/${formatNumber(fieldTotal)} · ${formatNumber(ratio)}%</span>`;
          })
          .join("")}
      </div>
    </div>
    <div class="capture-audit-safety">
      ${safetyItems
        .map(([label, ok]) => `<span class="${ok ? "ok" : "warn"}">${escapeHtml(label)}：${ok ? "是" : "否"}</span>`)
        .join("")}
    </div>
    <div class="security-contract-card">
      <strong>安全契约</strong>
      <dl>
        ${contractItems.map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`).join("")}
      </dl>
      <p>回传范围：${escapeHtml(returnedScope.join(" / ") || "账号可见元数据 / 可见作品列表 / 可见互动指标 / 净化作品链接")}</p>
    </div>
    <div class="security-contract-card">
      <strong>本次授权</strong>
      <dl>
        ${authorizationItems.map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd>`).join("")}
      </dl>
      <p>只有页面按钮触发并消费一次性 token 后，才会执行真正的本机 Chrome 作品列表读取。</p>
    </div>
    <div class="handoff-manifest-callout">
      <strong>安全交接包</strong>
      <p>已准备 handoff_manifest.json：只包含账号素材清单、可见互动指标和安全审计；公开网站只接收净化后的元数据，不接收 Cookie、登录 token、签名 URL 或原始请求头。</p>
      ${
        currentCloneSetId
          ? `<a class="button-link" href="/api/creator-clone/sets/${encodeURIComponent(currentCloneSetId)}/files/handoff_manifest.json" target="_blank" rel="noreferrer">下载 handoff_manifest.json</a>`
          : ""
      }
    </div>
    <p class="muted compact-copy">该审计只记录采集方式、安全边界、滚动轮数和样本数，不包含 Cookie、签名 URL 或登录 token。</p>
  `;
}

function cloneSummaryFromSet(set) {
  if (!set) {
    return null;
  }
  const samples = normalizeItems(set.samples);
  return {
    scanned_count: set.sample_count || samples.length,
    video_count: samples.filter((item) => item.media_type === "video").length,
    max_engagement_score: Math.max(0, ...samples.map((item) => Number(item.engagement_score || 0))),
    avg_like_count: averageMetric(samples, "like_count"),
    avg_comment_count: averageMetric(samples, "comment_count"),
    avg_share_count: averageMetric(samples, "share_count"),
    top_items: sortCreatorSampleViewItems(samples, "engagement_score").slice(0, 3),
    profile_metadata: set.profile_metadata || {},
    content_keywords: [],
  };
}

function averageMetric(items, key) {
  const values = normalizeItems(items).map((item) => Number(item[key] || 0));
  if (!values.length) {
    return 0;
  }
  return Math.round(values.reduce((sum, value) => sum + value, 0) / values.length);
}

function isProfileFallbackError(error) {
  return ["DOUYIN_RISK_CONTROL", "PROFILE_SCAN_NEEDS_FALLBACK", "PROFILE_SCAN_FAILED"].includes(error?.error_code);
}

function showProfileFallback(error, options = {}) {
  const chromeFirst = Boolean(options.chromeFirst);
  profileFallbackHint.classList.remove("hidden");
  profileFallbackHint.innerHTML = `
    <strong>${chromeFirst ? "公开扫描受限，准备切换到本机 Chrome 辅助采集。" : "已切换到稳定兜底方式：多作品链接粘贴。"}</strong>
    <p>${chromeFirst ? "当前公开主页没有返回可解析作品列表，系统会引导你使用本机已打开的抖音主页做只读采集；如果 Chrome 辅助仍不可用，再使用多作品链接粘贴兜底。" : "主页被平台限制，当前不登录、不使用 Cookie、不绕风控，因此无法直接读取作品列表。建议复制多条作品链接到下方输入框，系统会整理成账号作品池。"}</p>
    <p class="muted compact-copy">调试信息：${escapeHtml(error.error_code || "PROFILE_SCAN_FAILED")}：${escapeHtml(error.message || "主页扫描失败")}</p>
  `;
  if (!chromeFirst) {
    profileManualSection.open = true;
    profileManualLinks.focus();
  }
}

async function prepareChromeProfileFallback(error) {
  showProfileFallback(error, {chromeFirst: true});
  if (profilePublicSection) {
    profilePublicSection.open = true;
  }
  if (profileChromeConfirm) {
    profileChromeConfirm.checked = false;
  }
  profileScanStatus.textContent = `${error.error_code || "PROFILE_SCAN_FAILED"}：公开扫描受限。请确认本机 Chrome 辅助采集边界后，点击“本机 Chrome 辅助入口”。`;
  try {
    await loadChromeHelperStatus({silent: true});
  } catch (statusError) {
    profileScanStatus.textContent = `${error.error_code || "PROFILE_SCAN_FAILED"}：公开扫描受限。请在本机 Chrome 打开目标抖音主页，完成登录/验证后再点击“本机 Chrome 辅助入口”。`;
  }
}

function chromeHelperNextAction(status) {
  if (status.ready_for_profile_scan) {
    return "下一步：点击“本机 Chrome 辅助入口”。页面会先申请一次性 token，再由你确认后读取当前主页可见作品。";
  }
  if (!status.chrome_available) {
    return "下一步：在本机 Chrome 打开目标抖音主页；如果本地助手需要调试 Chrome，请按设置预检中的提示启动。";
  }
  if (Number(status.douyin_profile_tab_count || 0) <= 0) {
    return "下一步：在已登录的本机 Chrome 中打开目标主页，页面加载完成后回到这里点击“本机 Chrome 辅助入口”。";
  }
  return "下一步：确认目标主页已经加载完成，然后点击“本机 Chrome 辅助入口”。";
}

function renderChromeHelperStatus(status) {
  if (!profileChromeStatus) {
    return;
  }
  const tabs = normalizeItems(status.douyin_tabs);
  const tabText = tabs.length
    ? `检测到 ${tabs.length} 个抖音标签页：${tabs.map((tab, index) => tab.label || (tab.is_profile ? `抖音主页 #${index + 1}` : `抖音标签页 #${index + 1}`)).slice(0, 2).join(" / ")}`
    : "未检测到抖音标签页";
  const launchHint = status.launch_hint ? ` 启动命令：${status.launch_hint}` : "";
  profileChromeAvailable = Boolean(status.chrome_available);
  profileChromeLaunchCommand = status.launch_hint || "";
  profileChromeStatus.classList.toggle("ready", Boolean(status.ready_for_profile_scan));
  profileChromeStatus.classList.toggle("blocked", !status.ready_for_profile_scan);
  const securityItems = normalizeItems(status.security).slice(0, 4);
  const dataScope = normalizeItems(status.returned_data_scope).map((item) => item.replaceAll("_", " ")).join(" / ");
  const requestOrigin = status.request_origin === "user_local_chrome_and_user_local_ip"
    ? "用户本机 Chrome / 本机 IP"
    : String(status.request_origin || "本机");
  const readinessLabel = status.ready_for_profile_scan ? "可扫描" : "未就绪";
  profileChromeStatus.innerHTML = `
    <strong>本机 Chrome 辅助状态：<span class="helper-readiness ${status.ready_for_profile_scan ? "ready" : "blocked"}">${readinessLabel}</span></strong>
    <p>${escapeHtml(status.status_message || "状态未知。")}</p>
    ${status.profile_note ? `<p>${escapeHtml(status.profile_note)}</p>` : ""}
    <span>${escapeHtml(tabText)}。</span>
    <p>${escapeHtml(status.next_action || chromeHelperNextAction(status))}</p>
    <p>请求来源：${escapeHtml(requestOrigin)}；返回范围：${escapeHtml(dataScope || "账号资料和作品元数据")}。</p>
    ${launchHint ? `<code>${escapeHtml(launchHint)}</code>` : ""}
    ${securityItems.length ? `<ul>${securityItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
  `;
}

async function loadChromeHelperStatus({silent = false} = {}) {
  if (profileChromeStatus && !silent) {
    profileChromeStatus.textContent = "本机 Chrome 辅助状态：正在检测...";
  }
  const response = await fetch("/api/local-helper/chrome/status", {cache: "no-store"});
  const payload = await readJsonResponse(response);
  renderChromeHelperStatus(payload);
  return payload;
}

async function requestChromeScanToken() {
  const tokenResponse = await fetch("/api/local-helper/chrome/scan-token", {method: "POST"});
  return readJsonResponse(tokenResponse);
}

function requireProfileChromeConfirmation() {
  if (!profileChromeConfirm || profileChromeConfirm.checked) {
    return true;
  }
  const advanced = profileChromeConfirm.closest("details");
  if (advanced) {
    advanced.open = true;
  }
  profileScanStatus.textContent = "请先勾选本次辅助采集确认：请求由本机 Chrome / 本机 IP 发起，只读取页面可见作品列表和元数据，不读取 Cookie。";
  return false;
}

function resetProfileChromeConfirmation() {
  if (profileChromeConfirm) {
    profileChromeConfirm.checked = false;
  }
}

function localChromeConfirmationPayload(extra = {}) {
  return {
    ...extra,
    page_confirmed: Boolean(profileChromeConfirm?.checked),
  };
}

async function openProfileInLocalChrome(profileValue) {
  const tokenPayload = await requestChromeScanToken();
  const response = await fetch("/api/local-helper/chrome/open-profile", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(localChromeConfirmationPayload({profile_url: profileValue, token: tokenPayload.token})),
  });
  return readJsonResponse(response);
}

async function launchLocalChrome(profileValue = "") {
  const tokenPayload = await requestChromeScanToken();
  const response = await fetch("/api/local-helper/chrome/launch", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(localChromeConfirmationPayload({profile_url: profileValue, token: tokenPayload.token})),
  });
  return readJsonResponse(response);
}

async function copyTextToClipboard(value) {
  if (!value) {
    return false;
  }
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return true;
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "readonly");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  return copied;
}

function currentProfileTargetValue() {
  const formData = new FormData(profileForm);
  const rawProfileValue = String(formData.get("profile_url") || "").trim();
  return firstUrlFromText(rawProfileValue) || rawProfileValue || profileLastChromeProfileValue;
}

// Creator Clone: sample table
function renderProfileTable() {
  renderCompactProfileTable();
}

function renderCompactProfileTable() {
  const sorted = visibleCreatorSampleViewItems();
  if (!sorted.length) {
    profileResultsBody.innerHTML = '<tr><td colspan="7" class="muted">当前筛选下没有素材。可以切换证据筛选，或改用粘贴作品链接、JSON / CSV、已有 Case 导入。</td></tr>';
    return;
  }
  const groupOrder = profileMediaFilter?.value === "all" ? ["video", "image", "unknown"] : [profileMediaFilter?.value || "all"];
  const groups = groupOrder
    .map((type) => {
      const rows = sorted.filter((item) => {
        const mediaType = item.media_type || "unknown";
        return type === "unknown" ? !["video", "image"].includes(mediaType) : mediaType === type;
      });
      return {type, rows};
    })
    .filter((group) => group.rows.length);
  profileResultsBody.innerHTML = groups
    .map((group) => {
      const label = {video: "视频素材", image: "图文/照片素材", unknown: "未知类型素材"}[group.type] || "素材";
      return `
        <tr class="profile-group-row"><td colspan="7">${escapeHtml(label)} · ${formatNumber(group.rows.length)} 条</td></tr>
        ${group.rows.map(renderProfileTableRow).join("")}
      `;
    })
    .join("");
  installProfileCoverFallbacks();
}

function profileCoverMarkup(item) {
  const title = item.title || item.desc || item.aweme_id || item.sample_id || "素材";
  if (!item.cover_url) {
    return profileCoverFallbackMarkup(item, "无封面");
  }
  return `<img src="${escapeHtml(item.cover_url)}" alt="${escapeHtml(title)}" class="profile-cover" loading="lazy" referrerpolicy="no-referrer" data-profile-cover-url="${escapeHtml(item.cover_url)}" data-profile-cover-fallback="${escapeHtml(profileCoverFallbackLabel(item))}">`;
}

function profileCoverFallbackLabel(item) {
  const type = item.media_type || "unknown";
  return type === "video" ? "视频" : type === "image" ? "图文" : "无封面";
}

function profileCoverFallbackMarkup(item, label = "") {
  const coverUrl = item.cover_url || "";
  const text = label || profileCoverFallbackLabel(item);
  if (coverUrl) {
    return `<div class="profile-cover placeholder"><span>封面受限</span><small>${escapeHtml(text)}</small></div>`;
  }
  return `<div class="profile-cover placeholder"><span>${escapeHtml(text)}</span></div>`;
}

function installProfileCoverFallbacks() {
  profileResultsBody.querySelectorAll("img.profile-cover").forEach((image) => {
    image.addEventListener("error", () => {
      const label = image.dataset.profileCoverFallback || "无封面";
      const coverUrl = image.dataset.profileCoverUrl || "";
      if (coverUrl) {
        const fallback = document.createElement("div");
        fallback.className = "profile-cover placeholder";
        fallback.innerHTML = `<span>封面受限</span><small>${escapeHtml(label)}</small>`;
        image.replaceWith(fallback);
        return;
      }
      const fallback = document.createElement("div");
      fallback.className = "profile-cover placeholder";
      fallback.innerHTML = `<span>${escapeHtml(label)}</span>`;
      image.replaceWith(fallback);
    }, {once: true});
  });
}

function renderProfileTableRow(item) {
  const typeLabel = {video: "视频", image: "图文/照片", unknown: "未知"}[item.media_type] || "未知";
  const status = profileItemStatus(item);
  const level = item.understanding_level || "metadata_only";
  const levelLabel = {full: "完整", partial: "部分", metadata_only: "仅元数据"}[level] || "仅元数据";
  const evidenceBadges = profileEvidenceBadges(item);
  const key = sampleViewItemKey(item);
  const checked = profileSelectedKeys.has(key) ? " checked" : "";
  const awemeLabel = item.aweme_id || item.case_id || item.sample_id || "无";
  const titleText = item.title || item.desc || awemeLabel;
  const secondaryText = [item.desc, item.source_url || item.webpage_url]
    .map((value) => String(value || "").trim())
    .find((value) => value && value !== titleText) || "";
  const sourceHref = item.source_url || item.webpage_url || (item.aweme_id ? `https://www.douyin.com/video/${item.aweme_id}` : "");
  const sourceLink = sourceHref
    ? `<a class="text-link profile-source-link" href="${escapeHtml(sourceHref)}" target="_blank" rel="noreferrer">来源</a>`
    : "";
  const caseLink = item.case_id
    ? `<a class="text-link profile-source-link" href="/cases/${escapeHtml(item.case_id)}" target="_blank" rel="noreferrer">打开 Case</a>`
    : "";
  const primaryAction = item.case_id
    ? caseLink
    : isSampleViewItemBuildable(item)
      ? `<button type="button" class="text-button" data-profile-select-action="${escapeHtml(key)}">选入富化</button>`
      : sourceLink || `<span class="muted">仅参考</span>`;
  const metricLines = [
    `赞 ${formatNumber(item.like_count)}`,
    `评 ${formatNumber(item.comment_count)}`,
    `分享 ${formatNumber(item.share_count)}`,
    `收藏 ${formatNumber(item.collect_count)}`,
    `综合 ${formatNumber(item.engagement_score)}`,
  ];
  return `
    <tr>
      <td><input type="checkbox" data-profile-select value="${escapeHtml(key)}"${checked}></td>
      <td>
        <div class="profile-material-cell">
          ${profileCoverMarkup(item)}
          <div>
            <strong>${escapeHtml(titleText)}</strong>
            ${secondaryText ? `<p>${escapeHtml(secondaryText)}</p>` : ""}
            <code>${escapeHtml(awemeLabel)}</code>
            ${representativeSampleMarkup(item)}
          </div>
        </div>
      </td>
      <td><span class="profile-media-type ${escapeHtml(item.media_type || "unknown")}">${escapeHtml(typeLabel)}</span></td>
      <td>
        <div class="profile-metric-stack">${metricLines.map((line) => `<span>${escapeHtml(line)}</span>`).join("")}</div>
      </td>
      <td><span class="profile-item-status ${escapeHtml(level)}">${escapeHtml(levelLabel)}</span>${evidenceBadges}</td>
      <td><span class="profile-item-status ${escapeHtml(item.media_type || "unknown")}">${escapeHtml(status)}</span></td>
      <td><div class="profile-row-actions">${primaryAction}${caseLink && sourceLink ? sourceLink : ""}</div></td>
    </tr>
  `;
}

function profileScanMaxPagesForCount(count) {
  const target = Number(count || 20);
  return Math.max(1, Math.min(20, Math.ceil(target / 10)));
}

async function scanProfile(sourceMode = "public") {
  let activeSource = "public";
  profileScanButton.disabled = true;
  profileScanStatus.textContent = "正在扫描主页并生成账号素材清单...";
  profileResultsCard.classList.add("hidden");
  profileFallbackHint.classList.add("hidden");
  profileLastChromeProfileValue = "";
  updateProfileChromeContinueButton();
  try {
    const formData = new FormData(profileForm);
    const rawProfileValue = String(formData.get("profile_url") || "").trim();
    const profileValue = firstUrlFromText(rawProfileValue) || rawProfileValue;
    const isUrl = /^https?:\/\//i.test(profileValue);
    activeSource = ["public", "manual", "structured", "handoff", "case"].includes(sourceMode) ? sourceMode : "public";
    if (activeSource === "public" && resetCreatorClonePoolIfProfileChanged(profileValue)) {
      profileScanStatus.textContent = "检测到新的主页链接，已清空上一次素材池，正在重新扫描...";
    }
    const requestedCount = Number(formData.get("count") || 20);
    const requestedMaxPages = activeSource === "public" ? profileScanMaxPagesForCount(requestedCount) : 1;
    const profilePayload = {
      profile_url: activeSource === "public" && isUrl ? profileValue : "",
      sec_user_id: activeSource === "public" && !isUrl ? profileValue : "",
      manual_links: activeSource === "manual" ? String(formData.get("manual_links") || "") : "",
      structured_items: activeSource === "structured" ? String(formData.get("structured_items") || "") : "",
      count: requestedCount,
      max_pages: requestedMaxPages,
      sort_by: String(profileSort?.value || "like_count"),
    };
    const clonePayload = {
      title: "创作者蒸馏素材池",
      source_platform: "douyin",
      profile_url: profilePayload.profile_url,
      sec_user_id: profilePayload.sec_user_id,
      manual_links: profilePayload.manual_links,
      structured_items: profilePayload.structured_items,
      case_ids: activeSource === "case" ? String(formData.get("case_ids") || "") : "",
      count: profilePayload.count,
      max_pages: profilePayload.max_pages,
      sort_by: profilePayload.sort_by,
    };
    let endpoint = "/api/creator-clone/import";
    let requestBody = clonePayload;
    if (activeSource === "handoff") {
      const rawHandoff = String(formData.get("handoff_manifest") || "").trim();
      if (!rawHandoff) {
        throw {error_code: "HANDOFF_MANIFEST_INVALID", message: "请先粘贴 handoff_manifest.json。"};
      }
      try {
        const tokenResponse = await fetch("/api/creator-clone/handoff-token", {method: "POST"});
        const tokenPayload = await readJsonResponse(tokenResponse);
        requestBody = {handoff_manifest: JSON.parse(rawHandoff), handoff_token: tokenPayload.token};
      } catch (error) {
        if (error?.error_code) {
          throw error;
        }
        throw {error_code: "HANDOFF_MANIFEST_INVALID", message: "handoff_manifest.json 不是合法 JSON。"};
      }
      endpoint = "/api/creator-clone/import-handoff";
    }
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(requestBody),
    });
    const result = await readJsonResponse(response);
    const stats = result.import_stats || {};
    const itemCount = result.items?.length || result.set?.sample_count || 0;
    const statsText = stats.input_count
      ? ` 成功识别 ${stats.recognized_count || 0} 条，去重 ${stats.duplicate_count || 0} 条，忽略 ${stats.invalid_count || 0} 条。`
      : "";
    profileScanStatus.textContent = `账号素材清单已生成：${itemCount} 条素材。${statsText}`;
    renderProfileResults(result);
  } catch (error) {
    if (activeSource === "public" && isProfileFallbackError(error)) {
      await prepareChromeProfileFallback(error);
    } else {
      profileScanStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "导入失败，请改用多作品链接粘贴、JSON / CSV 或已有 Case。"}`;
      if (isProfileFallbackError(error)) {
        showProfileFallback(error);
      }
    }
  } finally {
    profileScanButton.disabled = false;
    renderCreatorCloneNextAction();
  }
}

async function scanProfileWithLocalChrome(options = {}) {
  const profileValue = currentProfileTargetValue();
  const profileChanged = resetCreatorClonePoolIfProfileChanged(profileValue);
  const continueScan = Boolean(options.continueScan) && !profileChanged && Boolean(currentCloneSetId);
  if (!profileValue) {
    profileScanStatus.textContent = "请先填写主页 URL / sec_user_id，并在 Chrome 中打开该主页。";
    return;
  }
  if (!requireProfileChromeConfirmation()) {
    return;
  }
  let status;
  try {
    status = await loadChromeHelperStatus();
  } catch (error) {
    profileScanStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "无法检测本机 Chrome 辅助状态"}`;
    return;
  }
  if (!status.ready_for_profile_scan) {
    if (status.chrome_available && !continueScan) {
      const profileModeHint = status.profile_mode === "dedicated"
        ? "当前连接的是项目专用调试 Chrome，不是你的日常 Chrome；日常 Chrome 里已经打开的抖音主页不会被识别。"
        : "当前连接的是已配置的本机调试 Chrome。";
      const shouldOpen = window.confirm(
        `${profileModeHint} 是否先在这个调试 Chrome 中打开目标主页？这个动作只打开页面，不读取 Cookie，不上传 Cookie；页面加载并完成登录/验证后，再点击“本机 Chrome 辅助采集”执行扫描。`,
      );
      if (!shouldOpen) {
        profileScanStatus.textContent = status.profile_mode === "dedicated"
          ? "已连接专用调试 Chrome，但没有找到抖音主页标签页。请在该调试 Chrome 中打开目标主页，或在 .env 中切换 existing 模式。"
          : "已连接 Chrome，但没有找到抖音主页标签页。你可以先打开目标主页，再重新点击本机 Chrome 辅助采集。";
        return;
      }
      profileBrowserHelperButton.disabled = true;
      profileScanStatus.textContent = "正在本机调试 Chrome 中打开主页...";
      try {
        await openProfileInLocalChrome(profileValue);
        profileLastChromeProfileValue = profileValue;
        profileScanStatus.textContent = "已打开目标主页。请等待页面加载并完成登录/验证后，再点击“本机 Chrome 辅助采集”开始扫描。";
        window.setTimeout(() => {
          loadChromeHelperStatus({silent: true}).catch(() => {});
        }, 900);
      } catch (error) {
        profileScanStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "无法在调试 Chrome 中打开主页"}`;
      } finally {
        profileBrowserHelperButton.disabled = false;
        resetProfileChromeConfirmation();
      }
      return;
    }
    if (!status.chrome_available && profileChromeLaunchCommand) {
      try {
        await launchLocalChrome(profileValue);
        profileLastChromeProfileValue = profileValue;
        profileScanStatus.textContent = "未检测到 Chrome DevTools，已尝试启动调试 Chrome。请等待页面加载并完成登录/验证后，再点击“本机 Chrome 辅助采集”。";
        window.setTimeout(() => {
          loadChromeHelperStatus({silent: true}).catch(() => {});
        }, 1200);
      } catch (error) {
        try {
          await copyTextToClipboard(profileChromeLaunchCommand);
          profileScanStatus.textContent = "未检测到 Chrome DevTools，自动启动失败，已尝试复制启动命令。请关闭普通 Chrome 后用该命令启动，再打开目标主页。";
        } catch (copyError) {
          profileScanStatus.textContent = "未检测到 Chrome DevTools。请复制状态区里的启动命令，用 remote debugging 模式启动 Chrome。";
        }
      }
      resetProfileChromeConfirmation();
      return;
    }
    profileScanStatus.textContent = status.chrome_available
      ? "已连接 Chrome，但没有找到抖音主页标签页。请先打开目标主页。"
      : "未检测到 Chrome DevTools。请按页面提示用 remote debugging 模式启动 Chrome。";
    resetProfileChromeConfirmation();
    return;
  }
  const confirmed = window.confirm(
    continueScan
      ? "将继续使用本机 Chrome 在当前抖音主页做更多受控滚动，把新出现的作品去重合并进当前素材池。请求由你的本机发起，不读取 Cookie，不上传 Cookie。确认继续？"
      : "将使用本机 Chrome 辅助采集当前已打开的抖音主页，并在该标签页内进行几轮受控滚动以读取更多可见作品。请求由你的本机发起，不读取 Cookie，不上传 Cookie，只返回页面可见作品列表和元数据。确认继续？",
  );
  if (!confirmed) {
    resetProfileChromeConfirmation();
    return;
  }
  profileBrowserHelperButton.disabled = true;
  if (profileContinueChromeButton) {
    profileContinueChromeButton.disabled = true;
  }
  profileScanStatus.textContent = continueScan ? "正在继续采集更多可见作品..." : "正在连接本机 Chrome DevTools...";
  if (!continueScan) {
    profileResultsCard.classList.add("hidden");
  }
  profileFallbackHint.classList.add("hidden");
  try {
    const tokenPayload = await requestChromeScanToken();
    const scanResponse = await fetch("/api/local-helper/chrome/scan-profile", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(localChromeConfirmationPayload({
        profile_url: profileValue,
        token: tokenPayload.token,
        max_items: continueScan ? 200 : 100,
        scroll_rounds: continueScan ? 12 : 6,
        sample_set_id: continueScan ? currentCloneSetId : "",
      })),
    });
    const result = await readJsonResponse(scanResponse);
    profileLastChromeProfileValue = profileValue;
    profileScanStatus.textContent = continueScan
      ? `继续采集完成：当前素材池 ${result.set?.sample_count || 0} 条。`
      : `本机 Chrome 辅助采集完成：${result.set?.sample_count || 0} 条素材。`;
    renderProfileResults(result);
  } catch (error) {
    if (!continueScan && error.error_code === "LOCAL_CHROME_TAB_NOT_FOUND") {
      try {
        profileScanStatus.textContent = "当前调试 Chrome 中没有找到你输入的目标主页，正在打开新主页...";
        await openProfileInLocalChrome(profileValue);
        profileLastChromeProfileValue = profileValue;
        profileScanStatus.textContent = "已在调试 Chrome 中打开你输入的目标主页。请等待页面加载完成并确认账号正确后，再点击“本机 Chrome 辅助采集”。";
        window.setTimeout(() => {
          loadChromeHelperStatus({silent: true}).catch(() => {});
        }, 900);
      } catch (openError) {
        profileScanStatus.textContent = `${openError.error_code || "ERROR"}：${openError.message || "无法在调试 Chrome 中打开目标主页"}`;
      }
      return;
    }
    profileScanStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "本机 Chrome 辅助采集失败"}`;
  } finally {
    profileBrowserHelperButton.disabled = false;
    resetProfileChromeConfirmation();
    updateProfileChromeContinueButton();
    renderCreatorCloneNextAction();
  }
}

async function readHandoffManifestFile(file) {
  if (!file || !profileHandoffManifest) {
    return;
  }
  if (file.size > HANDOFF_MANIFEST_MAX_BYTES) {
    if (profileHandoffFile) {
      profileHandoffFile.value = "";
    }
    profileScanStatus.textContent = "HANDOFF_MANIFEST_INVALID：handoff_manifest.json 文件过大，请确认这是本机助手导出的安全交接包。";
    return;
  }
  try {
    const text = await file.text();
    JSON.parse(text);
    profileHandoffManifest.value = text;
    profileScanStatus.textContent = `已读取 ${file.name || "handoff_manifest.json"}，可点击“导入交接包”。`;
  } catch (error) {
    profileScanStatus.textContent = "HANDOFF_MANIFEST_INVALID：handoff_manifest.json 不是合法 JSON。";
  }
}

async function runCreatorCloneImportStep() {
  const mode = inferCreatorCloneImportMode();
  if (!hasCreatorCloneImportInput()) {
    profileScanStatus.textContent = "请先输入主页 URL、作品链接、aweme_id，或展开“换一种导入方式”导入 JSON / CSV / Case。";
    profileQuickInput?.focus();
    return;
  }
  if (currentCloneSetId || activeCreatorSampleViewItems().length || currentCreatorRuntimeState) {
    resetCreatorClonePoolForNewProfile({clearInput: false});
  }
  syncUnifiedInputToImportFields(mode);
  setActiveImportMode(mode);
  if (mode === "browser") {
    // Main profile imports must go through the server profile pipeline first.
    // When a Douyin Cookie is configured, that path prioritizes Cookie API.
    // Local Chrome remains an explicit fallback button after API/public scan fails.
    await scanProfile("public");
    if (!activeCreatorSampleViewItems().length) {
      setActiveImportMode("manual");
      profileManualLinks?.focus();
      profileScanStatus.textContent = profileScanStatus.textContent || "主页导入未得到素材，已切换到作品链接粘贴方式。";
    }
    return;
  }
  const sourceMode = {manual: "manual", structured: "structured", case: "case", handoff: "handoff"}[mode] || "manual";
  await scanProfile(sourceMode);
}

async function syncCreatorCloneWorkflowSelection() {
  if (!currentCloneSetId) {
    return null;
  }
  const selectedIds = selectedCreatorSampleViewItems().map(sampleViewItemKey).filter(Boolean);
  if (!selectedIds.length) {
    return null;
  }
  return dispatchCreatorIntelligenceWorkflowAction("SELECT_SAMPLES", {selected_sample_ids: selectedIds});
}

async function dispatchCreatorIntelligenceWorkflowAction(action, requestPayload = {}) {
  if (!currentCloneSetId) {
    return null;
  }
  const response = await fetch(`/api/creator-intelligence/projects/${encodeURIComponent(currentCloneSetId)}/workflow`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      action,
      ...requestPayload,
    }),
  });
  const responsePayload = await readJsonResponse(response);
  const profilePayload = profilePayloadFromCreatorIntelligenceProject(responsePayload);
  applyCreatorIntelligencePayload(profilePayload);
  if (profilePayload.set) {
    refreshProfilePoolFromSet(profilePayload.set);
  }
  return responsePayload;
}

function scheduleCreatorCloneSelectionSync() {
  if (!currentCloneSetId) {
    return;
  }
  window.clearTimeout(creatorCloneSelectionSyncTimer);
  creatorCloneSelectionSyncTimer = window.setTimeout(async () => {
    try {
      await syncCreatorCloneWorkflowSelection();
      renderCreatorCloneNextAction();
    } catch {
      // Keep local selection responsive; explicit actions surface sync errors.
    }
  }, 250);
}

async function markCreatorCloneDistillationStarted() {
  if (!currentCloneSetId) {
    return null;
  }
  await dispatchCreatorIntelligenceWorkflowAction("MARK_EVIDENCE_READY");
  return dispatchCreatorIntelligenceWorkflowAction("START_DISTILLATION");
}

async function useRecommendedProfileSamples() {
  const recommended = recommendedProfileSampleMix();
  if (!recommended.length) {
    profileScanStatus.textContent = "当前素材池还没有可推荐样本，请展开“手动调整样本”自行选择。";
    return;
  }
  setProfileSelection(recommended);
  try {
    await syncCreatorCloneWorkflowSelection();
  } catch (error) {
    profileScanStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "样本选择同步失败"}`;
    return;
  }
  setProfileStageView("select", {scroll: true});
  profileScanStatus.textContent = `已使用推荐样本继续：${recommended.length} 条。`;
}

async function handleWizardPrimaryAction() {
  let command = creatorCloneNextButton?.dataset.creatorCloneAction || creatorCloneStateMeta().command || "";
  if (command === "select_recommended_samples" && selectedCreatorSampleViewItems().length) {
    try {
      await syncCreatorCloneWorkflowSelection();
      renderCreatorCloneNextAction();
      command = creatorCloneNextButton?.dataset.creatorCloneAction || creatorCloneStateMeta().command || command;
    } catch (error) {
      profileScanStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "样本选择同步失败"}`;
      return;
    }
  }
  if (command === "import_input") {
    await runCreatorCloneImportStep();
    if (activeCreatorSampleViewItems().length || currentCloneSetId) {
      setProfileStageView("select", {scroll: true});
    } else {
      setProfileStageView("import", {scroll: true});
    }
    return;
  }
  if (command === "show_pool") {
    setProfileStageView("pool", {scroll: true});
    renderCreatorCloneNextAction();
    return;
  }
  if (command === "show_select") {
    setProfileStageView("select", {scroll: true});
    renderCreatorCloneNextAction();
    return;
  }
  if (command === "show_distill") {
    setProfileStageView("distill", {scroll: true});
    renderCreatorCloneNextAction();
    return;
  }
  if (command === "select_recommended_samples") {
    await useRecommendedProfileSamples();
    return;
  }
  if (command === "select_samples") {
    setProfileStageView("select", {scroll: true});
    renderCreatorCloneNextAction();
    return;
  }
  if (command === "build_evidence") {
    setProfileStageView("enrich", {scroll: true});
    await buildSelectedProfileQueue();
    return;
  }
  if (command === "start_distillation") {
    setProfileStageView("distill", {scroll: true});
    await distillSelectedCreatorClone();
    return;
  }
  if (command === "start_batch_distillation") {
    setProfileStageView("distill", {scroll: true});
    await batchDistillSelectedCreatorClone({confirm: true});
    return;
  }
  if (command === "export_report") {
    let reportHref = downloadCreatorCloneMd?.getAttribute("href") || "";
    if ((!reportHref || reportHref === "#") && currentCreatorCloneSetId()) {
      try {
        await hydrateCreatorCloneReportFromSet(currentCreatorCloneSetId(), {scroll: false});
        reportHref = downloadCreatorCloneMd?.getAttribute("href") || "";
      } catch (error) {
        profileScanStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "报告恢复失败，请重新蒸馏或刷新页面。"}`;
      }
    }
    if (reportHref && reportHref !== "#") {
      window.open(reportHref, "_blank", "noopener,noreferrer");
      return;
    }
    creatorCloneResultCard?.scrollIntoView({behavior: "smooth", block: "start"});
    return;
  }
  renderCreatorCloneNextAction();
}

async function runCreatorCloneNextAction() {
  return handleWizardPrimaryAction();
}

function profileSelectionSetsEqual(left, right) {
  if (left.size !== right.size) {
    return false;
  }
  return [...left].every((key) => right.has(key));
}

function setProfileSelection(items) {
  const selectedIds = new Set(items.map(sampleViewItemKey));
  const selectionChanged = !profileSelectionSetsEqual(profileSelectedKeys, selectedIds);
  profileSelectedKeys = selectedIds;
  if (selectionChanged) {
    invalidateCreatorRuntimeReportForSelectionChange();
  }
  document.querySelectorAll("[data-profile-select]").forEach((input) => {
    input.checked = selectedIds.has(input.value) && !input.disabled;
  });
  updateCreatorCloneSelectionStatus();
  scheduleCreatorCloneSelectionSync();
}

function selectedBuildableSampleViewItems() {
  return selectedCreatorSampleViewItems().filter(isSampleViewItemBuildable);
}

function queueItemPayload(item) {
  const awemeId = item.aweme_id || "";
  const fallbackTitle = item.title || item.desc || item.case_id || item.sample_id || item.source_url || "参考样本";
  return {
    aweme_id: awemeId,
    sample_id: item.sample_id || "",
    case_id: item.case_id || "",
    source_url: item.source_url || "",
    webpage_url: item.webpage_url || item.source_url || (awemeId ? `https://www.douyin.com/video/${awemeId}` : ""),
    title: fallbackTitle,
    media_type: item.media_type || "unknown",
  };
}

function mergeProfileQueueItems(items) {
  const queueItems = normalizeItems(items);
  const baseItems = activeCreatorSampleViewItems();
  if (!queueItems.length || !baseItems.length) {
    return;
  }
  runtimeSampleRows = baseItems.map((item) => {
    const itemKeys = new Set([
      item.sample_id,
      item.aweme_id,
      item.case_id,
      item.source_url,
      item.webpage_url,
    ].filter(Boolean).map(String));
    const queueItem = queueItems.find((candidate) => sampleViewItemMatchesKeySet(candidate, itemKeys));
    if (!queueItem) {
      return item;
    }
    const caseId = queueItem.case_id || item.case_id || "";
    const asrStatus = queueItem.asr_status || item.asr_status || "";
    const ocrStatus = queueItem.ocr_status || item.ocr_status || "";
    const enrichmentStatus = queueItem.enrichment_status || item.enrichment_status || "";
    return {
      ...item,
      case_id: caseId,
      local_video_id: queueItem.local_video_id || item.local_video_id || "",
      has_video: Boolean(item.has_video || queueItem.local_video_id || caseId),
      has_frames: Boolean(item.has_frames || caseId),
      has_asr: Boolean(item.has_asr || ["success", "no_speech"].includes(asrStatus)),
      has_ocr: Boolean(item.has_ocr || ["success", "no_text"].includes(ocrStatus)),
      enrichment_status: enrichmentStatus,
      asr_status: asrStatus,
      ocr_status: ocrStatus,
      analysis_status: queueItem.analysis_status || item.analysis_status || "",
      understanding_level: caseId ? "partial" : (item.understanding_level || "metadata_only"),
    };
  });
  syncCreatorProjectSamplesFromViewItems(runtimeSampleRows);
  renderProfileTable();
}

function renderProfileQueue(result) {
  const items = normalizeItems(result.items);
  activeProfileBuildLastResult = result || {};
  revealProfileQueueCard();
  mergeProfileQueueItems(items);
  renderProfileEvidenceQueueProgress(result);
  const completedCount = Number(result.completed_count || 0);
  const failedCount = Number(result.failed_count || 0);
  const referenceOnlyCount = Number(result.reference_only_count || 0);
  const skippedCount = Number(result.skipped_count || 0);
  const otherSkippedCount = Math.max(0, skippedCount - referenceOnlyCount);
  profileQueueSummary.innerHTML = renderProfileQueueSummary({
    completedCount,
    failedCount,
    referenceOnlyCount,
    otherSkippedCount,
    pipelineSummary: result.pipeline_summary || {},
  });
  profileQueueItems.innerHTML = items.length
    ? items
    .map((item) => {
      const caseLink = item.case_id
        ? `<a class="button-link small-link" href="/cases/${escapeHtml(item.case_id)}" target="_blank" rel="noreferrer">打开 Case</a>`
        : "";
      const isReferenceOnly = item.status === "skipped" && item.error_code === "UNSUPPORTED_PROFILE_ITEM";
      const message = isReferenceOnly
        ? item.message || "参考样本已保留，不执行视频下载。"
        : item.error_code
          ? `${item.error_code}：${item.message || ""}`
          : item.message || "";
      const statusLabel = isReferenceOnly ? "参考样本" : item.status || "pending";
      const itemLabel = item.aweme_id || item.case_id || item.sample_id || item.source_url || "参考样本";
      const pipeline = renderProfileQueuePipeline(item);
      return `
        <article class="profile-queue-item ${escapeHtml(item.status || "pending")}">
          <div class="profile-queue-main">
            <strong>${escapeHtml(item.title || itemLabel)}</strong>
            <p><code>${escapeHtml(itemLabel)}</code></p>
          </div>
          <span class="profile-queue-status">${escapeHtml(statusLabel)}</span>
          <p class="profile-queue-message">${escapeHtml(message)}</p>
          ${pipeline}
          ${caseLink}
        </article>
      `;
    })
    .join("")
    : `<p class="muted compact-copy">队列准备中，稍后会显示每条样本的处理状态。</p>`;
}

function renderProfileQueueSummary({completedCount, failedCount, referenceOnlyCount, otherSkippedCount, pipelineSummary}) {
  const notes = normalizeItems(pipelineSummary.notes);
  const actions = normalizeItems(pipelineSummary.next_actions);
  const missingBits = [
    pipelineSummary.asr_provider_missing_count ? `ASR 未配置 ${formatNumber(pipelineSummary.asr_provider_missing_count)} 条` : "",
    pipelineSummary.ocr_provider_missing_count ? `OCR 未配置 ${formatNumber(pipelineSummary.ocr_provider_missing_count)} 条` : "",
  ].filter(Boolean);
  const statusBits = [
    `完成 ${formatNumber(completedCount)} 条`,
    referenceOnlyCount ? `参考 ${formatNumber(referenceOnlyCount)} 条` : "",
    failedCount ? `失败 ${formatNumber(failedCount)} 条` : "",
    otherSkippedCount ? `其他跳过 ${formatNumber(otherSkippedCount)} 条` : "",
  ].filter(Boolean);
  return `
    <p>${escapeHtml(statusBits.join("，") || "队列准备中")}。上方显示总进度，下方显示每条素材的处理状态。</p>
    ${missingBits.length ? `<p class="compact-copy">${missingBits.map(escapeHtml).join("；")}。这是可选富化缺口，不影响已生成素材包继续进入蒸馏。</p>` : ""}
    ${notes.length ? `<p class="compact-copy">${escapeHtml(notes.slice(-1)[0])}</p>` : ""}
    ${
      actions.length
        ? `<p class="compact-copy">${escapeHtml(actions[0])}</p>`
        : ""
    }
  `;
}

function profilePipelineStatusClass(status) {
  const value = String(status || "pending").toLowerCase();
  if (["success", "completed"].includes(value)) {
    return "ready";
  }
  if (["failed", "error"].includes(value)) {
    return "failed";
  }
  if (["provider_missing", "skipped", "not_analyzed"].includes(value)) {
    return "skipped";
  }
  return "pending";
}

function renderProfileQueuePipeline(item) {
  const stages = [
    ["下载", item.local_video_id ? "success" : (["downloading", "building_case", "enriching", "asr_optional", "ocr_optional", "analyzing_optional", "completed"].includes(item.status) ? "success" : "pending")],
    ["素材包", item.case_id ? "success" : (item.status === "building_case" ? "pending" : "")],
    ["富化", item.enrichment_status],
    ["ASR", item.asr_status],
    ["OCR", item.ocr_status],
    ["AI", item.analysis_status],
  ].filter(([, status]) => status !== "");
  if (!stages.length) {
    return "";
  }
  return `
    <div class="profile-queue-pipeline" aria-label="样本处理流水线">
      ${stages
        .map(([label, status]) => `<span class="${profilePipelineStatusClass(status)}">${escapeHtml(label)} · ${escapeHtml(status || "pending")}</span>`)
        .join("")}
    </div>
  `;
}

function refreshProfilePoolFromSet(set) {
  if (!set) {
    return;
  }
  applyCreatorIntelligencePayload({set});
  const selectedIds = new Set(selectedCreatorSampleViewItems().map(sampleViewItemKey));
  currentCloneSetId = set.set_id || currentCloneSetId;
  if (currentCloneSetId) {
    rememberRecentCreatorCloneSetId(currentCloneSetId);
  }
  if (profileContentProfile && set.content_profile) {
    profileContentProfile.value = set.content_profile;
  }
  profileScanPayload = {set};
  runtimeSampleRows = normalizeItems(set.samples);
  syncCreatorProjectSamplesFromViewItems(runtimeSampleRows);
  renderProfileSummary(cloneSummaryFromSet(set) || {});
  renderProfileDecisionBoard({set});
  renderProfileTable();
  setProfileSelection(activeCreatorSampleViewItems().filter((item) => selectedIds.has(sampleViewItemKey(item))));
  updateCreatorCloneSelectionStatus();
  const warnings = normalizeItems(set.warnings);
  profileWarnings.classList.toggle("hidden", !warnings.length);
  profileWarnings.textContent = warnings.join(" ");
}

async function refreshProfilePoolFromPersistedSet(setId) {
  if (!isSafeCreatorCloneSetId(setId)) {
    return false;
  }
  const response = await fetch(`/api/creator-clone/sets/${encodeURIComponent(setId)}`, {cache: "no-store"});
  const payload = await readJsonResponse(response);
  const profilePayload = payload.set ? payload : profilePayloadFromCreatorIntelligenceProject(payload);
  if (!profilePayload?.set) {
    return false;
  }
  refreshProfilePoolFromSet(profilePayload.set);
  return true;
}

async function pollProfileQueue(jobId, options = {}) {
  if (activeHomeRoute !== "profile") {
    return;
  }
  let job = null;
  if (options.safeStatus) {
    job = await fetchWorkbenchJob(jobId);
  } else {
    const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, {cache: "no-store"});
    const payload = await readJsonResponse(response);
    job = payload.job;
  }
  if (activeHomeRoute !== "profile") {
    return;
  }
  if (!job) {
    return;
  }
  if (job.status === "pending" || job.status === "running") {
    setActiveProfileBuildJob(job);
  }
  renderJobStatus(job);
  renderProfileQueue(job.result_json || {});
  if (options.safeStatus && job.status === "stale") {
    clearActiveProfileBuildJob(job.id);
    profileScanStatus.textContent = "证据富化任务可能已停止更新。当前状态保持只读，不会自动轮询、重试或进入大模型蒸馏。";
    jobMessage.className = "job-message";
    jobMessage.textContent = `stale · ${job.progress || 0}% · ${job.message || "任务较长时间没有更新"}`;
    updateCreatorCloneSelectionStatus();
    return;
  }
  if (["pending", "running"].includes(job.status) && isProfileBuildJobStale(job)) {
    clearActiveProfileBuildJob(job.id);
    profileScanStatus.textContent = "任务可能已停止更新。当前状态仍保持原样；请检查队列后，由你决定是否手动重新执行证据富化。";
    jobMessage.className = "job-message";
    jobMessage.textContent = `stale · ${job.progress || 0}% · ${job.message || "任务较长时间没有更新"}`;
    updateCreatorCloneSelectionStatus();
    return;
  }
  if (job.status === "success") {
    clearActiveProfileBuildJob(job.id);
    renderJobStatus(job);
    const persistedSetId = String(
      options.setId
      || job.result_json?.set?.set_id
      || job.result_json?.set_id
      || job.result_json?.recovery_context?.sample_set_id
      || job.resume_target?.resource_id
      || "",
    );
    if (options.safeStatus && persistedSetId) {
      await refreshProfilePoolFromPersistedSet(persistedSetId);
    } else if (job.result_json?.set) {
      refreshProfilePoolFromSet(job.result_json.set);
    }
    if (activeHomeRoute !== "profile") {
      return;
    }
    updateCreatorCloneSelectionStatus();
    if (options.allowAutoDistill !== false && profileAutoDistill?.checked) {
      const selected = selectedCreatorSampleViewItems();
      if (selected.length > CREATOR_CLONE_MAX_DISTILL_SAMPLES) {
        setProfileStageView("distill", {scroll: true});
        profileScanStatus.textContent = "样本富化队列完成，正在继续进行分批大模型蒸馏...";
        await batchDistillSelectedCreatorClone({confirm: false, triggeredByQueue: true});
      } else {
        setProfileStageView("distill", {scroll: true});
        profileScanStatus.textContent = "样本富化队列完成，正在继续进行大模型蒸馏...";
        await distillSelectedCreatorClone({confirmReadiness: false, triggeredByQueue: true});
      }
      return;
    }
    setProfileStageView("distill", {scroll: true});
    profileScanStatus.textContent = "样本富化队列完成。请确认样本仍然勾选，然后点击“大模型蒸馏”或“高级：分批蒸馏”。";
    return;
  }
  if (job.status === "failed") {
    clearActiveProfileBuildJob(job.id);
    jobMessage.className = "job-message failed";
    jobMessage.textContent = `${job.error_code || "ERROR"}：${job.message || "任务失败"}`;
    updateCreatorCloneSelectionStatus();
    return;
  }
  await new Promise((resolve) => {
    window.setTimeout(resolve, 900);
  });
  return pollProfileQueue(jobId, options);
}

// Creator Clone: enrichment queue
async function buildSelectedProfileQueue() {
  if (creatorCloneEnrichmentRunning) {
    return;
  }
  const selected = selectedCreatorSampleViewItems();
  if (!selected.length) {
    profileScanStatus.textContent = `请先选择代表样本。视频样本会下载富化，图文/元数据样本会保存为蒸馏参考。`;
    return;
  }
  setProfileStageView("enrich", {scroll: true});
  const buildableCount = selected.filter(isSampleViewItemBuildable).length;
  const referenceOnlyCount = selected.length - buildableCount;
  if (buildableCount > PROFILE_BUILD_MAX_ITEMS) {
    profileScanStatus.textContent = `当前自用版最多一次富化 ${PROFILE_BUILD_MAX_ITEMS} 条可下载视频，避免误批量下载。`;
    return;
  }
  setCreatorCloneEnrichmentLocked(true);
  renderCreatorCloneNextAction();
  try {
    await syncCreatorCloneWorkflowSelection();
    if (!placeJobCard("profile")) {
      return;
    }
    resetJobCard(buildableCount
      ? `创建素材富化队列：视频 ${buildableCount} 条，参考样本 ${referenceOnlyCount} 条。`
      : `保存选样：${referenceOnlyCount} 条仅作为蒸馏参考，不执行视频下载。`);
    revealProfileQueueCard();
    profileQueueSummary.innerHTML = renderProfileQueueSummary({
      completedCount: 0,
      failedCount: 0,
      referenceOnlyCount,
      otherSkippedCount: 0,
      pipelineSummary: {
        selected_count: selected.length,
        downloadable_count: buildableCount,
        reference_only_count: referenceOnlyCount,
        notes: [`已创建本地计划队列 ${selected.length} 条，等待后端逐条回写处理状态。`],
      },
    });
    renderProfileQueue({items: selected.map((item) => ({
      ...queueItemPayload(item),
      status: "pending",
      message: isSampleViewItemBuildable(item) ? "等待下载和素材包生成" : "参考样本等待保留",
      enrichment_status: isSampleViewItemBuildable(item) ? "pending" : "skipped",
      asr_status: isSampleViewItemBuildable(item) ? "pending" : "skipped",
      ocr_status: isSampleViewItemBuildable(item) ? "pending" : "skipped",
      analysis_status: "skipped",
    })), pipeline_summary: {
      selected_count: selected.length,
      downloadable_count: buildableCount,
      reference_only_count: referenceOnlyCount,
      notes: [`已创建本地计划队列 ${selected.length} 条，等待后端逐条回写处理状态。`],
    }});
    profileQueueCard.scrollIntoView({behavior: "smooth", block: "start"});
    rememberRecentProfileBuildState({
      setId: currentCloneSetId,
      selectedSampleIds: selectedCreatorSampleViewItems().map(sampleViewItemKey),
    });
    const response = await fetch("/api/jobs/profile-build-cases", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        items: selected.map(queueItemPayload),
        selected_sample_ids: selectedCreatorSampleViewItems().map(sampleViewItemKey),
        auto_enrich: true,
        auto_asr: true,
        auto_ocr: true,
        auto_analyze: false,
        quality_preference: qualityPreference?.value || "1080",
        sample_set_id: currentCloneSetId,
      }),
    });
    const payload = await readJsonResponse(response);
    setActiveProfileBuildJob({id: payload.job_id, status: "running", updated_at: new Date().toISOString()});
    rememberRecentProfileBuildState({
      setId: currentCloneSetId,
      jobId: payload.job_id,
      selectedSampleIds: selectedCreatorSampleViewItems().map(sampleViewItemKey),
    });
    profileScanStatus.textContent = buildableCount
      ? `已创建样本富化队列：${payload.selected_count} 条；可下载视频会生成素材包，图文/元数据样本会作为蒸馏参考。`
      : `已保存 ${payload.selected_count} 条参考样本；这些样本不下载视频，可直接进入大模型蒸馏。`;
    await pollProfileQueue(payload.job_id);
  } catch (error) {
    if (activeHomeRoute !== "profile") {
      return;
    }
    clearActiveProfileBuildJob();
    jobMessage.className = "job-message failed";
    jobMessage.textContent = `${error.error_code || "ERROR"}：${error.message || "队列创建失败"}`;
    profileScanStatus.textContent = jobMessage.textContent;
    updateCreatorCloneSelectionStatus();
  } finally {
    setCreatorCloneEnrichmentLocked(false);
    updateCreatorCloneSelectionStatus();
    renderCreatorCloneNextAction();
  }
}

function topCreatorSampleViewItemsBy(key, count = 3) {
  return sortCreatorSampleViewItems(activeCreatorSampleViewItems(), key).slice(0, count);
}

function lowPerformanceCreatorSampleViewItems(count = 3) {
  return [...activeCreatorSampleViewItems()]
    .sort((left, right) => Number(left.engagement_score || 0) - Number(right.engagement_score || 0))
    .slice(0, count);
}

function needsEnrichmentCreatorSampleViewItems(count = 5) {
  return sortCreatorSampleViewItems(activeCreatorSampleViewItems().filter((item) => isSampleViewItemBuildable(item) && !item.has_frames), "engagement_score").slice(0, count);
}

function profileEvidenceScore(item) {
  return [
    item.has_video,
    item.has_frames,
    item.has_asr,
    item.has_ocr,
    item.has_comments,
  ].filter(Boolean).length;
}

function readyEvidenceCreatorSampleViewItems(count = 5) {
  return [...activeCreatorSampleViewItems()]
    .filter((item) => profileEvidenceScore(item) >= 2)
    .sort((left, right) => {
      const scoreDiff = profileEvidenceScore(right) - profileEvidenceScore(left);
      return scoreDiff || Number(right.engagement_score || 0) - Number(left.engagement_score || 0);
    })
    .slice(0, count);
}

function profileDistillReadiness(items) {
  const selected = normalizeItems(items);
  const counts = selected.reduce(
    (acc, item) => {
      acc.metadataOnly += !item.understanding_level || item.understanding_level === "metadata_only" ? 1 : 0;
      acc.video += item.media_type === "video" ? 1 : 0;
      acc.image += item.media_type === "image" ? 1 : 0;
      acc.unknown += item.media_type === "unknown" ? 1 : 0;
      acc.buildable += isSampleViewItemBuildable(item) ? 1 : 0;
      acc.frames += item.has_frames ? 1 : 0;
      acc.asr += item.has_asr ? 1 : 0;
      acc.ocr += item.has_ocr ? 1 : 0;
      acc.comments += item.has_comments ? 1 : 0;
      acc.score += profileEvidenceScore(item);
      const mediaType = item.media_type || "unknown";
      acc.mediaTypes[mediaType] = (acc.mediaTypes[mediaType] || 0) + 1;
      return acc;
    },
    {metadataOnly: 0, video: 0, image: 0, unknown: 0, buildable: 0, frames: 0, asr: 0, ocr: 0, comments: 0, score: 0, mediaTypes: {}},
  );
  const averageScore = selected.length ? counts.score / selected.length : 0;
  const warnings = [];
  const mediaTypeKeys = Object.keys(counts.mediaTypes).filter((key) => counts.mediaTypes[key] > 0);
  if (mediaTypeKeys.length > 1) {
    warnings.push(`混合格式样本：视频 ${counts.mediaTypes.video || 0}，图文 ${counts.mediaTypes.image || 0}，未知 ${counts.mediaTypes.unknown || 0}`);
  } else if (counts.mediaTypes.image || counts.mediaTypes.unknown) {
    warnings.push(`非视频样本 ${selected.length}/${selected.length}：只能作为封面、标题或元数据参考`);
  }
  if (counts.metadataOnly >= Math.ceil(selected.length / 2)) {
    warnings.push(`仅元数据样本 ${counts.metadataOnly}/${selected.length}`);
  }
  if (counts.frames < Math.ceil(selected.length / 2)) {
    warnings.push(`有关键帧样本 ${counts.frames}/${selected.length}`);
  }
  if (averageScore < 2) {
    warnings.push(`平均证据分 ${averageScore.toFixed(1)}/5`);
  }
  const recommendations = [];
  if (!selected.length) {
    recommendations.push("先从素材池选择代表样本。");
  } else if (warnings.length) {
    recommendations.push("建议先点击主按钮开始富化证据，补齐视频、关键帧、OCR、ASR 后再蒸馏。");
  } else {
    recommendations.push("证据足够，可以直接开始大模型蒸馏。");
  }
  if (counts.image || counts.unknown) {
    recommendations.push("混合图文/未知样本时，蒸馏结论会更多依赖封面、标题、指标和元数据。");
  }
  if (counts.comments === 0) {
    recommendations.push("后续可导入评论，用于判断争议点、需求和互动动机。");
  }
  return {ready: !warnings.length, warnings, averageScore, counts, recommendations};
}

function renderProfileDistillReadiness(items) {
  if (!profileDistillReadinessStatus) {
    return;
  }
  const selected = normalizeItems(items);
  if (!selected.length) {
    profileDistillReadinessStatus.classList.remove("ready", "warning");
    profileDistillReadinessStatus.innerHTML = `
      <div class="distill-readiness-head">
        <strong>蒸馏准备度</strong>
        <p>先选择代表样本。系统会根据样本数量、格式结构、关键帧和证据完整度提示是否适合蒸馏。</p>
      </div>
    `;
    return;
  }
  const readiness = profileDistillReadiness(selected);
  profileDistillReadinessStatus.classList.toggle("ready", readiness.ready);
  profileDistillReadinessStatus.classList.toggle("warning", !readiness.ready);
  const counts = readiness.counts || {};
  const metrics = [
    ["已选样本", selected.length],
    ["可富化视频", counts.buildable],
    ["关键帧", counts.frames],
    ["ASR", counts.asr],
    ["OCR", counts.ocr],
    ["评论", counts.comments],
  ];
  profileDistillReadinessStatus.innerHTML = `
    <div class="distill-readiness-head">
      <strong>${readiness.ready ? "蒸馏准备度：可开始" : "蒸馏准备度：建议先富化"}</strong>
      <p>平均证据分 ${readiness.averageScore.toFixed(1)}/5；视频 ${formatNumber(counts.video)}，图文 ${formatNumber(counts.image)}，未知 ${formatNumber(counts.unknown)}，仅元数据 ${formatNumber(counts.metadataOnly)}。</p>
    </div>
    <div class="distill-readiness-matrix" aria-label="蒸馏证据矩阵">
      ${metrics.map(([label, value]) => `<span><strong>${formatNumber(value || 0)}</strong>${escapeHtml(label)}</span>`).join("")}
    </div>
    ${
      readiness.warnings.length
        ? `<ul class="distill-readiness-warnings">${readiness.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>`
        : ""
    }
    <ul class="distill-readiness-actions">
      ${readiness.recommendations.map((action) => `<li>${escapeHtml(action)}</li>`).join("")}
    </ul>
  `;
}

function confirmProfileDistillReadiness(selected) {
  const readiness = profileDistillReadiness(selected);
  if (readiness.ready) {
    return true;
  }
  const warningText = readiness.warnings.length
    ? readiness.warnings.join("；")
    : "部分样本缺少视频、关键帧、OCR 或 ASR 证据";
  const message = `当前选样证据不足：${warningText}。将继续生成临时蒸馏结果；建议后续补齐证据后再重跑。`;
  if (profileScanStatus) {
    profileScanStatus.textContent = message;
  }
  if (jobMessage) {
    jobMessage.className = "job-message warning";
    jobMessage.textContent = message;
  }
  return true;
}

function recommendedProfileSampleMix() {
  if (!representativeSampleSelectorUi || !currentRepresentativeSampleSelection) {
    return [];
  }
  return representativeSampleSelectorUi.matchingItems(
    currentRepresentativeSampleSelection,
    activeCreatorSampleViewItems(),
    sampleViewItemKey,
  );
}

function profilePresetItems(preset) {
  if (preset === "recommended_mix") {
    return recommendedProfileSampleMix();
  }
  const match = String(preset || "").match(/^(top_likes|top_comments|top_shares|top_collects|latest|low_performance|needs_enrichment|ready_evidence)_(\d+)$/);
  if (match) {
    const [, type, countText] = match;
    const count = Math.max(1, Number(countText || 3));
    if (type === "top_likes") return topCreatorSampleViewItemsBy("like_count", count);
    if (type === "top_comments") return topCreatorSampleViewItemsBy("comment_count", count);
    if (type === "top_shares") return topCreatorSampleViewItemsBy("share_count", count);
    if (type === "top_collects") return topCreatorSampleViewItemsBy("collect_count", count);
    if (type === "latest") return topCreatorSampleViewItemsBy("create_time", count);
    if (type === "low_performance") return lowPerformanceCreatorSampleViewItems(count);
    if (type === "needs_enrichment") return needsEnrichmentCreatorSampleViewItems(count);
    if (type === "ready_evidence") return readyEvidenceCreatorSampleViewItems(count);
  }
  return [];
}

function profilePresetLabel(preset) {
  const match = String(preset || "").match(/^(top_likes|top_comments|top_shares|top_collects|latest|low_performance|needs_enrichment|ready_evidence)_(\d+)$/);
  if (match) {
    const [, type, count] = match;
    const labels = {
      top_likes: `高赞 Top ${count}`,
      top_comments: `高评 Top ${count}`,
      top_shares: `高分享 Top ${count}`,
      top_collects: `高收藏 Top ${count}`,
      latest: `最新 Top ${count}`,
      low_performance: `低表现 ${count} 条`,
      needs_enrichment: `待富化 Top ${count}`,
      ready_evidence: `证据完整 Top ${count}`,
    };
    return labels[type] || "分层样本";
  }
  return {
    recommended_mix: "推荐组合",
  }[preset] || "分层样本";
}

function applyProfilePresetSelection(preset) {
  if (!activeCreatorSampleViewItems().length) {
    profileScanStatus.textContent = "请先扫描或导入账号素材清单。";
    return;
  }
  const items = profilePresetItems(preset);
  if (preset === "recommended_mix" && !items.length) {
    profileScanStatus.textContent = "代表样本推荐尚未生成，请稍候或点击“重新计算”。";
    return;
  }
  setProfileSelection(items);
  profileScanStatus.textContent = `已选择${profilePresetLabel(preset)}：${items.length} 条。可继续手动勾选补充代表样本。`;
}

function creatorCloneSamplePayload(item) {
  return {
    sample_id: sampleViewItemKey(item),
    source_type: item.source_type || "douyin",
    source_url: item.source_url || item.webpage_url || "",
    aweme_id: item.aweme_id || "",
    title: item.title || item.desc || "",
    desc: item.desc || "",
    author: item.author || "",
    cover_url: item.cover_url || "",
    media_type: item.media_type || "unknown",
    duration: Number(item.duration || 0),
    content_category: item.content_category || "",
    like_count: Number(item.like_count || 0),
    comment_count: Number(item.comment_count || 0),
    share_count: Number(item.share_count || 0),
    collect_count: Number(item.collect_count || 0),
    view_count: Number(item.view_count || 0),
    create_time: item.create_time || "",
    case_id: item.case_id || "",
    understanding_level: item.understanding_level || "metadata_only",
    has_video: Boolean(item.has_video),
    has_frames: Boolean(item.has_frames),
    has_asr: Boolean(item.has_asr),
    has_ocr: Boolean(item.has_ocr),
    has_comments: Boolean(item.has_comments),
    enrichment_status: item.enrichment_status || "pending",
    asr_status: item.asr_status || "pending",
    ocr_status: item.ocr_status || "pending",
    analysis_status: item.analysis_status || "not_analyzed",
    tags: item.tags || [],
    notes: item.notes || "",
  };
}

function renderProfileSegments(segments) {
  return `
    <h5>高赞样本</h5>${renderSegmentSampleList(segments.highest_like_samples, "like_count", "赞")}
    <h5>高评论样本</h5>${renderSegmentSampleList(segments.highest_comment_samples, "comment_count", "评")}
    <h5>高分享样本</h5>${renderSegmentSampleList(segments.highest_share_samples, "share_count", "分享")}
    <h5>高收藏样本</h5>${renderSegmentSampleList(segments.highest_collect_samples, "collect_count", "收藏")}
    <h5>弱样本 / 对照样本</h5>${renderSegmentSampleList(segments.weak_or_reference_samples, "engagement_score", "综合")}
  `;
}

function segmentListCount(value) {
  return normalizeItems(value).length;
}

function renderCompactPerformanceSegments(segments = {}) {
  const chips = [
    ["高赞", segments.highest_like_samples],
    ["高评", segments.highest_comment_samples],
    ["高分享", segments.highest_share_samples],
    ["高收藏", segments.highest_collect_samples],
    ["对照", segments.weak_or_reference_samples],
  ].map(([label, rows]) => `<span class="segment-summary-chip">${escapeHtml(label)} ${formatNumber(segmentListCount(rows))}</span>`);
  return `
    <details class="creator-clone-segment-disclosure">
      <summary>
        <span>样本分层摘要</span>
        ${chips.join("")}
      </summary>
      <div class="profile-segment-body">
        ${renderProfileSegments(segments)}
      </div>
    </details>
  `;
}

function renderTopicBuckets(buckets) {
  const rows = normalizeItems(buckets).map((item) => {
    if (!item || typeof item !== "object") {
      return item;
    }
    const name = item.name || item.title || "";
    const parts = [
      item.description,
      item.why_it_works ? `为什么有效：${item.why_it_works}` : "",
      item.evidence ? `证据：${formatReportValue(item.evidence)}` : "",
    ].filter(isMeaningfulReportText);
    return [name, parts.join("；")].filter(isMeaningfulReportText).join("：");
  }).filter(isMeaningfulReportText);
  return renderPublicList(rows, "暂无稳定选题方向。");
}

function renderFormulaCards(formulas) {
  const rows = normalizeItems(formulas).map((item) => {
    if (!item || typeof item !== "object") {
      return item;
    }
    const name = item.name || item.title || item.formula || "";
    const parts = [
      item.when_to_use ? `适用：${item.when_to_use}` : "",
      publicValueHasContent(item.input_material_needed) ? `素材：${formatReportValue(item.input_material_needed)}` : "",
      publicValueHasContent(item.beat_structure || item.beats || item.structure) ? `结构：${formatReportValue(item.beat_structure || item.beats || item.structure)}` : "",
      item.expected_metric_strength ? `强项：${item.expected_metric_strength}` : "",
      publicValueHasContent(item.risks) ? `风险：${formatReportValue(item.risks)}` : "",
    ].filter(isMeaningfulReportText);
    return [name, parts.join("；")].filter(isMeaningfulReportText).join("：");
  }).filter(isMeaningfulReportText);
  return renderPublicList(rows, "本次没有返回独立公式，建议先从高互动样本中人工提炼 2-3 个可复用拍法。");
}

function renderCandidateIdeas(ideas) {
  const rows = normalizeItems(ideas).map((item) => {
    if (!item || typeof item !== "object") {
      return item;
    }
    const title = item.title || item.idea || item.name || "";
    const parts = [
      item.formula_used ? `使用公式：${item.formula_used}` : "",
      item.why_worth_trying || item.reason ? `理由：${item.why_worth_trying || item.reason}` : "",
      item.likely_strength ? `强度：${item.likely_strength}` : "",
      publicValueHasContent(item.production_requirements) ? `制作要求：${formatReportValue(item.production_requirements)}` : "",
    ].filter(isMeaningfulReportText);
    return [title, parts.join("；")].filter(isMeaningfulReportText).join("：");
  }).filter(isMeaningfulReportText);
  return renderPublicList(rows, "本次没有返回独立选题库，可先基于爆款共性手动生成候选选题。");
}

function compactReportList(...values) {
  const rows = [];
  values.forEach((value) => {
    normalizeItems(value).forEach((item) => {
      const text = cleanPublicReportText(reportItemPrimaryText(item));
      if (isMeaningfulReportText(text) && !rows.includes(text)) {
        rows.push(text);
      }
    });
  });
  return rows;
}

function isTechnicalReportNote(value) {
  return /(LLM|Reduce|Prompt|批次|本地汇总|大模型暂不可用|大模型未配置|重试|超时|失败|fallback|prompt_only)/i.test(String(value || ""));
}

function trimReportClause(value) {
  return String(value || "").replace(/\s+/g, " ").trim().replace(/[。；;,，、\s]+$/g, "");
}

function truncateReportText(value, limit = 120) {
  const text = trimReportClause(value);
  return text.length > limit ? `${text.slice(0, limit - 1).trim()}…` : text;
}

function compactPublicReportText(value, limit = 240) {
  const chunks = [];
  normalizeItems(value).forEach((item) => {
    const text = reportItemPrimaryText(item).replace(/\s+/g, " ").trim();
    text.split(/[。；;!！?？]\s*/).forEach((part) => {
      const clean = trimReportClause(part);
      if (!isMeaningfulReportText(clean) || isTechnicalReportNote(clean) || chunks.includes(clean)) {
        return;
      }
      chunks.push(truncateReportText(clean, 96));
    });
  });
  const summary = chunks.slice(0, 3).join("；");
  return summary.length > limit ? `${summary.slice(0, limit - 1).trim()}…` : summary;
}

function compactReportHeadline(value, limit = 120) {
  for (const item of normalizeItems(value)) {
    const text = reportItemPrimaryText(item).replace(/\s+/g, " ").trim();
    for (const part of text.split(/[。；;!！?？]\s*/)) {
      const clean = trimReportClause(part);
      if (isMeaningfulReportText(clean) && !isTechnicalReportNote(clean)) {
        return truncateReportText(clean, limit);
      }
    }
  }
  return "";
}

function nonTechnicalReportList(...values) {
  return compactReportList(...values).filter((item) => !isTechnicalReportNote(item));
}

function technicalReportNotes(...values) {
  return compactReportList(...values).filter(isTechnicalReportNote).slice(0, 6);
}

function reportViewEvidenceCountsFromOverview(overview = {}) {
  const counts = overview.understanding_counts || {};
  return {
    selected_count: Number(overview.selected_count || 0),
    sample_count: Number(overview.sample_count || 0),
    understanding_full: Number(counts.full || 0),
    understanding_partial: Number(counts.partial || 0),
    understanding_metadata_only: Number(counts.metadata_only || 0),
  };
}

function creatorReportViewModelFromResult(result = {}, overview = {}, templateLabel = "") {
  if (result.creator_report_view_model && typeof result.creator_report_view_model === "object") {
    const viewModel = {...result.creator_report_view_model};
    viewModel.headline = compactReportHeadline(viewModel.headline || result.summary, 120) || truncateReportText(viewModel.headline || "", 120);
    viewModel.summary = compactPublicReportText(viewModel.summary || result.summary) || truncateReportText(viewModel.summary || result.summary || "", 240);
    viewModel.technical_notes = normalizeItems(viewModel.technical_notes).filter(isMeaningfulReportText).slice(0, 6);
    viewModel.value_upgrade = viewModel.value_upgrade && typeof viewModel.value_upgrade === "object" ? {...viewModel.value_upgrade} : {};
    viewModel.value_upgrade.quality = viewModel.value_upgrade.quality || result.report_quality || {};
    viewModel.value_upgrade.diagnostics = viewModel.value_upgrade.diagnostics || creatorReportDiagnosticsFromResult(result, overview);
    return viewModel;
  }
  const strategy = creatorStrategyFromResult(result) || {};
  const positioning = result.creator_positioning || {};
  const patterns = result.expression_patterns || {};
  const thinking = result.thinking_patterns || {};
  const spec = result.creator_clone_spec || {};
  const segments = result.performance_segments || {};
  const headline = compactReportHeadline(strategy.positioning || positioning.what_the_creator_sells || positioning.audience_promise || "账号规律已完成蒸馏", 120);
  const fallbackSummary = compactPublicReportText([
    strategy.positioning,
    positioning.what_the_creator_sells,
    positioning.audience_promise,
    result.summary,
  ]);
  const formulas = nonTechnicalReportList(strategy.templates, result.transferable_formulas).slice(0, 5);
  const ideas = nonTechnicalReportList(strategy.idea_bank, result.candidate_ideas, result.topic_buckets).slice(0, 6);
  return {
    headline,
    summary: fallbackSummary || "请先查看下方核心结论、流量来源和可复刻公式。",
    template_label: templateLabel || result.content_profile?.effective_label || "自动识别",
    confidence_label: overview.confidence || "",
    confidence_note: overview.confidence ? `系统置信度：${overview.confidence}` : "",
    evidence_counts: reportViewEvidenceCountsFromOverview(overview),
    sections: {
      core_judgment: {
        fields: [
          {label: "定位", value: headline},
          {label: "观众承诺", value: positioning.audience_promise},
          {label: "隐藏类型", value: positioning.hidden_genre},
          {label: "观众假设", value: positioning.audience_assumption},
        ],
        bullets: nonTechnicalReportList(positioning.audience_promise, positioning.hidden_genre, positioning.audience_assumption, result.summary).slice(0, 5),
      },
      traffic_sources: {
        metric_signals: compactReportList(
          firstSegmentBrief(segments, "highest_like_samples", "高赞"),
          firstSegmentBrief(segments, "highest_comment_samples", "高评"),
          firstSegmentBrief(segments, "highest_share_samples", "高分享"),
          firstSegmentBrief(segments, "highest_collect_samples", "高收藏"),
        ).slice(0, 4),
        hooks: nonTechnicalReportList(strategy.hooks, patterns.opening_hooks, thinking.tension_sources, positioning.audience_promise).slice(0, 6),
      },
      formulas: formulas.length ? formulas : nonTechnicalReportList(strategy.content_strategy, spec.structure_rules, spec.visual_rules, patterns.opening_hooks).slice(0, 5),
      repeatable_patterns: nonTechnicalReportList(result.topic_buckets, patterns.visual_style, patterns.scene_order, patterns.subtitle_voice, spec.expression_rules, spec.visual_rules, spec.structure_rules).slice(0, 6),
      next_ideas: ideas,
      next_actions: nonTechnicalReportList(result.next_actions, result.topic_buckets).slice(0, 5),
      checklist: nonTechnicalReportList(strategy.validation_rules, spec.self_check_rubric).slice(0, 6),
      anti_patterns: nonTechnicalReportList(strategy.anti_patterns, spec.anti_patterns).slice(0, 6),
    },
    technical_notes: technicalReportNotes(overview.warnings, result.next_actions, result.evidence_gaps),
    value_upgrade: {
      quality: result.report_quality || {},
      diagnostics: creatorReportDiagnosticsFromResult(result, overview),
    },
  };
}

function firstSegmentBrief(segments, key, metricLabel) {
  const item = normalizeItems(segments?.[key])[0];
  if (!item || typeof item !== "object") {
    return "";
  }
  const title = item.title || item.desc || item.source_url || "代表样本";
  const metricValue = item.metric_value ?? item.like_count ?? item.comment_count ?? item.share_count ?? item.collect_count;
  return metricValue !== undefined && metricValue !== null && metricValue !== ""
    ? `${metricLabel}代表：${title}（${formatNumber(metricValue)}）`
    : `${metricLabel}代表：${title}`;
}

function creatorCloneMarkdownList(value, fallback = "暂无") {
  const items = normalizeItems(value)
    .map(formatReportValue)
    .map(cleanPublicReportText)
    .filter(isMeaningfulReportText);
  return items.length ? items.map((item) => `- ${item}`).join("\n") : `- ${fallback}`;
}

function creatorCloneMarkdownReport(result, overview, templateLabel) {
  const viewModel = creatorReportViewModelFromResult(result, overview, templateLabel);
  const sections = viewModel.sections || {};
  const strategy = creatorStrategyFromResult(result) || {};
  const positioning = result.creator_positioning || {};
  return [
    "# 创作者蒸馏报告",
    "",
    "## 0. 核心摘要",
    "",
    viewModel.summary || result.summary || "创作者蒸馏完成。",
    "",
    "## 1. 核心判断",
    "",
    `- 定位：${viewModel.headline || strategy.positioning || positioning.what_the_creator_sells || "待补充"}`,
    `- 观众承诺：${positioning.audience_promise || "待补充"}`,
    `- 隐藏类型：${positioning.hidden_genre || "待补充"}`,
    `- 观众假设：${positioning.audience_assumption || "待补充"}`,
    "",
    "## 2. 流量来源与内容策略",
    "",
    creatorCloneMarkdownList(sections.traffic_sources?.hooks || strategy.content_strategy),
    "",
    "## 3. 可复刻创作公式",
    "",
    creatorCloneMarkdownList(sections.formulas || strategy.templates, "本次没有返回独立公式。"),
    "",
    "## 4. 下一批可以怎么拍",
    "",
    creatorCloneMarkdownList(sections.next_ideas || strategy.idea_bank, "本次没有返回独立选题库。"),
    "",
    "## 5. 发布前自检",
    "",
    creatorCloneMarkdownList(sections.checklist || strategy.validation_rules, "暂无自检规则。"),
    "",
    "## 6. 不要照搬 / 风险边界",
    "",
    creatorCloneMarkdownList(sections.anti_patterns || strategy.anti_patterns, "暂无风险边界。"),
  ].join("\n");
}

function renderCreatorCloneEvidenceOverview(overview) {
  const counts = overview.understanding_counts || {};
  const warnings = normalizeItems(overview.warnings);
  return `
    <section class="creator-clone-evidence-strip" aria-label="创作者蒸馏证据完整度">
      <article>
        <span>选中样本</span>
        <strong>${formatNumber(overview.selected_count || 0)} / ${formatNumber(overview.sample_count || 0)}</strong>
      </article>
      <article>
        <span>完整证据</span>
        <strong>${formatNumber(counts.full || 0)}</strong>
      </article>
      <article>
        <span>部分证据</span>
        <strong>${formatNumber(counts.partial || 0)}</strong>
      </article>
      <article>
        <span>仅元数据</span>
        <strong>${formatNumber(counts.metadata_only || 0)}</strong>
      </article>
      <article class="wide">
        <span>可信度提示</span>
        <strong>${escapeHtml(overview.confidence || "unknown")}</strong>
        ${warnings.length ? `<p>${escapeHtml(warnings.join("；"))}</p>` : "<p>没有额外警告。</p>"}
      </article>
    </section>
  `;
}

function firstCloneValue(value, fallback = "待补充") {
  const values = normalizeItems(value);
  if (values.length) {
    return formatReportValue(values[0]) || fallback;
  }
  if (value && typeof value === "object") {
    return formatReportValue(value) || fallback;
  }
  return String(value || fallback);
}

function renderCreatorCloneActionSummary(result) {
  const strategy = creatorStrategyFromResult(result) || {};
  const positioning = result.creator_positioning || {};
  const formulas = normalizeItems(result.transferable_formulas);
  const ideas = normalizeItems(result.candidate_ideas);
  const templateValue = firstCloneValue(
    normalizeItems(strategy.templates).map((item) => item?.name || item?.title || item?.template || item),
    "",
  );
  const ideaValue = firstCloneValue(
    normalizeItems(strategy.idea_bank).map((item) => item?.title || item?.idea || item),
    firstCloneValue(ideas.map((item) => item?.title || item), ""),
  );
  const summaryCards = [
    ["核心定位", strategy.positioning || positioning.what_the_creator_sells || result.summary || "待补充"],
    ["内容策略", firstCloneValue(strategy.content_strategy || formulas.map((item) => item?.name || item), "待补充")],
    ["开头钩子", firstCloneValue(strategy.hooks || result.expression_patterns?.opening_hooks, "")],
    ["可复用模板", templateValue],
    ["优先选题", ideaValue],
  ].filter(([, value]) => publicValueHasContent(value));
  return `
    <section class="creator-clone-action-summary" aria-label="创作者蒸馏可执行摘要">
      <div class="section-heading-row compact-row">
        <div>
          <div class="entry-label">Action Summary</div>
          <h3>可执行摘要</h3>
        </div>
        <span class="status-badge muted-badge">用于选题 / 脚本 / 自检</span>
      </div>
      <div class="creator-clone-action-grid">
        ${summaryCards
          .map(([label, value]) => `
            <article>
              <span>${escapeHtml(label)}</span>
              <strong>${escapeHtml(value)}</strong>
            </article>
          `)
          .join("")}
      </div>
    </section>
  `;
}

function renderCreatorStrategyOutput(strategy = {}) {
  if (!strategy || typeof strategy !== "object") {
    return "";
  }
  const hasStrategy = [
    strategy.positioning,
    ...normalizeItems(strategy.content_strategy),
    ...normalizeItems(strategy.hooks),
    ...normalizeItems(strategy.templates),
    ...normalizeItems(strategy.anti_patterns),
    ...normalizeItems(strategy.idea_bank),
    ...normalizeItems(strategy.validation_rules),
  ].some((item) => item !== undefined && item !== null && item !== "");
  if (!hasStrategy) {
    return "";
  }
  const cards = [
    publicValueHasContent(strategy.positioning)
      ? renderPublicCard("策略定位", renderPublicFields([["Positioning", strategy.positioning]]), "featured")
      : "",
    publicValueHasContent(strategy.content_strategy)
      ? renderPublicCard("内容策略", renderPublicList(strategy.content_strategy), "featured")
      : "",
    publicValueHasContent(strategy.hooks)
      ? renderPublicCard("开头钩子", renderPublicList(strategy.hooks))
      : "",
    publicValueHasContent(strategy.templates)
      ? renderPublicCard("可复用模板", renderFormulaCards(strategy.templates), "featured")
      : "",
    publicValueHasContent(strategy.idea_bank)
      ? renderPublicCard("选题库", renderCandidateIdeas(strategy.idea_bank), "featured")
      : "",
  ].filter(Boolean).join("");
  if (!cards) {
    return "";
  }
  return `
    <div class="public-report-grid creator-strategy-grid" aria-label="Creator Intelligence Strategy Output">
      ${cards}
    </div>
  `;
}

function creatorCloneOverviewFromSet(set) {
  const samples = normalizeItems(set?.samples);
  const selectedIds = new Set(normalizeItems(set?.selected_sample_ids));
  const selected = selectedIds.size
    ? samples.filter((sample) => selectedIds.has(sample.sample_id) || selectedIds.has(sample.aweme_id) || selectedIds.has(sample.case_id))
    : samples.filter((sample) => sample.selected);
  const scopedSamples = selected.length ? selected : samples;
  const counts = scopedSamples.reduce(
    (acc, sample) => {
      const level = sample.understanding_level || "metadata_only";
      acc[level] = (acc[level] || 0) + 1;
      return acc;
    },
    {full: 0, partial: 0, metadata_only: 0},
  );
  const selectedCount = selected.length || Number(set?.selected_count || 0);
  const confidence = counts.full >= Math.max(1, Math.floor(scopedSamples.length / 2))
    ? "medium_high"
    : counts.full + counts.partial >= Math.max(1, Math.floor(scopedSamples.length / 2))
      ? "medium"
      : "low_metadata_only";
  return {
    sample_count: Number(set?.sample_count || samples.length || 0),
    selected_count: selectedCount,
    understanding_counts: counts,
    confidence,
    warnings: normalizeItems(set?.warnings),
  };
}

// Creator Clone: export
function hasRenderedCreatorCloneReport() {
  return Boolean(
    creatorReportView?.hasReport(creatorCloneResult)
    || creatorCloneResult?.querySelector(".creator-distillation-report"),
  );
}

function hasRenderedCreatorCloneOutput() {
  return hasRenderedCreatorCloneReport() || Boolean(creatorCloneResult?.querySelector(".prompt-preview"));
}

function revealCreatorCloneResultCard({scroll = false} = {}) {
  setProfileStageView("export");
  creatorCloneResultCard?.classList.remove("hidden", "stage-hidden");
  if (scroll) {
    creatorCloneResultCard?.scrollIntoView({behavior: "smooth", block: "start"});
  }
  renderCreatorCloneNextAction();
  return hasRenderedCreatorCloneOutput();
}

function renderCreatorCloneResult(result, set, prompt, exports = {}, options = {}) {
  currentCreatorRuntimeReport = result || null;
  currentDistillPrompt = prompt || currentDistillPrompt || "";
  if (creatorStrategyPlanCard) {
    creatorStrategyPlanCard.classList.toggle("hidden", !result);
  }
  if (creatorStrategyPlanResult) {
    creatorStrategyPlanResult.innerHTML = "";
  }
  if (creatorStrategyPlanStatus) {
    creatorStrategyPlanStatus.textContent = result
      ? "基于当前创作者蒸馏报告生成，不重新扫描、不重新富化。"
      : "请先完成创作者蒸馏报告。";
  }
  if (generateCreatorStrategyButton) {
    generateCreatorStrategyButton.disabled = !result || !set?.set_id;
  }
  if (creatorCloneExportActions) {
    creatorCloneExportActions.open = false;
    creatorCloneExportActions.classList.add("hidden");
    creatorCloneExportActions.hidden = true;
  }
  const overview = result?.sample_overview || creatorCloneOverviewFromSet(set);
  creatorCloneConfidence.textContent = overview.confidence || (result ? "distilled" : "prompt only");
  if (downloadCreatorCloneJson && exports.creator_clone_result_json && set?.set_id) {
    downloadCreatorCloneJson.href = `/api/creator-clone/sets/${encodeURIComponent(set.set_id)}/files/creator_clone_result.json`;
  }
  if (downloadCreatorCloneMd && set?.set_id) {
    const reportFile = exports.creator_clone_html ? "creator_clone.html" : "creator_clone.md";
    downloadCreatorCloneMd.href = `/api/creator-clone/sets/${encodeURIComponent(set.set_id)}/files/${reportFile}`;
    downloadCreatorCloneMd.textContent = reportFile === "creator_clone.html" ? "打开网页报告" : "下载 Markdown";
  }
  if (!result) {
    if (downloadCreatorCloneMd) {
      downloadCreatorCloneMd.href = "#";
      downloadCreatorCloneMd.textContent = "暂无网页报告";
    }
    creatorCloneResult.innerHTML = `
      <section class="public-analysis-hero">
        <span>LLM 未配置</span>
        <strong>已生成蒸馏 Prompt，可复制到外部大模型手动分析。</strong>
      </section>
      ${renderCreatorCloneEvidenceOverview(overview)}
      <pre class="prompt-preview">${escapeHtml(currentDistillPrompt.slice(0, 3000))}</pre>
    `;
    revealCreatorCloneResultCard({scroll: options.scroll !== false});
    return true;
  }
  const contentProfile = result.content_profile || overview.content_profile || {};
  const templateLabel = contentProfile.effective_label || contentProfile.requested_label || "自动判断";
  const rendered = creatorReportView?.render({
    container: creatorCloneResult,
    result,
    overview,
    templateLabel,
    viewModel: creatorReportViewModelFromResult(result, overview, templateLabel),
  });
  if (!rendered) {
    throw new Error("蒸馏报告节点未生成。");
  }
  revealCreatorCloneResultCard({scroll: options.scroll !== false});
  return true;
}

function safeRenderCreatorCloneResult(result, set, prompt, exports = {}, options = {}) {
  try {
    renderCreatorCloneResult(result, set, prompt, exports, options);
    const expectedReport = hasCreatorCloneResultPayload(result);
    const outputReady = expectedReport ? hasRenderedCreatorCloneReport() : hasRenderedCreatorCloneOutput();
    if (!outputReady) {
      throw new Error(expectedReport ? "蒸馏报告节点未生成。" : "蒸馏输出节点未生成。");
    }
    creatorCloneResultCard?.classList.remove("hidden", "stage-hidden");
    return true;
  } catch (error) {
    console.error("Creator clone report render failed", error);
    setProfileStageView("export", {scroll: options.scroll === true});
    creatorCloneResultCard?.classList.remove("hidden", "stage-hidden");
    if (creatorStrategyPlanCard) {
      creatorStrategyPlanCard.classList.add("hidden");
    }
    if (!creatorReportView?.showFailure(creatorCloneResult) && creatorCloneResult) {
      creatorCloneResult.textContent = "REPORT_RENDER_FAILED：报告已生成，但首次渲染失败。";
    }
    profileScanStatus.textContent = "REPORT_RENDER_FAILED：报告已生成，但页面首次渲染失败，请刷新或重新打开报告。";
    renderCreatorCloneNextAction();
    return false;
  }
}

function renderStrategyPlanItemList(items = [], emptyText = "暂无") {
  const rows = normalizeItems(items).filter(Boolean);
  if (!rows.length) {
    return `<p class="muted compact-copy">${escapeHtml(emptyText)}</p>`;
  }
  return `
    <ul class="public-report-list strategy-plan-list">
      ${rows.map((item) => {
        if (typeof item === "string") {
          return `<li>${escapeHtml(item)}</li>`;
        }
        const title = item.title || item.name || item.first_frame || "方案";
        const details = compactReportList(
          item.angle,
          item.why,
          item.formula_used ? `公式：${item.formula_used}` : "",
          item.expected_metric ? `指标：${item.expected_metric}` : "",
          item.production_notes,
          item.best_for,
          item.first_frame ? `首帧：${item.first_frame}` : "",
          item.action ? `动作：${item.action}` : "",
          item.camera ? `镜头：${item.camera}` : "",
          item.light_scene ? `光线/场景：${item.light_scene}` : "",
          item.title_topic ? `标题话题：${item.title_topic}` : "",
          item.validation_metric ? `验证：${item.validation_metric}` : "",
          item.risk_boundary ? `边界：${item.risk_boundary}` : "",
          item.cover_frame ? `封面：${item.cover_frame}` : "",
          item.promise ? `承诺：${item.promise}` : "",
          item.hook_type ? `钩子：${item.hook_type}` : "",
        ).slice(0, 6);
        const beats = normalizeItems(item.beats || item.beat_structure).map(formatReportValue).filter(Boolean);
        const timeline = normalizeItems(item.timeline).filter(Boolean);
        return `
          <li>
            <strong>${escapeHtml(title)}</strong>
            ${details.length ? `<p>${escapeHtml(details.join("；"))}</p>` : ""}
            ${beats.length ? `<ol>${beats.map((beat) => `<li>${escapeHtml(beat)}</li>`).join("")}</ol>` : ""}
            ${timeline.length ? `
              <ol class="strategy-plan-timeline">
                ${timeline.map((step) => {
                  const time = step.time || step.label || "";
                  const goal = step.goal || step.purpose || "";
                  const shot = step.shot || step.action || step.text || "";
                  return `<li><strong>${escapeHtml(time)}</strong>${escapeHtml([goal, shot].filter(Boolean).join("："))}</li>`;
                }).join("")}
              </ol>
            ` : ""}
            ${item.requires_review ? '<span class="strategy-plan-review">需人工复核</span>' : ""}
          </li>
        `;
      }).join("")}
    </ul>
  `;
}

function renderCreatorStrategyPlan(plan = {}) {
  if (!plan || typeof plan !== "object") {
    return "";
  }
  const lowConfidenceNotes = normalizeItems(plan.low_confidence_notes);
  const score = plan.source?.report_quality_score;
  const lowScore = score !== undefined && score !== null && Number(score) < 50;
  const warning = lowConfidenceNotes.length
    ? renderPublicCard(
      "低证据方案：不可直接拍摄",
      `
        <p class="strategy-plan-warning-copy">当前方案不可直接拍摄，需先补证据或人工复核。</p>
        ${lowScore ? '<p class="strategy-plan-warning-copy">低证据方案，仅供补证据和方向参考。</p>' : ""}
        ${renderStrategyPlanItemList(lowConfidenceNotes)}
      `,
      "warning wide",
    )
    : "";
  return `
    <div class="public-report-grid creator-strategy-plan-grid">
      ${warning}
      ${renderPublicCard("1. 下一批选题", renderStrategyPlanItemList(plan.next_topics, "暂无选题。"), "featured")}
      ${renderPublicCard("2. 脚本结构", renderStrategyPlanItemList(plan.script_templates, "暂无脚本结构。"), "featured")}
      ${renderPublicCard("3. 镜头 / 画面模板", renderStrategyPlanItemList(plan.shot_templates, "暂无镜头模板。"), "featured")}
      ${renderPublicCard("4. 标题 / 封面建议", renderStrategyPlanItemList(plan.title_cover_suggestions, "暂无标题封面建议。"))}
      ${renderPublicCard("5. 发布前自检", renderStrategyPlanItemList(plan.pre_publish_checklist, "暂无自检项。"))}
    </div>
  `;
}

async function generateCreatorStrategyPlan() {
  const setId = currentCreatorCloneSetId();
  if (!setId) {
    if (creatorStrategyPlanStatus) {
      creatorStrategyPlanStatus.textContent = "请先完成创作者蒸馏报告。";
    }
    return;
  }
  if (generateCreatorStrategyButton) {
    generateCreatorStrategyButton.disabled = true;
    generateCreatorStrategyButton.textContent = "生成中...";
  }
  if (creatorStrategyPlanStatus) {
    creatorStrategyPlanStatus.textContent = "正在把蒸馏报告转成下一批可执行创作方案。";
  }
  try {
    const response = await fetch(`/api/creator-intelligence/projects/${encodeURIComponent(setId)}/generate-strategy`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
    });
    const payload = await readJsonResponse(response);
    if (!payload.ok) {
      throw payload;
    }
    if (creatorStrategyPlanResult) {
      creatorStrategyPlanResult.innerHTML = renderCreatorStrategyPlan(payload.strategy_plan || {});
    }
    if (creatorStrategyPlanStatus) {
      const score = payload.source?.report_quality_score;
      creatorStrategyPlanStatus.textContent = score !== undefined && Number(score) < 50
        ? `低证据方案，仅供补证据和方向参考 · 报告质量 ${formatNumber(score)}/100`
        : `已生成下一批创作方案${score !== undefined ? ` · 报告质量 ${formatNumber(score)}/100` : ""}`;
    }
  } catch (error) {
    if (creatorStrategyPlanStatus) {
      creatorStrategyPlanStatus.textContent = `${error.error_code || "GENERATE_FAILED"}：${error.message || "生成创作方案失败。"}`;
    }
  } finally {
    if (generateCreatorStrategyButton) {
      generateCreatorStrategyButton.disabled = false;
      generateCreatorStrategyButton.textContent = "生成下一批创作方案";
    }
  }
}

function hasCreatorCloneResultPayload(result) {
  return Boolean(result && typeof result === "object" && Object.keys(result).length);
}

async function hydrateCreatorCloneReportFromSet(setId, options = {}) {
  if (!setId) {
    return null;
  }
  const response = await fetch(`/api/creator-clone/sets/${encodeURIComponent(setId)}`, {cache: "no-store"});
  const payload = await readJsonResponse(response);
  currentCloneSetId = payload.set?.set_id || currentCloneSetId;
  applyCreatorIntelligencePayload(payload);
  const fallbackPayload = options.fallbackPayload || {};
  const result = hasCreatorCloneResultPayload(payload.result)
    ? payload.result
    : hasCreatorCloneResultPayload(fallbackPayload.result)
      ? fallbackPayload.result
      : hasCreatorCloneResultPayload(currentCreatorRuntimeReport)
        ? currentCreatorRuntimeReport
        : null;
  const prompt = payload.prompt || fallbackPayload.prompt || "";
  const exportsPayload = payload.exports || fallbackPayload.exports || {};
  const rendered = safeRenderCreatorCloneResult(result, payload.set || fallbackPayload.set, prompt, exportsPayload, {
    scroll: options.scroll === true,
  });
  if (!rendered) {
    const error = new Error("持久化创作者蒸馏报告无法渲染。");
    error.error_code = "REPORT_RENDER_FAILED";
    throw error;
  }
  return payload;
}

async function hydrateRecentCreatorCloneReport(options = {}) {
  const currentSetId = currentCreatorCloneSetId();
  const url = currentSetId
    ? `/api/jobs/creator-clone-distill/recent?sample_set_id=${encodeURIComponent(currentSetId)}`
    : "/api/jobs/creator-clone-distill/recent";
  const response = await fetch(url, {cache: "no-store"});
  const payload = await readJsonResponse(response);
  const resultPayload = payload.job?.result_json || {};
  const setId = resultPayload.set?.set_id || "";
  if (!setId) {
    throw new Error("最近的创作者蒸馏任务没有关联素材池。");
  }
  currentCloneSetId = setId;
  rememberRecentCreatorCloneSetId(setId);
  await hydrateCreatorCloneReportFromSet(setId, {scroll: options.scroll === true, fallbackPayload: resultPayload});
  return resultPayload;
}

async function showCreatorCloneExportStage({scroll = true} = {}) {
  const setId = currentCreatorCloneSetId();
  const needsHydration = setId && (!creatorCloneResult?.innerHTML.trim() || !hasCreatorCloneReportLinkReady());
  if (needsHydration) {
    try {
      await hydrateCreatorCloneReportFromSet(setId, {scroll});
      return;
    } catch (error) {
      profileScanStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "报告恢复失败，请重新蒸馏或刷新页面。"}`;
    }
  }
  const needsRecentHydration = !setId && (!creatorCloneResult?.innerHTML.trim() || !hasCreatorCloneReportLinkReady());
  if (needsRecentHydration) {
    try {
      await hydrateRecentCreatorCloneReport({scroll});
      return;
    } catch (error) {
      profileScanStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "未找到最近的创作者蒸馏报告，请先完成蒸馏。"}`;
    }
  }
  setProfileStageView("export", {scroll});
  if (!creatorCloneResult?.innerHTML.trim() && currentCreatorCloneSetId()) {
    try {
      await hydrateCreatorCloneReportFromSet(currentCreatorCloneSetId(), {scroll: false});
    } catch {
      // Keep the export stage visible; the status line already explains recovery failures.
    }
  }
  renderCreatorCloneNextAction();
}

function applyCreatorCloneDistillPayload(payload) {
  applyCreatorIntelligencePayload(payload);
  const batch = payload.batch_distill || {};
  const recoveryHint = payload.recovery === "prompt_only"
    ? (payload.error_code === "LLM_NOT_CONFIGURED"
      ? "大模型未配置，已生成蒸馏 Prompt，可复制后手动分析。"
      : `${payload.error_code || "LLM_FAILED"}：${payload.message || "大模型蒸馏失败"} 已保留素材池证据和蒸馏 Prompt，可稍后重试或手动分析。`)
    : batch.batch_count
      ? `分批蒸馏完成：${formatNumber(batch.batch_count)} 个批次，已生成总汇总。`
      : "创作者蒸馏完成。";
  profileScanStatus.textContent = recoveryHint;
  currentCloneSetId = payload.set?.set_id || currentCloneSetId;
  safeRenderCreatorCloneResult(payload.result || null, payload.set, payload.prompt || "", payload.exports || {});
}

async function pollCreatorCloneDistillJob(jobId, options = {}) {
  if (activeHomeRoute !== "profile") {
    return {completed: false, rendered: false, superseded: true};
  }
  let job = null;
  if (options.safeStatus) {
    job = await fetchWorkbenchJob(jobId);
  } else {
    const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, {cache: "no-store"});
    const payload = await readJsonResponse(response);
    job = payload.job;
  }
  if (activeHomeRoute !== "profile") {
    return {completed: false, rendered: false, superseded: true};
  }
  if (!job) {
    return {completed: false, rendered: false};
  }
  renderJobStatus(job);
  if (options.safeStatus && job.status === "stale") {
    jobMessage.className = "job-message";
    jobMessage.textContent = `stale · ${job.progress || 0}% · ${job.message || "任务较长时间没有更新"}`;
    profileScanStatus.textContent = "蒸馏任务可能已停止更新。当前状态保持只读，不会自动轮询、重试或修改任务状态。";
    return {completed: false, rendered: false, stale: true};
  }
  if (job.status === "success") {
    renderJobStatus(job);
    const resultPayload = job.result_json || {};
    if (!options.safeStatus) {
      applyCreatorIntelligencePayload(resultPayload);
    }
    const setId = String(
      options.setId
      || resultPayload.set?.set_id
      || resultPayload.set_id
      || resultPayload.recovery_context?.sample_set_id
      || job.resume_target?.resource_id
      || "",
    );
    if (setId) {
      currentCloneSetId = setId;
      rememberRecentCreatorCloneSetId(setId);
      let rendered = safeRenderCreatorCloneResult(
        resultPayload.result || null,
        resultPayload.set,
        resultPayload.prompt || "",
        resultPayload.exports || {},
        {scroll: false},
      );
      const successMessage = resultPayload.batch_distill?.batch_count
        ? `分批蒸馏完成：${formatNumber(resultPayload.batch_distill.batch_count)} 个批次，已生成总汇总。`
        : "创作者蒸馏完成。";
      profileScanStatus.textContent = rendered
        ? successMessage
        : "创作者蒸馏完成，但任务结果渲染失败，正在恢复持久化报告。";
      let hydrateError = null;
      try {
        await hydrateCreatorCloneReportFromSet(setId, {scroll: false, fallbackPayload: resultPayload});
        rendered = hasRenderedCreatorCloneOutput();
      } catch (error) {
        hydrateError = error;
        if (rendered) {
          rendered = safeRenderCreatorCloneResult(
            resultPayload.result || null,
            resultPayload.set,
            resultPayload.prompt || "",
            resultPayload.exports || {},
            {scroll: false},
          );
        }
      }
      const expectsReport = hasCreatorCloneResultPayload(resultPayload.result)
        || hasCreatorCloneResultPayload(currentCreatorRuntimeReport);
      const reportVisible = expectsReport ? hasRenderedCreatorCloneReport() : hasRenderedCreatorCloneOutput();
      if (rendered && reportVisible) {
        revealCreatorCloneResultCard({scroll: false});
        const statusMessage = hydrateError
          ? `${hydrateError.error_code || "REPORT_SYNC_FAILED"}：${hydrateError.message || "报告文件同步失败，已使用任务结果直接渲染。"}`
          : successMessage;
        profileScanStatus.textContent = statusMessage;
        return {
          completed: true,
          rendered: true,
          setId,
          resultPayload,
          statusMessage,
        };
      }
      profileScanStatus.textContent = "REPORT_RENDER_FAILED：任务结果与持久化报告均无法渲染，请重新打开报告或再次蒸馏。";
      creatorCloneResultCard?.classList.remove("hidden", "stage-hidden");
      setProfileStageView("export");
      renderCreatorCloneNextAction();
      return {
        completed: true,
        rendered: false,
        setId,
        resultPayload,
        statusMessage: profileScanStatus.textContent,
      };
    }
    applyCreatorCloneDistillPayload(resultPayload);
    return {
      completed: true,
      rendered: hasRenderedCreatorCloneOutput(),
      setId: currentCreatorCloneSetId(),
      resultPayload,
      statusMessage: profileScanStatus.textContent,
    };
  }
  if (job.status === "failed") {
    jobMessage.className = "job-message failed";
    jobMessage.textContent = `${job.error_code || "ERROR"}：${job.message || "蒸馏失败"}`;
    profileScanStatus.textContent = jobMessage.textContent;
    updateCreatorCloneSelectionStatus();
    return {completed: false, rendered: false};
  }
  if (["pending", "running"].includes(job.status) && profileBuildJobAgeSeconds(job) >= WORKBENCH_TASK_STALE_SECONDS) {
    jobMessage.className = "job-message";
    jobMessage.textContent = `stale · ${job.progress || 0}% · ${job.message || "任务较长时间没有更新"}`;
    profileScanStatus.textContent = "蒸馏任务可能已停止更新。任务状态没有被修改；请检查模型服务后手动决定是否重新执行蒸馏。";
    return {completed: false, rendered: false, stale: true};
  }
  await new Promise((resolve) => {
    window.setTimeout(resolve, 900);
  });
  return pollCreatorCloneDistillJob(jobId, options);
}

function waitForCreatorCloneReportPaint() {
  return new Promise((resolve) => {
    if (typeof window.requestAnimationFrame === "function") {
      window.requestAnimationFrame(() => resolve());
      return;
    }
    window.setTimeout(resolve, 0);
  });
}

async function finalizeCreatorCloneDistillView(completion, {inputValueAtStart = "", scroll = true} = {}) {
  if (!completion?.completed) {
    return false;
  }
  const currentInputValue = creatorCloneUnifiedInputValue();
  const inputWasNotChangedDuringTask = currentInputValue === String(inputValueAtStart || "").trim();
  if (inputWasNotChangedDuringTask) {
    commitCreatorCloneUnifiedInput();
  }

  const resultPayload = completion.resultPayload || {};
  applyCreatorIntelligencePayload(resultPayload);
  const setId = completion.setId || resultPayload.set?.set_id || currentCreatorCloneSetId();
  if (!hasRenderedCreatorCloneOutput() && setId) {
    try {
      await hydrateCreatorCloneReportFromSet(setId, {scroll: false, fallbackPayload: resultPayload});
    } catch (error) {
      if (hasCreatorCloneResultPayload(resultPayload.result) || resultPayload.prompt) {
        safeRenderCreatorCloneResult(
          resultPayload.result || null,
          resultPayload.set,
          resultPayload.prompt || "",
          resultPayload.exports || {},
          {scroll: false},
        );
      } else {
        profileScanStatus.textContent = `${error.error_code || "REPORT_SYNC_FAILED"}：${error.message || "报告同步失败，请重新打开报告。"}`;
      }
    }
  }

  if (!inputWasNotChangedDuringTask && hasPendingQuickImportInput()) {
    return hasRenderedCreatorCloneOutput();
  }

  revealCreatorCloneResultCard({scroll: false});
  await waitForCreatorCloneReportPaint();

  const outputReady = hasRenderedCreatorCloneOutput();
  if (!outputReady) {
    profileScanStatus.textContent = "REPORT_RENDER_FAILED：报告已生成，但页面没有生成报告节点，请重新打开报告。";
    return false;
  }

  // Reapply the export stage after the distill function unlocks its controls;
  // the committed input baseline keeps later wizard renders on this stage.
  setProfileStageView("export");
  creatorCloneResultCard?.classList.remove("hidden", "stage-hidden");
  renderCreatorCloneNextAction();
  creatorCloneResultCard?.classList.remove("hidden", "stage-hidden");
  if (completion.statusMessage) {
    profileScanStatus.textContent = completion.statusMessage;
  }
  if (scroll) {
    creatorCloneResultCard?.scrollIntoView({behavior: "smooth", block: "start"});
  }
  return true;
}

// Creator Clone: distillation
async function distillSelectedCreatorClone(options = {}) {
  const shouldConfirmReadiness = options.confirmReadiness !== false;
  const selected = selectedCreatorSampleViewItems();
  if (!selected.length) {
    profileScanStatus.textContent = "请先选择要蒸馏的样本。";
    return;
  }
  if (selected.length > CREATOR_CLONE_MAX_DISTILL_SAMPLES) {
    profileScanStatus.textContent = `当前 MVP 最多选择 ${CREATOR_CLONE_MAX_DISTILL_SAMPLES} 条进行蒸馏，避免上下文过长。`;
    return;
  }
  if (shouldConfirmReadiness) {
    confirmProfileDistillReadiness(selected);
  }
  setProfileStageView("distill", {scroll: true});
  if (options.triggeredByQueue) {
    profileScanStatus.textContent = selected.length < 2
      ? "样本富化完成；样本过少，正在生成临时蒸馏结果..."
      : "样本富化完成，正在调用大模型蒸馏创作者规则...";
  } else {
    profileScanStatus.textContent = selected.length < 2
      ? "样本过少，结果仅供参考。正在生成蒸馏 Prompt..."
      : "正在调用大模型蒸馏创作者规则...";
  }
  setCreatorCloneDistillButtonsLocked(true);
  renderCreatorCloneNextAction();
  const inputValueAtStart = creatorCloneUnifiedInputValue();
  let completion = null;
  try {
    const selectedIds = selected.map(sampleViewItemKey);
    await syncCreatorCloneWorkflowSelection();
    await markCreatorCloneDistillationStarted();
    if (!placeJobCard("profile")) {
      return;
    }
    resetJobCard("正在创建创作者蒸馏任务...");
    scrollProfileTaskPanel();
    const response = await fetch("/api/jobs/creator-clone-distill", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        sample_set_id: currentCloneSetId,
        samples: currentCloneSetId ? [] : activeCreatorSampleViewItems().map(creatorCloneSamplePayload),
        selected_sample_ids: selectedIds,
        distill_mode: profileDistillMode?.value || "quick",
        include_case_reports: true,
        max_samples: CREATOR_CLONE_MAX_DISTILL_SAMPLES,
        title: "创作者蒸馏素材池",
        source_platform: "douyin",
        content_profile: profileContentProfile?.value || "auto",
      }),
    });
    const payload = await readJsonResponse(response);
    profileScanStatus.textContent = `已创建创作者蒸馏任务：${payload.selected_count || selected.length} 条样本。`;
    completion = await pollCreatorCloneDistillJob(payload.job_id);
  } catch (error) {
    if (activeHomeRoute !== "profile") {
      return;
    }
    profileScanStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "蒸馏失败"}`;
    jobMessage.className = "job-message failed";
    jobMessage.textContent = profileScanStatus.textContent;
  } finally {
    setCreatorCloneDistillButtonsLocked(false);
    updateCreatorCloneSelectionStatus();
    renderCreatorCloneNextAction();
  }
  if (completion?.completed) {
    await finalizeCreatorCloneDistillView(completion, {inputValueAtStart, scroll: true});
  }
}

async function batchDistillSelectedCreatorClone(options = {}) {
  const selected = selectedCreatorSampleViewItems();
  if (!selected.length) {
    profileScanStatus.textContent = "请先选择要分批蒸馏的样本。";
    return;
  }
  if (selected.length > PROFILE_BUILD_MAX_ITEMS) {
    profileScanStatus.textContent = `当前分批蒸馏最多支持 ${PROFILE_BUILD_MAX_ITEMS} 条样本。`;
    return;
  }
  if (options.confirm !== false && profileScanStatus) {
    profileScanStatus.textContent = `将把 ${selected.length} 条样本按每 ${CREATOR_CLONE_MAX_DISTILL_SAMPLES} 条一批进行蒸馏，并汇总为账号级报告。`;
  }
  const selectedIds = selected.map(sampleViewItemKey);
  setProfileStageView("distill", {scroll: true});
  setCreatorCloneDistillButtonsLocked(true);
  renderCreatorCloneNextAction();
  const inputValueAtStart = creatorCloneUnifiedInputValue();
  let completion = null;
  try {
    await syncCreatorCloneWorkflowSelection();
    await markCreatorCloneDistillationStarted();
    if (!placeJobCard("profile")) {
      return;
    }
    resetJobCard(options.triggeredByQueue ? "富化完成，正在创建分批蒸馏任务..." : "正在创建分批蒸馏任务...");
    scrollProfileTaskPanel();
    const response = await fetch("/api/jobs/creator-clone-batch-distill", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        sample_set_id: currentCloneSetId,
        samples: currentCloneSetId ? [] : activeCreatorSampleViewItems().map(creatorCloneSamplePayload),
        selected_sample_ids: selectedIds,
        distill_mode: profileDistillMode?.value || "quick",
        batch_size: CREATOR_CLONE_MAX_DISTILL_SAMPLES,
        max_samples: PROFILE_BUILD_MAX_ITEMS,
        title: "创作者蒸馏素材池",
        source_platform: "douyin",
        content_profile: profileContentProfile?.value || "auto",
      }),
    });
    const payload = await readJsonResponse(response);
    profileScanStatus.textContent = `已创建分批蒸馏任务：${payload.selected_count || selected.length} 条样本，${payload.batch_count || 1} 个批次。`;
    completion = await pollCreatorCloneDistillJob(payload.job_id);
  } catch (error) {
    if (activeHomeRoute !== "profile") {
      return;
    }
    profileScanStatus.textContent = `${error.error_code || "ERROR"}：${error.message || "分批蒸馏失败"}`;
    jobMessage.className = "job-message failed";
    jobMessage.textContent = profileScanStatus.textContent;
  } finally {
    setCreatorCloneDistillButtonsLocked(false);
    updateCreatorCloneSelectionStatus();
    renderCreatorCloneNextAction();
  }
  if (completion?.completed) {
    await finalizeCreatorCloneDistillView(completion, {inputValueAtStart, scroll: true});
  }
}

function setWorkbenchStatus(id, label, status = "partial") {
  const pill = workbenchStatusPills.find((item) => item.dataset.workbenchStatus === id);
  if (!pill) {
    return;
  }
  pill.textContent = label;
  const badgeState = window.WorkbenchShell?.normalizeBadgeState(status)
    || (["ready", "missing", "disabled", "partial"].includes(status) ? status : "partial");
  pill.className = `workbench-status-pill ${badgeState}`;
}

function workbenchStatusLabel(item = {}, fallbackLabel = "") {
  const badge = window.WorkbenchShell?.preflightBadge(item, fallbackLabel);
  if (badge) {
    return badge.label;
  }
  const status = item.status || "partial";
  const label = item.label || fallbackLabel || item.id || "检查项";
  const suffix = {ready: "可用", missing: "缺失", disabled: "关闭", partial: "待确认"}[status] || status;
  return `${label} ${suffix}`;
}

function renderWorkbenchLlmStatus(llm = {}) {
  if (llm.configured) {
    setWorkbenchStatus("llm", `LLM ${llm.model || "已配置"}`, "ready");
    return;
  }
  setWorkbenchStatus("llm", "LLM 未配置", "disabled");
}

function renderWorkbenchPreflightStatus(preflight = {}) {
  void preflight;
  setWorkbenchStatus("security", "本地安全模式", "ready");
}

function renderPreflightStatus(preflight) {
  if (!preflightSummary || !preflightList) {
    renderWorkbenchPreflightStatus(preflight || {});
    return;
  }
  const summary = preflight.summary || {};
  preflightCopySnippets = [];
  const refreshedAt = window.WorkbenchShell?.formatRefreshTime(Date.now()) || "刚刚";
  preflightSummary.textContent = `就绪 ${summary.ready_count || 0}/${summary.total_count || 0}，缺失 ${summary.missing_count || 0}，关闭 ${summary.disabled_count || 0}。最后刷新 ${refreshedAt}。`;
  preflightList.innerHTML = normalizeItems(preflight.checks)
    .map((item) => {
      const status = item.status || "unknown";
      const statusLabel = {ready: "可用", partial: "待打开", missing: "缺失", disabled: "关闭"}[status] || status;
      const snippet = String(item.env_snippet || "");
      const snippetIndex = snippet ? preflightCopySnippets.push(snippet) - 1 : -1;
      return `
        <article class="preflight-item">
          <strong>
            ${escapeHtml(item.label || item.id || "检查项")}
            <span class="preflight-status ${escapeHtml(status)}">${escapeHtml(statusLabel)}</span>
          </strong>
          <p>${escapeHtml(item.message || "")}</p>
          ${normalizeItems(item.contract_summary).length ? `<ul class="preflight-contract-summary">${normalizeItems(item.contract_summary).map((value) => `<li>${escapeHtml(value)}</li>`).join("")}</ul>` : ""}
          ${item.action_hint ? `<p class="preflight-action">${escapeHtml(item.action_hint)}</p>` : ""}
          ${snippet ? `
            <div class="preflight-command-row">
              <pre class="preflight-env-snippet">${escapeHtml(snippet)}</pre>
              <button type="button" class="text-button preflight-copy-button" data-preflight-copy-index="${snippetIndex}">复制命令</button>
            </div>
          ` : ""}
        </article>
      `;
    })
    .join("");
  renderWorkbenchPreflightStatus(preflight || {});
}

async function loadPreflightStatus() {
  if (preflightSummary) {
    preflightSummary.textContent = "正在检查本地工具...";
  }
  const response = await fetch("/api/settings/preflight", {cache: "no-store"});
  const payload = await readJsonResponse(response);
  renderPreflightStatus(payload.preflight || {});
  return payload;
}

function creatorCloneCurrentProfileValue() {
  const candidates = [
    creatorCloneUnifiedInputValue(),
    profileForm ? String(new FormData(profileForm).get("profile_url") || "").trim() : "",
    profileLastChromeProfileValue,
    ...collectCreatorCloneProfileInputCandidates(profileScanPayload || {}),
  ];
  for (const candidate of candidates) {
    const target = firstDouyinProfileTargetFromText(candidate);
    if (target) {
      return target;
    }
  }
  return "";
}

function buildFullPrompt(data) {
  const analysisInput = JSON.stringify(data.analysis_input || {}, null, 2);
  return `${data.prompt || ""}\n\n## 附：analysis_input.json\n\n\`\`\`json\n${analysisInput}\n\`\`\``;
}

function renderWorkflowResult(result) {
  const caseInfo = result.case || {};
  const caseId = result.case_id || caseInfo.case_id || "";
  const rows = [
    ["素材包 ID", caseId || ""],
    ["素材包状态", "已生成"],
    ["AI 自动拆解", result.analysis_status === "success" ? "已生成" : "未配置或未完成，可在 case 详情页重试"],
  ].filter(([, value]) => value);

  caseSummary.innerHTML = `
    <div class="case-status">素材包已生成</div>
    <dl>
      ${rows.map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`).join("")}
    </dl>
  `;
  uploadResult.classList.add("hidden");
  uploadResult.textContent = "";
}

function getCaseId(result) {
  const caseInfo = result.case || {};
  return result.case_id || caseInfo.case_id || "";
}

async function loadCasePayload(caseId) {
  const response = await fetch(`/api/cases/${caseId}`, {cache: "no-store"});
  const payload = await readJsonResponse(response);
  return payload.case;
}

function renderHomeCase(data) {
  loadedHomeCase = data;
  renderSingleItemStatus();
  const metadata = data.metadata || {};
  const analysisInput = data.analysis_input || {};
  const stats = analysisInput.stats || {};
  const report = data.analysis_report || "";
  const analysisResult = data.analysis_result || null;
  const analysisJob = data.analysis_job || {};
  const caseUrl = `/cases/${data.case_id}`;

  homeCaseView.classList.remove("hidden");
  homeContactSheet.src = `${data.artifact_urls.contact_sheet}?v=${Date.now()}`;
  openFullCaseLink.href = caseUrl;
  renderDefinitionList(homeCaseMeta, [
    ["标题", metadata.title],
    ["作者", metadata.author],
    ["点赞", formatNumber(stats.like_count)],
    ["评论", formatNumber(stats.comment_count)],
    ["分享", formatNumber(stats.share_count)],
  ]);

  if (analysisResult) {
    homeAiStatus.textContent = "AI 自动拆解已生成。";
    homeAiReport.innerHTML = renderPublicAnalysisReport(analysisResult);
  } else if (analysisJob.status === "failed") {
    const error = analysisJob.error || {};
    homeAiStatus.textContent = `${singleItemFailureCategory(error, "analysis")}。可更换模型后重新解析，或打开完整素材包查看现有结果。`;
    homeAiReport.innerHTML = "";
  } else if (analysisJob.status === "skipped") {
    homeAiStatus.textContent = "视频已准备好，但 AI 自动拆解未配置。配置模型后可重新解析。";
    homeAiReport.innerHTML = "";
  } else if (analysisJob.status === "pending" || analysisJob.status === "running") {
    homeAiStatus.textContent = "视频已准备好，AI 正在拆解。拆解完成后会在这里显示结果。";
    homeAiReport.innerHTML = "";
  } else {
    homeAiStatus.textContent = "视频已准备好。AI 摘要将在拆解完成后显示。";
    homeAiReport.innerHTML = "";
  }
}

async function showAnalysisInline(result, options = {}) {
  const caseId = getCaseId(result);
  if (!caseId) {
    return false;
  }
  if (options.updateMessage !== false) {
    jobMessage.textContent = "素材包已生成，正在加载首页分析视图...";
  }
  const caseData = await loadCasePayload(caseId);
  if (
    Number.isInteger(options.observationGeneration)
    && !isCurrentSingleItemObservation(options.jobId, options.observationGeneration)
  ) {
    return false;
  }
  if (result.analysis_status) {
    caseData.analysis_job = {
      status: result.analysis_status,
      error: result.analysis_error || {},
    };
  }
  if (result.analysis && result.analysis.analysis_result) {
    caseData.analysis_result = result.analysis.analysis_result;
  }
  if (result.analysis && result.analysis.analysis_report) {
    caseData.analysis_report = result.analysis.analysis_report;
  }
  renderHomeCase(caseData);
  if (options.scroll !== false) {
    resultCard.scrollIntoView({behavior: "smooth", block: "start"});
  }
  return true;
}

async function readJsonResponse(response) {
  const payload = await response.json().catch(() => ({
    ok: false,
    error_code: "INVALID_RESPONSE",
    message: "接口返回不是 JSON。",
  }));
  if (!response.ok || payload.ok === false) {
    throw payload;
  }
  return payload;
}

homeRouteButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setHomeRoute(button.dataset.homeRoute);
    if (button.dataset.workbenchFocus === "chrome") {
      window.setTimeout(() => {
        profilePublicSection?.scrollIntoView({behavior: "smooth", block: "start"});
      }, 120);
    }
  });
});

function safeWorkbenchInternalUrl(value) {
  let url;
  try {
    url = new URL(String(value || ""), window.location.origin);
  } catch {
    return "";
  }
  if (url.origin !== window.location.origin || url.search || url.hash) {
    return "";
  }
  if (/^\/cases\/[A-Za-z0-9_-]{1,100}$/.test(url.pathname)) {
    return url.pathname;
  }
  if (/^\/api\/creator-clone\/sets\/clone_[a-f0-9]{32}\/files\/creator_clone\.(?:html|md)$/i.test(url.pathname)) {
    return url.pathname;
  }
  return "";
}

function notifyWorkbenchTargetResult(ok, message = "") {
  document.dispatchEvent(new CustomEvent("workbench:target-result", {
    detail: {ok, message},
  }));
}

function safeWorkbenchJobId(value) {
  const jobId = String(value || "").trim();
  return /^job_[A-Za-z0-9-]{1,80}$/.test(jobId) ? jobId : "";
}

function safeWorkbenchResumeMode(value) {
  const mode = String(value || "manual").toLowerCase();
  return ["observe", "manual", "result"].includes(mode) ? mode : "manual";
}

async function fetchWorkbenchJob(jobId) {
  const safeJobId = safeWorkbenchJobId(jobId);
  if (!safeJobId) {
    return null;
  }
  const response = await fetch(`/api/workbench/jobs/${encodeURIComponent(safeJobId)}`, {cache: "no-store"});
  const payload = await readJsonResponse(response);
  const job = payload.job || payload.task || null;
  if (!job) {
    return null;
  }
  return {
    ...job,
    id: job.id || job.task_id || safeJobId,
    type: job.type || job.task_type || "",
    result_json: job.result_json || job.result || {},
  };
}

function renderWorkbenchRestoredJobStatus(job, mode, fallbackMessage = "已恢复任务状态") {
  renderJobStatus(job, fallbackMessage);
  const staleView = job?.status === "stale"
    || (mode === "manual" && ["pending", "running"].includes(job?.status));
  if (staleView && jobMessage) {
    jobMessage.className = "job-message";
    const isSingleScope = typeof currentJobCardScope !== "undefined" && currentJobCardScope === "single";
    const message = isSingleScope
      ? singleItemJobMessage({...job, status: "stale"})
      : job.message || "任务较长时间没有更新";
    jobMessage.textContent = `stale · ${job.progress || 0}% · ${message}`;
  }
  return staleView;
}

async function renderRecoveredSingleJob(
  job,
  {scroll = false, observationGeneration = null, observationJobId = ""} = {},
) {
  if (
    Number.isInteger(observationGeneration)
    && !isCurrentSingleItemObservation(observationJobId, observationGeneration)
  ) {
    return false;
  }
  const canRenderSingleItemStatus = typeof renderSingleItemStatus === "function";
  if (typeof currentSingleJob !== "undefined") {
    currentSingleJob = job || null;
  }
  if (canRenderSingleItemStatus) {
    renderSingleItemStatus();
  }
  const result = job?.result_json || {};
  const caseId = getCaseId(result);
  if (!caseId) {
    if (jobResult && Object.keys(result).length) {
      const statusView = canRenderSingleItemStatus ? renderSingleItemStatus() : null;
      showJson(jobResult, {
        status: job?.status || "unknown",
        progress: Number(job?.progress || 0),
        result_summary: statusView?.overallLabel || "状态更新中",
      });
    }
    return false;
  }
  currentLocalVideoId = result.local_video_id || result.download?.local_video_id || currentLocalVideoId;
  resultCard.classList.remove("hidden");
  buildCaseButton.hidden = true;
  renderWorkflowResult(result);
  try {
    const analysisShown = await showAnalysisInline(result, {
      scroll,
      updateMessage: false,
      jobId: observationJobId,
      observationGeneration,
    });
    if (
      Number.isInteger(observationGeneration)
      && !isCurrentSingleItemObservation(observationJobId, observationGeneration)
    ) {
      return false;
    }
    if (!analysisShown) {
      return false;
    }
  } catch (error) {
    if (
      Number.isInteger(observationGeneration)
      && !isCurrentSingleItemObservation(observationJobId, observationGeneration)
    ) {
      return false;
    }
    homeAiStatus.textContent = `${singleItemFailureCategory(error, "case")}。素材包视图暂时无法加载。`;
  }
  return true;
}

async function openWorkbenchSingleTarget(target, openUrl) {
  const mode = safeWorkbenchResumeMode(target?.mode);
  const jobId = safeWorkbenchJobId(target?.job_id);
  if (openUrl && mode !== "observe") {
    window.location.assign(openUrl);
    return true;
  }
  setHomeRoute("single");
  const observationGeneration = startSingleItemObservation(jobId);
  currentSingleJob = null;
  loadedHomeCase = null;
  singleItemFlow = {stage: "idle", status: "pending", error_code: ""};
  currentLocalVideoId = "";
  homeCaseView.classList.add("hidden");
  resultCard.classList.add("hidden");
  singleButton.disabled = false;
  singleButton.textContent = "解析";
  buildCaseButton.disabled = false;
  renderSingleItemStatus();
  const resourceId = String(target?.resource_id || "");
  let restoredResource = false;
  if (/^\d{15,22}$/.test(resourceId) && singleForm?.elements?.value) {
    singleForm.elements.value.value = resourceId;
    restoredResource = true;
  } else if (/^local_[A-Za-z0-9_-]{1,94}$/.test(resourceId)) {
    currentLocalVideoId = resourceId;
    restoredResource = true;
  }
  window.scrollTo({top: 0, behavior: "smooth"});
  if (!jobId) {
    return restoredResource;
  }
  placeJobCard("single");
  const job = await fetchWorkbenchJob(jobId);
  if (!isCurrentSingleItemObservation(jobId, observationGeneration)) {
    return false;
  }
  if (!job) {
    return false;
  }
  renderWorkbenchRestoredJobStatus(job, mode);
  const restoredCase = await renderRecoveredSingleJob(job, {
    scroll: false,
    observationGeneration,
    observationJobId: jobId,
  });
  if (!isCurrentSingleItemObservation(jobId, observationGeneration)) {
    return false;
  }
  if (mode === "observe" && ["pending", "running"].includes(job.status)) {
    await monitorWorkbenchSingleJob(jobId, observationGeneration);
    return true;
  }
  if (mode === "observe" && job.status === "stale") {
    return true;
  }
  return restoredCase || restoredResource;
}

async function monitorWorkbenchSingleJob(
  jobId,
  observationGeneration = singleItemObservationGeneration,
) {
  if (!isCurrentSingleItemObservation(jobId, observationGeneration)) {
    return false;
  }
  const job = await fetchWorkbenchJob(jobId);
  if (!isCurrentSingleItemObservation(jobId, observationGeneration)) {
    return false;
  }
  if (!job) {
    return false;
  }
  if (renderJobStatus(job) === false) {
    return true;
  }
  await renderRecoveredSingleJob(job, {
    scroll: job.status === "success",
    observationGeneration,
    observationJobId: jobId,
  });
  if (!isCurrentSingleItemObservation(jobId, observationGeneration)) {
    return false;
  }
  if (job.status === "stale") {
    renderWorkbenchRestoredJobStatus(job, "manual");
    return true;
  }
  if (["success", "failed"].includes(job.status)) {
    return true;
  }
  if (["pending", "running"].includes(job.status) && profileBuildJobAgeSeconds(job) >= WORKBENCH_TASK_STALE_SECONDS) {
    renderWorkbenchRestoredJobStatus(job, "manual");
    return true;
  }
  await new Promise((resolve) => window.setTimeout(resolve, 900));
  return monitorWorkbenchSingleJob(jobId, observationGeneration);
}

async function monitorWorkbenchProfileScanJob(jobId) {
  if (activeHomeRoute !== "profile") {
    return false;
  }
  const job = await fetchWorkbenchJob(jobId);
  if (activeHomeRoute !== "profile") {
    return false;
  }
  if (!job) {
    return false;
  }
  if (!placeJobCard("profile")) {
    return false;
  }
  renderJobStatus(job, "已恢复主页扫描任务");
  if (job.status === "stale") {
    renderWorkbenchRestoredJobStatus(job, "manual");
    profileScanStatus.textContent = "主页扫描任务可能已停止更新。当前状态保持只读，不会自动轮询、重试或修改任务状态。";
    return true;
  }
  if (job.status === "success") {
    const setId = String(
      job.result_json?.set?.set_id
      || job.result_json?.set_id
      || job.result_json?.recovery_context?.sample_set_id
      || job.resume_target?.resource_id
      || "",
    );
    if (setId) {
      await refreshProfilePoolFromPersistedSet(setId);
    }
    if (activeHomeRoute !== "profile") {
      return false;
    }
    profileScanStatus.textContent = "主页扫描任务已完成；请确认素材池后继续。";
    return true;
  }
  if (job.status === "failed") {
    profileScanStatus.textContent = `${job.error_code || "ERROR"}：${job.message || "主页扫描失败"}`;
    return true;
  }
  if (["pending", "running"].includes(job.status) && profileBuildJobAgeSeconds(job) >= WORKBENCH_TASK_STALE_SECONDS) {
    profileScanStatus.textContent = "主页扫描任务可能已停止更新。任务状态保持不变，请由你决定是否重新执行导入。";
    return true;
  }
  await new Promise((resolve) => window.setTimeout(resolve, 900));
  return monitorWorkbenchProfileScanJob(jobId);
}

async function openWorkbenchProfileTarget(target) {
  const setId = String(target?.resource_id || "");
  const jobId = safeWorkbenchJobId(target?.job_id);
  const taskType = String(target?.task_type || "");
  const mode = safeWorkbenchResumeMode(target?.mode);
  const stage = String(target?.stage || "");
  setHomeRoute("profile");
  window.scrollTo({top: 0, behavior: "smooth"});

  if (!setId) {
    setProfileStageView("import", {scroll: false});
    if (jobId) {
      if (taskType === "profile-scan" && mode === "observe") {
        return monitorWorkbenchProfileScanJob(jobId);
      }
      const job = await fetchWorkbenchJob(jobId);
      if (job) {
        if (!placeJobCard("profile")) {
          return false;
        }
        const staleView = renderWorkbenchRestoredJobStatus(job, mode);
        profileScanStatus.textContent = staleView
          ? "主页扫描任务可能已停止更新。已恢复导入步骤，但不会自动轮询、重试或修改任务状态。"
          : job.status === "failed"
          ? `${job.error_code || "ERROR"}：${job.message || "任务失败"}`
          : "已打开任务对应的导入步骤；系统不会自动重新执行。";
      }
      return mode === "observe" && Boolean(job);
    }
    return false;
  }
  if (!isSafeCreatorCloneSetId(setId)) {
    return false;
  }

  resetCreatorClonePoolForNewProfile();
  rememberRecentCreatorCloneSetId(setId);
  if (taskType === "profile-build-cases" && jobId) {
    rememberRecentProfileBuildState({setId, jobId});
  }
  recentCreatorCloneRestoreAttempted = false;
  const shouldObserve = mode === "observe";
  const restored = await restoreRecentCreatorCloneSet({
    pollActive: false,
    restoreQueue: false,
  });
  if (!restored) {
    return false;
  }

  if (taskType === "profile-build-cases" && jobId) {
    await restoreRecentProfileBuildJob(setId, {
      pollActive: shouldObserve,
      allowAutoDistill: false,
      safeStatus: true,
    });
  }
  if (["import", "pool", "select", "enrich", "distill", "export"].includes(stage)) {
    setProfileStageView(stage, {scroll: false});
  }
  if (["creator-clone-distill", "creator-clone-batch-distill"].includes(taskType) && jobId) {
    if (!placeJobCard("profile")) {
      return false;
    }
    const job = await fetchWorkbenchJob(jobId);
    if (activeHomeRoute !== "profile") {
      return false;
    }
    let staleView = false;
    if (job) {
      staleView = renderWorkbenchRestoredJobStatus(job, mode, "已恢复创作者蒸馏任务");
    }
    if (shouldObserve && ["pending", "running"].includes(job?.status)) {
      setCreatorCloneDistillButtonsLocked(true);
      renderCreatorCloneNextAction();
      try {
        const completion = await pollCreatorCloneDistillJob(jobId, {
          safeStatus: true,
          setId,
        });
        if (completion?.completed) {
          await finalizeCreatorCloneDistillView(completion, {
            inputValueAtStart: creatorCloneUnifiedInputValue(),
            scroll: true,
          });
        }
      } finally {
        setCreatorCloneDistillButtonsLocked(false);
        updateCreatorCloneSelectionStatus();
        renderCreatorCloneNextAction();
      }
    } else if (staleView) {
      profileScanStatus.textContent = "蒸馏任务可能已停止更新。已恢复蒸馏步骤，但不会自动轮询、重试或修改任务状态。";
    } else if (job?.status === "failed") {
      profileScanStatus.textContent = `${job.error_code || "ERROR"}：${job.message || "蒸馏失败"}。已有素材池和证据仍保留，请手动决定是否重跑。`;
    }
  }
  return true;
}

document.addEventListener("workbench:navigate", (event) => {
  const route = String(event.detail?.route || "");
  if (!["single", "profile"].includes(route)) {
    return;
  }
  setHomeRoute(route);
  window.scrollTo({top: 0, behavior: "smooth"});
});

document.addEventListener("workbench:open-url", (event) => {
  const openUrl = safeWorkbenchInternalUrl(event.detail?.open_url);
  if (openUrl) {
    window.open(openUrl, "_blank", "noopener,noreferrer");
  }
});

document.addEventListener("workbench:open-target", async (event) => {
  const target = event.detail?.target;
  const route = String(target?.route || "");
  if (!["single", "profile"].includes(route)) {
    notifyWorkbenchTargetResult(false, "任务目标无效，概览未执行跳转。");
    return;
  }
  if (route === "single") {
    const openUrl = safeWorkbenchInternalUrl(event.detail?.open_url || target?.open_url);
    let observationGeneration = null;
    let observationJobId = "";
    try {
      const restorePromise = openWorkbenchSingleTarget(target, openUrl);
      observationGeneration = singleItemObservationGeneration;
      observationJobId = singleItemActiveJobId;
      const restored = await restorePromise;
      if (!isCurrentSingleItemObservation(observationJobId, observationGeneration)) {
        return;
      }
      notifyWorkbenchTargetResult(restored, restored ? "" : "单作品任务状态无法恢复，请重新导入。" );
    } catch (error) {
      if (
        Number.isInteger(observationGeneration)
        && !isCurrentSingleItemObservation(observationJobId, observationGeneration)
      ) {
        return;
      }
      notifyWorkbenchTargetResult(
        false,
        `${singleItemFailureCategory(error, "case")}。单作品任务状态暂时无法恢复。`,
      );
    }
    return;
  }
  try {
    const restored = await openWorkbenchProfileTarget(target);
    notifyWorkbenchTargetResult(
      restored,
      restored ? "" : "指定 Creator set 无法恢复，请在创作者页面重新导入。",
    );
  } catch (error) {
    notifyWorkbenchTargetResult(false, `${error.error_code || "ERROR"}：${error.message || "创作者任务恢复失败"}`);
  }
});

function restoreLibraryResumeTarget() {
  const storageKey = "shortVideoAgent.library.resumeTarget.v1";
  let raw = "";
  try {
    raw = window.sessionStorage.getItem(storageKey) || "";
    window.sessionStorage.removeItem(storageKey);
  } catch (_error) {
    return;
  }
  if (!raw) {
    return;
  }
  let target;
  try {
    target = JSON.parse(raw);
  } catch (_error) {
    return;
  }
  const route = String(target?.route || "");
  const resourceId = String(target?.resource_id || "");
  const validResource = route === "profile"
    ? /^clone_[A-Za-z0-9_-]{1,94}$/.test(resourceId)
    : /^case_[A-Za-z0-9_-]{1,94}$/.test(resourceId);
  if (!["single", "profile"].includes(route) || !validResource) {
    return;
  }
  document.dispatchEvent(new CustomEvent("workbench:open-target", {
    detail: {
      target: {
        route,
        stage: route === "profile" ? "export" : "case",
        resource_id: resourceId,
        job_id: "",
        task_type: route === "profile" ? "creator_report" : "case_asset",
        mode: "result",
        open_url: safeWorkbenchInternalUrl(target?.open_url),
      },
      open_url: safeWorkbenchInternalUrl(target?.open_url),
    },
  }));
}

function markWorkbenchPreflightFailed() {
  const fallback = window.WorkbenchShell?.apiFailureBadge("本地状态")
    || {label: "本地状态待确认", status: "partial"};
  setWorkbenchStatus("security", fallback.label, fallback.status);
}

function updateAssistantContext(route = routeFromHash()) {
  if (!assistantCurrentStage || !assistantNextStep || !assistantMacroStep) {
    return;
  }
  const activeRoute = ["workbench", "single", "profile"].includes(route) ? route : "workbench";
  if (activeRoute === "single") {
    assistantCurrentStage.textContent = "单作品解析";
    assistantMacroStep.textContent = loadedHomeCase ? "3. 爆款拆解" : "1. 素材导入";
    assistantNextStep.textContent = loadedHomeCase ? "查看单条拆解结果，或复制 Prompt 继续人工分析。" : "粘贴单条作品链接，生成素材包和拆解报告。";
  } else if (activeRoute === "profile") {
    assistantCurrentStage.textContent = `Creator Clone Lab · ${creatorCloneCurrentStep?.textContent || "导入素材"}`;
    assistantMacroStep.textContent = currentCreatorRuntimeReport
      ? "4. 克隆规则 / 复用输出"
      : (creatorCloneEnrichmentRunning ? "2. 证据富化" : "1. 素材导入 / 选择样本");
    assistantNextStep.textContent = currentCreatorRuntimeReport
      ? "查看创作者蒸馏报告，或生成下一批创作方案。"
      : "按 6 步流程导入素材、选择样本、富化证据并进入蒸馏。";
  } else {
    assistantCurrentStage.textContent = "拆解工作台";
    assistantMacroStep.textContent = "4 步流程概览";
    assistantNextStep.textContent = "选择单作品解析或 Creator Clone，进入对应的现有流程。";
  }
}

function showAssistantHint(message) {
  if (!assistantHint) {
    return;
  }
  assistantHint.textContent = message;
}

aiAssistantToggle?.addEventListener("click", () => {
  const hidden = aiAssistantPanel?.classList.toggle("hidden");
  aiAssistantToggle.setAttribute("aria-expanded", hidden ? "false" : "true");
  updateAssistantContext();
});

aiAssistantClose?.addEventListener("click", () => {
  aiAssistantPanel?.classList.add("hidden");
  aiAssistantToggle?.setAttribute("aria-expanded", "false");
});

document.addEventListener("workbench:coming-soon", (event) => {
  aiAssistantPanel?.classList.remove("hidden");
  aiAssistantToggle?.setAttribute("aria-expanded", "true");
  showAssistantHint(event.detail?.message || "该模块尚未接入，本轮只保留工作台信息架构位置。");
});

assistantCopyPromptButton?.addEventListener("click", async () => {
  const text = currentDistillPrompt || (loadedHomeCase ? buildFullPrompt(loadedHomeCase) : "");
  if (!text) {
    showAssistantHint("当前还没有可复制的拆解 Prompt。请先完成单作品素材包或创作者蒸馏。");
    return;
  }
  await navigator.clipboard.writeText(text);
  showAssistantHint("已复制当前可用 Prompt。");
});

assistantStrategyPlanButton?.addEventListener("click", () => {
  setHomeRoute("profile");
  if (creatorStrategyPlanCard && !creatorStrategyPlanCard.classList.contains("hidden")) {
    creatorStrategyPlanCard.scrollIntoView({behavior: "smooth", block: "start"});
    showAssistantHint("已跳转到 Strategy Plan。");
    return;
  }
  showAssistantHint("当前还没有 Strategy Plan。请先完成创作者蒸馏后再生成下一批创作方案。");
});

window.addEventListener("hashchange", () => {
  setHomeRoute(routeFromHash(), false);
});

// Single Work
async function runSingleValue(value) {
  const observationGeneration = startSingleItemObservation();
  singleButton.disabled = true;
  singleButton.textContent = "解析中...";
  selectedCandidate = null;
  currentAwemeId = "";
  currentLocalVideoId = "";
  currentSingleJob = null;
  loadedHomeCase = null;
  homeCaseView.classList.add("hidden");
  resultCard.classList.add("hidden");
  setSingleItemFlow("received", "active");
  try {
    const importResponse = await fetch("/api/videos/import-single", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({value}),
    });
    const imported = await readJsonResponse(importResponse);
    if (!isCurrentSingleItemObservation("", observationGeneration)) {
      return;
    }
    currentAwemeId = imported.video.aweme_id;
    setSingleItemFlow("acquisition", "active");
    singleResult.classList.remove("hidden");
    singleResult.textContent = `已导入作品：${currentAwemeId}，正在解析可用清晰度...`;
    const qualitiesResolved = await resolveQualities([currentAwemeId], observationGeneration);
    if (
      qualitiesResolved
      && selectedCandidate
      && isCurrentSingleItemObservation("", observationGeneration)
    ) {
      await downloadCandidate(selectedCandidate, observationGeneration);
    }
  } catch (error) {
    if (!isCurrentSingleItemObservation("", observationGeneration)) {
      return;
    }
    singleResult.classList.remove("hidden");
    singleResult.textContent = `${singleItemFailureCategory(error, "acquisition")}。请检查作品链接或稍后重试。`;
    setSingleItemFlow(currentAwemeId ? "acquisition" : "received", "failed", error.error_code);
    singleButton.disabled = false;
    singleButton.textContent = "解析";
  } finally {
    if (
      !selectedCandidate
      && isCurrentSingleItemObservation("", observationGeneration)
    ) {
      singleButton.disabled = false;
      singleButton.textContent = "解析";
    }
  }
}

singleForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const value = new FormData(singleForm).get("value");
  await runSingleValue(value);
});

profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await scanProfile(event.submitter?.dataset.profileSource || "public");
});

profileHandoffFile?.addEventListener("change", async () => {
  await readHandoffManifestFile(profileHandoffFile.files?.[0]);
});

profileImportModeButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setActiveImportMode(button.dataset.profileImportMode || "browser");
  });
});

creatorCloneFlowSteps.forEach((button) => {
  button.addEventListener("click", async () => {
    const targetStage = normalizeProfileStage(button.dataset.profileStageNav || "import");
    if (targetStage === "import" && (currentCloneSetId || activeCreatorSampleViewItems().length || currentCreatorRuntimeState)) {
      if (lockedProfileNavigationStage()) {
        profileScanStatus.textContent = profileStageNavigationLockMessage(targetStage);
        renderCreatorCloneNextAction();
        return;
      }
      enterCreatorCloneImportView({scroll: true});
      profileScanStatus.textContent = "已切换到导入素材。当前素材池仍保留；点击“下一步：开始导入素材”后才会替换旧结果。";
      return;
    }
    if (!canNavigateProfileStage(targetStage)) {
      profileScanStatus.textContent = profileStageNavigationLockMessage(targetStage);
      renderCreatorCloneNextAction();
      return;
    }
    if (targetStage === "export") {
      await showCreatorCloneExportStage({scroll: true});
      return;
    }
    setProfileStageView(targetStage, {scroll: true});
    renderCreatorCloneNextAction();
  });
});

profileQuickInput?.addEventListener("input", () => {
  if (currentCloneSetId || activeCreatorSampleViewItems().length || currentCreatorRuntimeState) {
    setProfileStageView("import", {scroll: false});
  }
  profileQuickInputRestoredValue = "";
  renderCreatorCloneNextAction();
});

creatorCloneNextButton?.addEventListener("click", async () => {
  if (creatorCloneNextActionRunning) {
    return;
  }
  creatorCloneNextActionRunning = true;
  renderWizardPrimaryAction();
  try {
    await runCreatorCloneNextAction();
  } finally {
    creatorCloneNextActionRunning = false;
    renderCreatorCloneNextAction();
  }
});

profileBrowserHelperButton.addEventListener("click", async () => {
  await scanProfileWithLocalChrome();
});

profileSort.addEventListener("change", () => {
  if (profileScanPayload) {
    renderProfileTable();
    updateCreatorCloneSelectionStatus();
  }
});

profileEvidenceFilter?.addEventListener("change", () => {
  if (profileScanPayload) {
    renderProfileTable();
    updateCreatorCloneSelectionStatus();
  }
});

profileMediaFilter?.addEventListener("change", () => {
  if (profileScanPayload) {
    renderProfileTable();
    updateCreatorCloneSelectionStatus();
  }
});

profileResultsBody.addEventListener("change", (event) => {
  if (event.target.matches("[data-profile-select]")) {
    if (event.target.checked) {
      profileSelectedKeys.add(event.target.value);
    } else {
      profileSelectedKeys.delete(event.target.value);
    }
    invalidateCreatorRuntimeReportForSelectionChange();
    updateCreatorCloneSelectionStatus();
    scheduleCreatorCloneSelectionSync();
  }
});

profileResultsBody.addEventListener("click", (event) => {
  const button = event.target.closest("[data-profile-select-action]");
  if (!button) {
    return;
  }
  const key = button.dataset.profileSelectAction || "";
  if (!key) {
    return;
  }
  profileSelectedKeys.add(key);
  invalidateCreatorRuntimeReportForSelectionChange();
  document.querySelectorAll("[data-profile-select]").forEach((input) => {
    if (input.value === key) {
      input.checked = true;
    }
  });
  updateCreatorCloneSelectionStatus();
  scheduleCreatorCloneSelectionSync();
  profileScanStatus.textContent = "已选入本轮样本。";
});

profileSelectAllButton.addEventListener("click", () => {
  const items = visibleCreatorSampleViewItems();
  setProfileSelection(items);
  profileScanStatus.textContent = `已全选当前列表：${items.length} 条。蒸馏最多支持 ${CREATOR_CLONE_MAX_DISTILL_SAMPLES} 条。`;
});

profileClearSelectionButton.addEventListener("click", () => {
  setProfileSelection([]);
  if (profilePresetKind) {
    profilePresetKind.value = "";
  }
  profileScanStatus.textContent = "已取消选择。";
});

function applyProfilePresetSelectValue() {
  const preset = profilePresetKind?.value || "";
  if (!preset) {
    return;
  }
  applyProfilePresetSelection(preset);
}

profilePresetKind?.addEventListener("change", applyProfilePresetSelectValue);

creatorCloneRecommendation?.addEventListener("click", async (event) => {
  const target = event.target instanceof Element ? event.target : event.target?.parentElement;
  const action = target?.closest("[data-representative-action]")?.dataset.representativeAction || "";
  if (action === "apply") {
    applyRepresentativeSampleSelection();
  } else if (action === "refresh") {
    await refreshRepresentativeSampleRecommendations();
  }
});

profileDecisionBoard?.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target : event.target?.parentElement;
  const stageButton = target?.closest("[data-profile-stage-go]");
  if (stageButton) {
    setProfileStageView(stageButton.dataset.profileStageGo || "select", {scroll: true});
  }
});

profileContinueChromeButton?.addEventListener("click", async () => {
  await scanProfileWithLocalChrome({continueScan: true});
});

profileSelectedBuildButton.addEventListener("click", async () => {
  await buildSelectedProfileQueue();
});

creatorCloneDistillButton.addEventListener("click", async () => {
  await distillSelectedCreatorClone();
});

creatorCloneBatchDistillButton?.addEventListener("click", async () => {
  await batchDistillSelectedCreatorClone();
});

generateCreatorStrategyButton?.addEventListener("click", async () => {
  await generateCreatorStrategyPlan();
});

copyCreatorCloneSpecButton.addEventListener("click", async () => {
  const strategy = creatorStrategyFromResult(currentCreatorRuntimeReport || {}) || null;
  const payload = strategy || currentCreatorRuntimeReport?.creator_clone_spec || null;
  if (!payload) {
    return;
  }
  await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
  copyCreatorCloneSpecButton.textContent = "已复制";
  window.setTimeout(() => {
    copyCreatorCloneSpecButton.textContent = "复制 Creator Clone Spec";
  }, 1600);
});

copyDistillPromptButton.addEventListener("click", async () => {
  if (!currentDistillPrompt) {
    return;
  }
  await navigator.clipboard.writeText(currentDistillPrompt);
  copyDistillPromptButton.textContent = "已复制";
  window.setTimeout(() => {
    copyDistillPromptButton.textContent = "复制蒸馏 Prompt";
  }, 1600);
});

async function resolveQualities(awemeIds, observationGeneration = null) {
  const response = await fetch("/api/videos/qualities", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({aweme_ids: awemeIds}),
  });
  const payload = await readJsonResponse(response);
  if (
    Number.isInteger(observationGeneration)
    && !isCurrentSingleItemObservation("", observationGeneration)
  ) {
    return false;
  }
  const candidates = payload.results[currentAwemeId] || [];
  if (!candidates.length) {
    singleResult.textContent = "没有解析到可用清晰度候选。";
    setSingleItemFlow("acquisition", "failed", "QUALITY_NO_CANDIDATE");
    return false;
  }
  selectedCandidate = chooseCandidate(candidates);
  const sizeMb = selectedCandidate.size_bytes
    ? (selectedCandidate.size_bytes / 1024 / 1024).toFixed(2)
    : "未知";
  const bitrate = selectedCandidate.bitrate
    ? `${Math.round(selectedCandidate.bitrate / 1000)} kbps`
    : "未知码率";
  singleResult.textContent = `已按设置选择：${selectedCandidate.quality_label || "网页候选"} · ${sizeMb} MB · ${bitrate}`;
  setSingleItemFlow("acquisition", "active");
  return true;
}

function chooseCandidate(candidates) {
  const preference = qualityPreference?.value || "1080";
  if (preference === "1080") {
    return candidates.find((candidate) => String(candidate.quality_label || "").includes("1080")) || candidates[0];
  }
  if (preference === "720") {
    return candidates.find((candidate) => String(candidate.quality_label || "").includes("720")) || candidates[0];
  }
  return candidates[0];
}

async function downloadCandidate(
  candidate,
  observationGeneration = singleItemObservationGeneration,
) {
  if (!isCurrentSingleItemObservation("", observationGeneration)) {
    return;
  }
  let inlineCaseShown = false;
  let observationJobId = "";
  setHomeRoute("single");
  placeJobCard("single");
  setSingleItemFlow("acquisition", "active");
  resetJobCard("创建下载和素材包任务...");
  caseSummary.innerHTML = "";
  resultCard.classList.add("hidden");
  buildCaseButton.hidden = true;
  try {
    const response = await fetch("/api/jobs/download-build-analyze-case", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({aweme_id: currentAwemeId, candidate_id: candidate.candidate_id}),
    });
    const payload = await readJsonResponse(response);
    if (!bindSingleItemObservation(payload.job_id, observationGeneration)) {
      return;
    }
    observationJobId = payload.job_id;
    const renderIntermediateCase = async (job, {scroll = false} = {}) => {
      const result = job.result_json || {};
      const caseId = getCaseId(result);
      if (!caseId || inlineCaseShown) {
        return;
      }
      currentLocalVideoId = result.local_video_id || currentLocalVideoId;
      resultCard.classList.remove("hidden");
      buildCaseButton.hidden = true;
      renderWorkflowResult(result);
      try {
        const analysisShown = await showAnalysisInline(result, {
          scroll,
          updateMessage: false,
          jobId: payload.job_id,
          observationGeneration,
        });
        if (!isCurrentSingleItemObservation(payload.job_id, observationGeneration)) {
          return;
        }
        inlineCaseShown = analysisShown;
      } catch (error) {
        if (!isCurrentSingleItemObservation(payload.job_id, observationGeneration)) {
          return;
        }
        homeAiStatus.textContent = `${singleItemFailureCategory(error, "case")}。本地拆解视图暂时无法加载，任务仍在继续。`;
      }
    };
    return pollJob(payload.job_id, async (job) => {
      if (job.status === "success" && job.result_json.local_video_id) {
        currentLocalVideoId = job.result_json.local_video_id;
        resultCard.classList.remove("hidden");
        buildCaseButton.hidden = true;
        renderWorkflowResult(job.result_json);
        if (await showAnalysisInline(job.result_json, {
          scroll: !inlineCaseShown,
          updateMessage: false,
          jobId: payload.job_id,
          observationGeneration,
        })) {
          jobMessage.textContent = "success · 100% · 任务处理完成";
          return;
        }
      }
    }, async (job) => {
      await renderIntermediateCase(job, {scroll: true});
    }, observationGeneration);
  } catch (error) {
    if (!isCurrentSingleItemObservation(observationJobId, observationGeneration)) {
      return;
    }
    jobMessage.className = "job-message failed";
    jobMessage.textContent = singleItemFailureCategory(error, "acquisition");
    setSingleItemFlow("acquisition", "failed", error.error_code);
    singleButton.disabled = false;
    singleButton.textContent = "解析";
  }
}

buildCaseButton.addEventListener("click", async () => {
  if (!currentLocalVideoId) {
    return;
  }
  buildCaseButton.disabled = true;
  placeJobCard("single");
  setSingleItemFlow("acquisition", "active");
  resetJobCard("创建任务...");
  const observationGeneration = startSingleItemObservation();
  let observationJobId = "";
  try {
    const response = await fetch("/api/jobs/build-case", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({local_video_id: currentLocalVideoId}),
    });
    const payload = await readJsonResponse(response);
    if (!bindSingleItemObservation(payload.job_id, observationGeneration)) {
      return;
    }
    observationJobId = payload.job_id;
    pollJob(payload.job_id, null, null, observationGeneration);
  } catch (error) {
    if (!isCurrentSingleItemObservation(observationJobId, observationGeneration)) {
      return;
    }
    jobMessage.className = "job-message failed";
    jobMessage.textContent = singleItemFailureCategory(error, "case");
    setSingleItemFlow("acquisition", "failed", error.error_code);
    buildCaseButton.disabled = false;
  }
});

async function pollJob(
  jobId,
  onSuccess,
  onProgress,
  observationGeneration = singleItemObservationGeneration,
) {
  if (!isCurrentSingleItemObservation(jobId, observationGeneration)) {
    return;
  }
  try {
    const response = await fetch(`/api/jobs/${jobId}`, {cache: "no-store"});
    const payload = await readJsonResponse(response);
    if (!isCurrentSingleItemObservation(jobId, observationGeneration)) {
      return;
    }
    const job = payload.job;
    if (renderJobStatus(job) === false) {
      return;
    }
    if (job.status === "success") {
      renderJobStatus(job);
      if (onSuccess) {
        await onSuccess(job);
      } else if (jobResult) {
        showJson(jobResult, job.result_json);
      }
      if (!isCurrentSingleItemObservation(jobId, observationGeneration)) {
        return;
      }
      buildCaseButton.disabled = false;
      singleButton.disabled = false;
      singleButton.textContent = "解析";
      return;
    }
    if (job.status === "failed") {
      jobMessage.className = "job-message failed";
      jobMessage.textContent = singleItemFailureCategory(job, "");
      if (jobResult) {
        showJson(jobResult, {
          status: "failed",
          progress: Number(job.progress || 0),
          error_category: singleItemFailureCategory(job, ""),
        });
      }
      buildCaseButton.disabled = false;
      singleButton.disabled = false;
      singleButton.textContent = "解析";
      return;
    }
    if (["pending", "running"].includes(job.status) && profileBuildJobAgeSeconds(job) >= WORKBENCH_TASK_STALE_SECONDS) {
      currentSingleJob = {...job, status: "stale"};
      renderSingleItemStatus();
      jobMessage.className = "job-message";
      jobMessage.textContent = `stale · ${job.progress || 0}% · ${singleItemJobMessage(currentSingleJob)}`;
      buildCaseButton.disabled = false;
      singleButton.disabled = false;
      singleButton.textContent = "解析";
      return;
    }
    if (onProgress) {
      await onProgress(job);
    }
    if (!isCurrentSingleItemObservation(jobId, observationGeneration)) {
      return;
    }
    await new Promise((resolve) => {
      window.setTimeout(resolve, 700);
    });
    return pollJob(jobId, onSuccess, onProgress, observationGeneration);
  } catch (error) {
    if (!isCurrentSingleItemObservation(jobId, observationGeneration)) {
      return;
    }
    const terminalStatusKnown = ["success", "failed"].includes(currentSingleJob?.status);
    if (!terminalStatusKnown) {
      currentSingleJob = {...(currentSingleJob || {}), status: "stale"};
      renderSingleItemStatus();
    }
    jobMessage.className = "job-message failed";
    jobMessage.textContent = terminalStatusKnown
      ? "任务已结束，但结果视图暂时无法加载。请稍后重新进入工作台查看。"
      : "任务状态暂时无法确认，请稍后重新进入工作台查看。";
    buildCaseButton.disabled = false;
    singleButton.disabled = false;
    singleButton.textContent = "解析";
  }
}

copyHomePromptButton.addEventListener("click", async () => {
  if (!loadedHomeCase) {
    return;
  }
  await navigator.clipboard.writeText(buildFullPrompt(loadedHomeCase));
  copyHomePromptButton.textContent = "已复制";
  window.setTimeout(() => {
    copyHomePromptButton.textContent = "复制 Prompt";
  }, 1600);
});

downloadHomeAnalysisInputButton.addEventListener("click", () => {
  const url = loadedHomeCase?.artifact_urls?.analysis_input;
  if (url) {
    window.open(url, "_blank", "noopener,noreferrer");
  }
});

window.addEventListener("beforeunload", (event) => {
  if (!creatorCloneEnrichmentRunning && !creatorCloneDistillRunning && !creatorCloneNextActionRunning) {
    return;
  }
  event.preventDefault();
  event.returnValue = "";
});

const settingsPanelController = window.SettingsPanel?.init({
  elements: {
    toggle: settingsToggle,
    modal: settingsModal,
    close: settingsClose,
    llmStatusBadge,
    llmStatusList,
    llmConfigHint,
    llmForm: llmSettingsForm,
    llmProviderInput,
    llmApiBaseInput,
    llmModelInput,
    llmApiKeyInput,
    llmTimeoutInput,
    llmCreatorDistillTimeoutInput,
    llmFinalReduceTimeoutInput,
    llmQuickDistillBudgetInput,
    llmDeepDistillBudgetInput,
    llmBatchJobBudgetInput,
    llmFinalReduceReserveInput,
    llmCompactRetryMinInput,
    llmTemperatureInput,
    llmClearKeyInput,
    saveLlmButton: saveLlmSettingsButton,
    llmSaveResult,
    testLlmButton,
    llmTestResult,
    dataSourceStatusBadge,
    dataSourceStatusList,
    loginStateStatusBadge,
    loginStateStatusList,
    startLoginStatePairButton,
    refreshLoginStateButton,
    loginStatePairResult,
    douyinForm: douyinSettingsForm,
    douyinCookieInput,
    douyinUserAgentInput,
    douyinRefererInput,
    douyinClearCookieInput,
    saveDouyinButton: saveDouyinSettingsButton,
    douyinSaveResult,
    testDouyinButton: testDouyinCookieButton,
    douyinCookieTestResult,
    refreshPreflightButton,
    preflightSummary,
    preflightList,
  },
  requestJson: async (url, options = {}) => readJsonResponse(await fetch(url, options)),
  callbacks: {
    refreshPreflight: loadPreflightStatus,
    onPreflightFailure: markWorkbenchPreflightFailed,
    onLlmStatus: renderWorkbenchLlmStatus,
    onLlmLoadFailure: () => setWorkbenchStatus("llm", "LLM 读取失败", "missing"),
    getDouyinTestPayload: () => {
      const profileValue = creatorCloneCurrentProfileValue();
      if (/^MS4w[A-Za-z0-9_.-]+$/.test(profileValue)) {
        return {count: 5, sec_user_id: profileValue};
      }
      return {count: 5, profile_url: firstUrlFromText(profileValue) || profileValue};
    },
    copyPreflightSnippet: (index) => {
      const snippet = Number.isInteger(index) ? preflightCopySnippets[index] : "";
      return copyTextToClipboard(snippet);
    },
  },
}) || null;

settingsPanelController?.loadLlmStatus();
settingsPanelController?.loadDataSourceStatus();
settingsPanelController?.loadLoginStateStatus();
loadPreflightStatus().catch(() => {
  markWorkbenchPreflightFailed();
});
renderCreatorCloneNextAction();
setHomeRoute(routeFromHash(), !window.location.hash);
window.setTimeout(restoreLibraryResumeTarget, 0);
