from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


APP_JS = Path("app/static/app.js")
INDEX_TEMPLATE = Path("app/templates/index.html")
BEGIN_MARKER = "// BEGIN SINGLE_ITEM_JOB_STATUS"
END_MARKER = "// END SINGLE_ITEM_JOB_STATUS"
ALLOWED_STATES = {"pending", "active", "completed", "partial", "failed"}
EXPECTED_STAGE_LABELS = ["已接收", "获取素材", "生成分析", "完成"]

NODE_CANDIDATES = [
    shutil.which("node"),
    Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node",
]
NODE_BINARY = next(
    (
        Path(value)
        for value in NODE_CANDIDATES
        if value and Path(value).is_file()
    ),
    None,
)


def _module_source() -> str:
    source = APP_JS.read_text(encoding="utf-8")
    assert source.count(BEGIN_MARKER) == 1
    assert source.count(END_MARKER) == 1
    before, remainder = source.split(BEGIN_MARKER, 1)
    module_source, _after = remainder.split(END_MARKER, 1)
    assert before or module_source
    return module_source


def _source_between(source: str, start: str, end: str) -> str:
    assert source.count(start) >= 1, start
    remainder = source.split(start, 1)[1]
    assert end in remainder, end
    return start + remainder.split(end, 1)[0]


def _single_item_status_template() -> str:
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")
    match = re.search(
        r'<section\b[^>]*\bid="single-item-status-card"[^>]*>.*?</section>',
        template,
        flags=re.DOTALL,
    )
    assert match is not None
    return match.group(0)


def _run_node(script: str) -> dict:
    assert NODE_BINARY is not None
    completed = subprocess.run(
        [str(NODE_BINARY), "-e", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return json.loads(completed.stdout)


@pytest.fixture(scope="module")
def status_module_result() -> dict:
    if NODE_BINARY is None:
        pytest.skip("Node.js is unavailable")

    script = "const source = " + json.dumps(_module_source()) + ";\n" + r"""
const vm = require("vm");
const context = {console: {error() {}, warn() {}, log() {}}};
context.window = context;
context.globalThis = context;
const before = Object.keys(context);
vm.runInNewContext(source, context, {filename: "app.js#SingleItemJobStatus"});
const api = context.SingleItemJobStatus;
const added = Object.keys(context).filter((key) => !before.includes(key));

function snapshot(input) {
  const beforeInput = JSON.stringify(input);
  const viewModel = api.derive(input);
  const markup = api.renderMarkup(viewModel);
  return {
    viewModel,
    markup,
    inputUnchanged: JSON.stringify(input) === beforeInput,
  };
}

const idle = snapshot({job: null, caseData: null, flow: null});
const firstActive = snapshot({
  job: null,
  caseData: null,
  flow: {stage: "received", status: "active"},
});
const acquisitionFlowFailure = snapshot({
  job: null,
  caseData: null,
  flow: {
    stage: "acquisition",
    status: "failed",
    error_code: "QUALITY_NO_CANDIDATE",
  },
});
const middleActive = snapshot({
  job: {status: "running", progress: 28, result_json: {}},
  caseData: null,
  flow: {stage: "acquisition", status: "active"},
});
const runningWithDownload = snapshot({
  job: {
    status: "running",
    progress: 65,
    result_json: {
      download: {local_video_id: 31},
      local_video_id: 31,
      analysis_status: "pending",
    },
  },
  caseData: null,
  flow: null,
});
const localVideoOnlyFailure = snapshot({
  job: {
    status: "failed",
    progress: 66,
    error_code: "AUTO_ANALYSIS_FAILED",
    result_json: {local_video_id: 32},
  },
  caseData: null,
  flow: null,
});
const success = snapshot({
  job: {
    status: "success",
    progress: 100,
    result_json: {
      download: {status: "success"},
      local_video_id: 21,
      case_id: 34,
      case: {case_id: 34},
      analysis_status: "success",
    },
  },
  caseData: {
    case_id: 34,
    primary_workflow: {artifact_ready: true, analysis_status: "completed"},
  },
  flow: {stage: "complete", status: "completed"},
});
const partial = snapshot({
  job: {
    status: "success",
    progress: 100,
    result_json: {
      download: {status: "success"},
      local_video_id: 21,
      case_id: 34,
      case: {case_id: 34},
      analysis_status: "failed",
      analysis_error: {error_code: "LLM_REQUEST_FAILED"},
    },
  },
  caseData: {
    case_id: 34,
    primary_workflow: {artifact_ready: true, analysis_status: "not_analyzed"},
  },
  flow: {stage: "complete", status: "partial"},
});
const completeFailure = snapshot({
  job: {
    status: "failed",
    progress: 19,
    error_code: "DOWNLOAD_FAILED",
    result_json: {},
  },
  caseData: null,
  flow: {stage: "acquisition", status: "failed"},
});
const unknown = snapshot({
  job: {status: "future_job_state", progress: 100, result_json: {}},
  caseData: null,
  flow: {stage: "future_stage", status: "future_status"},
});
const missingJob = snapshot({
  job: null,
  caseData: {
    case_id: 55,
    primary_workflow: {artifact_ready: true, analysis_status: "completed"},
  },
  flow: {stage: "complete", status: "completed"},
});
const missingCase = snapshot({
  job: {
    status: "success",
    progress: 100,
    result_json: {
      download: {status: "success"},
      local_video_id: 89,
      case_id: 144,
      analysis_status: "success",
    },
  },
  caseData: null,
  flow: {stage: "complete", status: "completed"},
});
const missingError = snapshot({
  job: {status: "failed", progress: 40, result_json: {}},
  caseData: null,
  flow: {stage: "acquisition", status: "failed"},
});
const multipleFailures = snapshot({
  job: {
    status: "success",
    progress: 100,
    result_json: {
      download: {status: "success"},
      local_video_id: 233,
      case_id: 377,
      analysis_status: "failed",
      analysis_error: {error_code: "LLM_REQUEST_FAILED"},
    },
  },
  caseData: {
    case_id: 377,
    primary_workflow: {artifact_ready: true, analysis_status: "not_analyzed"},
    enrichment: {manifest: {statuses: {asr: "failed", ocr: "failed"}}},
  },
  flow: {
    stage: "complete",
    status: "partial",
  },
});
const groupedMissingArtifacts = snapshot({
  job: {
    status: "success",
    progress: 100,
    available_results: ["已保留素材包输入"],
    result_json: {case_id: 1597, analysis_status: "pending"},
  },
  caseData: {
    case_id: 1597,
    analysis_result: {summary: "已保留的分析结果"},
    primary_workflow: {
      artifact_ready: false,
      analysis_status: "artifact_incomplete",
      missing_artifacts: ["prompt", "contact_sheet", "keyframes_dir"],
    },
  },
  flow: {stage: "complete", status: "partial"},
});
const duplicateMaterialSignals = snapshot({
  job: {
    status: "recoverable",
    progress: 91,
    available_results: ["已保留输入"],
    result_json: {case_id: 9871, analysis_status: "pending"},
  },
  caseData: {
    case_id: 9871,
    status: "failed",
    analysis_result: {summary: "已保留的分析结果"},
    primary_workflow: {
      artifact_ready: false,
      analysis_status: "artifact_incomplete",
      missing_artifacts: ["metadata", "contact_sheet", "keyframes_dir"],
    },
    enrichment: {manifest: {statuses: {asr: "failed", ocr: "failed"}}},
  },
  flow: {stage: "complete", status: "partial"},
});
const staleCaseArtifactSuccess = snapshot({
  job: {
    status: "success",
    progress: 100,
    result_json: {
      download: {local_video_id: 2584},
      local_video_id: 2584,
      case_id: 4181,
      case: {case_id: 4181, local_video_id: 2584},
      analysis_status: "pending",
    },
  },
  caseData: {
    case_id: 4181,
    primary_workflow: {
      artifact_ready: false,
      analysis_status: "artifact_incomplete",
      missing_artifacts: ["analysis_input"],
    },
  },
  flow: null,
});

function staleAnalysisConflict(workflowStatus) {
  const artifactReady = workflowStatus !== "artifact_incomplete";
  return snapshot({
    job: {
      status: "success",
      progress: 100,
      result_json: {
        download: {local_video_id: 6765},
        local_video_id: 6765,
        case_id: 10946,
        case: {case_id: 10946, local_video_id: 6765},
        analysis_status: "success",
        analysis: {},
      },
    },
    caseData: {
      case_id: 10946,
      primary_workflow: {
        artifact_ready: artifactReady,
        analysis_status: workflowStatus,
        missing_artifacts: artifactReady ? [] : ["analysis_input"],
      },
    },
    flow: null,
  });
}

const analysisConflicts = {
  notAnalyzed: staleAnalysisConflict("not_analyzed"),
  notConfigured: staleAnalysisConflict("not_configured"),
  artifactIncomplete: staleAnalysisConflict("artifact_incomplete"),
};
const actualAnalysisEvidence = {
  jobPayload: snapshot({
    job: {
      status: "success",
      progress: 100,
      result_json: {
        download: {local_video_id: 17711},
        local_video_id: 17711,
        case_id: 28657,
        case: {case_id: 28657, local_video_id: 17711},
        analysis_status: "success",
        analysis: {analysis_result: {summary: "已持久化报告"}},
      },
    },
    caseData: {
      case_id: 28657,
      primary_workflow: {artifact_ready: true, analysis_status: "not_analyzed"},
    },
    flow: null,
  }),
  casePayload: snapshot({
    job: {
      status: "success",
      progress: 100,
      result_json: {
        download: {local_video_id: 46368},
        local_video_id: 46368,
        case_id: 75025,
        case: {case_id: 75025, local_video_id: 46368},
        analysis_status: "success",
        analysis: {},
      },
    },
    caseData: {
      case_id: 75025,
      analysis_result: {summary: "Case 已加载报告"},
      primary_workflow: {artifact_ready: true, analysis_status: "not_configured"},
    },
    flow: null,
  }),
};

const secret = "Authorization: Bearer eyJhbGciOi-super-secret; Cookie=sessionid-private; token=raw-token; /Users/alice/private.mp4";
const sensitive = snapshot({
  job: {
    status: "success",
    progress: 100,
    message: secret,
    result_json: {
      download: {status: "success", path: "/Users/alice/private.mp4"},
      local_video_id: 610,
      case_id: 987,
      analysis_status: "failed",
      analysis_error: {
        error_code: "LLM_REQUEST_FAILED",
        message: secret,
        source: secret,
      },
    },
  },
  caseData: {primary_workflow: {artifact_ready: true, analysis_status: "not_analyzed"}},
  flow: {stage: "complete", status: "partial"},
});

const categoryCases = {
  download: api.failureCategory("DOWNLOAD_FAILED", "download"),
  caseBuild: api.failureCategory("CASE_BUILD_FAILED", "case"),
  analysis: api.failureCategory("LLM_REQUEST_FAILED", "analysis"),
  asr: api.failureCategory("ASR_FAILED", "asr"),
  ocr: api.failureCategory("OCR_FAILED", "ocr"),
  enrichment: api.failureCategory("ENRICHMENT_FAILED", "enrichment"),
  unknown: api.failureCategory("FUTURE_PRIVATE_ERROR", "future"),
  secretSource: api.failureCategory("LLM_REQUEST_FAILED", secret),
};

process.stdout.write(JSON.stringify({
  added,
  namespaceFrozen: Object.isFrozen(api),
  api: Object.keys(api).sort(),
  scenarios: {
    idle,
    firstActive,
    acquisitionFlowFailure,
    middleActive,
    runningWithDownload,
    localVideoOnlyFailure,
    success,
    partial,
    completeFailure,
    unknown,
    missingJob,
    missingCase,
    missingError,
    multipleFailures,
    groupedMissingArtifacts,
    duplicateMaterialSignals,
    staleCaseArtifactSuccess,
    sensitive,
  },
  analysisConflicts,
  actualAnalysisEvidence,
  categoryCases,
}));
"""
    return _run_node(script)


@pytest.fixture(scope="module")
def semantic_edge_result() -> dict:
    if NODE_BINARY is None:
        pytest.skip("Node.js is unavailable")

    script = "const source = " + json.dumps(_module_source()) + ";\n" + r"""
const vm = require("vm");
const context = {console: {error() {}, warn() {}, log() {}}};
context.window = context;
context.globalThis = context;
vm.runInNewContext(source, context, {filename: "app.js#SingleItemJobStatus"});
const api = context.SingleItemJobStatus;

function snapshot(input) {
  return {viewModel: api.derive(input)};
}

function completedCase(statuses = {}) {
  return {
    case_id: "case_current",
    analysis_result: {summary: "已持久化报告"},
    primary_workflow: {artifact_ready: true, analysis_status: "completed"},
    enrichment: {manifest: {statuses}},
  };
}

function announcement(input) {
  const element = {textContent: ""};
  api.render(api.derive(input), {announcement: element});
  return element.textContent;
}

const neutralOptional = {};
for (const status of [
  "", "pending", "missing", "disabled", "not_configured", "skipped", "not_required",
  "no_speech", "no_text",
]) {
  neutralOptional[status || "blank"] = snapshot({
    caseData: completedCase({
      asr: status,
      ocr: status,
      comments: status,
      metrics: status,
      index: status,
    }),
  });
}

const explicitOptionalFailure = {
  failed: snapshot({caseData: completedCase({asr: "failed"})}),
  providerMissing: snapshot({caseData: completedCase({ocr: "provider_missing"})}),
};

const mismatchedCase = snapshot({
  job: {
    id: "job_new",
    status: "success",
    type: "download-build-analyze-case",
    result_json: {
      case_id: "case_new",
      case: {case_id: "case_new", local_video_id: "local_new"},
      local_video_id: "local_new",
      analysis_status: "failed",
      analysis_error: {error_code: "LLM_REQUEST_FAILED"},
    },
  },
  caseData: {
    case_id: "case_old",
    analysis_result: {summary: "旧任务报告"},
    primary_workflow: {artifact_ready: true, analysis_status: "completed"},
  },
});

const workbenchRunningJob = {
  id: "job_sequence",
  task_id: "job_sequence",
  type: "download-build-analyze-case",
  task_type: "download-build-analyze-case",
  status: "running",
  result_json: {
    case_id: "case_sequence",
    case: {case_id: "case_sequence"},
    download: {local_video_id: "local_sequence"},
    analysis_status: "pending",
  },
};
const staleCase = {
  case_id: "case_sequence",
  primary_workflow: {artifact_ready: true, analysis_status: "not_analyzed"},
};
const safeTerminalSuccess = {
  ...workbenchRunningJob,
  status: "success",
  progress: 100,
  result_json: {...workbenchRunningJob.result_json, analysis_status: "success"},
};
const safeTerminalFailure = {
  ...workbenchRunningJob,
  status: "success",
  progress: 100,
  result_json: {
    ...workbenchRunningJob.result_json,
    analysis_status: "failed",
    analysis_error: {error_code: "LLM_REQUEST_FAILED"},
  },
};
const refreshedCase = {
  case_id: "case_sequence",
  analysis_result: {summary: "刷新后的报告"},
  primary_workflow: {artifact_ready: true, analysis_status: "completed"},
};
const sequence = {
  running: snapshot({job: workbenchRunningJob, caseData: staleCase}),
  successBeforeCaseRefresh: snapshot({job: safeTerminalSuccess, caseData: null}),
  successAfterCaseRefresh: snapshot({job: safeTerminalSuccess, caseData: refreshedCase}),
  failureBeforeCaseRefresh: snapshot({job: safeTerminalFailure, caseData: null}),
  failureAfterCaseRefresh: snapshot({job: safeTerminalFailure, caseData: staleCase}),
};

const caseOnlyWorkbenchRunning = {
  ...workbenchRunningJob,
  id: "job_case_only",
  task_id: "job_case_only",
  result_json: {
    case_id: "case_only",
    case: {case_id: "case_only"},
    analysis_status: "pending",
  },
};
const caseOnlySequence = {
  running: snapshot({job: caseOnlyWorkbenchRunning, caseData: null}),
  successBeforeCaseRefresh: snapshot({
    job: {
      ...caseOnlyWorkbenchRunning,
      status: "success",
      result_json: {...caseOnlyWorkbenchRunning.result_json, analysis_status: "success"},
    },
    caseData: null,
  }),
  successAfterCaseRefresh: snapshot({
    job: {
      ...caseOnlyWorkbenchRunning,
      status: "success",
      result_json: {...caseOnlyWorkbenchRunning.result_json, analysis_status: "success"},
    },
    caseData: {
      case_id: "case_only",
      analysis_result: {summary: "Case-only 任务报告"},
      primary_workflow: {artifact_ready: true, analysis_status: "completed"},
    },
  }),
};
const rawCombinedSuccess = {
  id: "job_raw_sequence",
  type: "download-build-analyze-case",
  status: "success",
  progress: 100,
  __singleItemCaseVerificationPending: true,
  result_json: {
    case_id: "case_raw_sequence",
    case: {case_id: "case_raw_sequence", local_video_id: "local_raw_sequence"},
    local_video_id: "local_raw_sequence",
    analysis_status: "success",
    analysis: {analysis_result: {summary: "Job 中的真实报告"}},
  },
};
const rawSequence = {
  terminalBeforeCaseRefresh: snapshot({job: rawCombinedSuccess, caseData: null}),
  terminalAfterIncompleteCase: snapshot({
    job: rawCombinedSuccess,
    caseData: {
      case_id: "case_raw_sequence",
      primary_workflow: {
        artifact_ready: false,
        analysis_status: "artifact_incomplete",
        missing_artifacts: ["analysis_input"],
      },
    },
  }),
  terminalAfterCompleteCase: snapshot({
    job: rawCombinedSuccess,
    caseData: {
      case_id: "case_raw_sequence",
      analysis_result: {summary: "Case 中的真实报告"},
      primary_workflow: {artifact_ready: true, analysis_status: "completed"},
    },
  }),
};
const announcements = {
  acquisition: announcement({job: {status: "running", result_json: {}}}),
  analysis: announcement({job: workbenchRunningJob, caseData: staleCase}),
  partial: announcement({caseData: completedCase({asr: "failed"})}),
};

const transientArtifact = {
  running: snapshot({
    job: workbenchRunningJob,
    caseData: {
      case_id: "case_sequence",
      status: "missing",
      primary_workflow: {
        artifact_ready: false,
        analysis_status: "artifact_incomplete",
        missing_artifacts: ["analysis_input"],
      },
    },
  }),
  stale: snapshot({
    job: {...workbenchRunningJob, status: "stale"},
    caseData: staleCase,
  }),
};

const rawTopLevelAnalysis = snapshot({
  job: {
    id: "job_analyze",
    type: "analyze-case",
    status: "success",
    result_json: {
      case_id: "case_analyze",
      analysis_result: {summary: "顶层真实结果"},
      analysis_report: "报告",
    },
  },
  caseData: {
    case_id: "case_analyze",
    primary_workflow: {artifact_ready: true, analysis_status: "not_analyzed"},
  },
});

const legacy = {
  workbenchBlankError: snapshot({
    job: {id: "job_legacy", task_id: "job_legacy", status: "failed", result_json: {}},
  }),
  workbenchFutureError: snapshot({
    job: {
      id: "job_future",
      task_id: "job_future",
      status: "failed",
      error_code: "FUTURE_PRIVATE_ERROR",
      result_json: {},
    },
  }),
  rawFailedWithoutError: snapshot({
    job: {id: "job_raw", status: "failed", result_json: {}},
  }),
  unverifiedAvailableHint: snapshot({
    job: {
      id: "job_hint",
      task_id: "job_hint",
      status: "recoverable",
      available_results: ["Case 素材包"],
      result_json: {},
    },
  }),
  flowOnlyComplete: snapshot({
    flow: {stage: "complete", status: "completed"},
  }),
};

process.stdout.write(JSON.stringify({
  neutralOptional,
  explicitOptionalFailure,
  announcements,
  mismatchedCase,
  sequence,
  caseOnlySequence,
  rawSequence,
  transientArtifact,
  rawTopLevelAnalysis,
  legacy,
}));
"""
    return _run_node(script)


def _states(scenario: dict) -> list[str]:
    return [stage["state"] for stage in scenario["viewModel"]["stages"]]


def _labels(scenario: dict) -> list[str]:
    return [stage["label"] for stage in scenario["viewModel"]["stages"]]


def test_namespace_is_frozen_and_exposes_the_three_pure_helpers(
    status_module_result: dict,
) -> None:
    assert status_module_result["added"] == ["SingleItemJobStatus"]
    assert status_module_result["namespaceFrozen"] is True
    assert {"derive", "failureCategory", "renderMarkup"} <= set(
        status_module_result["api"]
    )
    assert all(
        scenario["inputUnchanged"]
        for scenario in status_module_result["scenarios"].values()
    )


def test_idle_has_four_pending_stages(status_module_result: dict) -> None:
    idle = status_module_result["scenarios"]["idle"]
    assert _labels(idle) == EXPECTED_STAGE_LABELS
    assert _states(idle) == ["pending", "pending", "pending", "pending"]


def test_first_and_middle_active_states_are_unambiguous(
    status_module_result: dict,
) -> None:
    first = status_module_result["scenarios"]["firstActive"]
    middle = status_module_result["scenarios"]["middleActive"]
    assert _states(first) == ["active", "pending", "pending", "pending"]
    assert _states(middle) == ["completed", "active", "pending", "pending"]
    assert first["markup"].count("进行中") >= 1
    assert middle["markup"].count("进行中") >= 1


def test_acquisition_flow_failure_preserves_received_and_fails_completion(
    status_module_result: dict,
) -> None:
    failed = status_module_result["scenarios"]["acquisitionFlowFailure"]
    assert _states(failed) == ["completed", "failed", "pending", "failed"]
    assert failed["viewModel"]["completeFailure"] is True
    assert failed["viewModel"]["hasUsableResult"] is False
    assert failed["viewModel"]["failureCategory"] == "素材获取未完成"


def test_running_job_with_download_moves_into_analysis_without_claiming_a_result(
    status_module_result: dict,
) -> None:
    running = status_module_result["scenarios"]["runningWithDownload"]
    assert _states(running) == ["completed", "completed", "active", "pending"]
    assert running["viewModel"]["hasUsableResult"] is False
    assert running["viewModel"]["partialSummary"] is None
    assert running["viewModel"]["completeFailure"] is False


def test_local_video_id_only_advances_stages_and_does_not_mask_total_failure(
    status_module_result: dict,
) -> None:
    failed = status_module_result["scenarios"]["localVideoOnlyFailure"]
    assert _states(failed) == ["completed", "completed", "failed", "failed"]
    assert failed["viewModel"]["hasUsableResult"] is False
    assert failed["viewModel"]["partialSummary"] is None
    assert failed["viewModel"]["completeFailure"] is True


def test_all_success_marks_every_stage_completed(status_module_result: dict) -> None:
    success = status_module_result["scenarios"]["success"]
    assert _states(success) == ["completed"] * 4
    assert success["viewModel"]["overallLabel"] == "已完成"
    assert "已完成" in success["markup"]


def test_usable_results_survive_analysis_failure_as_partial(
    status_module_result: dict,
) -> None:
    partial = status_module_result["scenarios"]["partial"]
    states = _states(partial)
    assert states[:2] == ["completed", "completed"]
    assert states[2:] == ["partial", "partial"]
    assert partial["viewModel"]["partialSummary"] is not None
    assert partial["viewModel"]["completeFailure"] is False
    assert "自动拆解未生成" in partial["markup"]
    assert "部分完成" in partial["markup"]


def test_complete_failure_is_not_downgraded_to_partial(
    status_module_result: dict,
) -> None:
    failed = status_module_result["scenarios"]["completeFailure"]
    assert "failed" in _states(failed)
    assert "partial" not in _states(failed)
    assert _states(failed)[-1] == "failed"
    assert failed["viewModel"]["completeFailure"] is True
    assert failed["viewModel"]["partialSummary"] is None
    assert "素材获取未完成" in failed["markup"]


def test_unknown_state_never_paints_a_false_all_completed_result(
    status_module_result: dict,
) -> None:
    unknown = status_module_result["scenarios"]["unknown"]
    assert unknown["viewModel"]["unknown"] is True
    assert _states(unknown) != ["completed"] * 4
    assert "状态更新中" in unknown["markup"]


def test_missing_job_remains_readable_when_case_itself_proves_completion(
    status_module_result: dict,
) -> None:
    scenario = status_module_result["scenarios"]["missingJob"]
    assert _labels(scenario) == EXPECTED_STAGE_LABELS
    assert _states(scenario) == ["completed"] * 4
    assert "undefined" not in scenario["markup"]
    assert "null" not in scenario["markup"]


def test_status_only_success_without_case_does_not_claim_completion(
    status_module_result: dict,
) -> None:
    scenario = status_module_result["scenarios"]["missingCase"]
    assert _labels(scenario) == EXPECTED_STAGE_LABELS
    assert _states(scenario) == ["completed", "completed", "active", "pending"]
    assert scenario["viewModel"]["unknown"] is True
    assert scenario["viewModel"]["overallLabel"] == "状态更新中"
    assert "undefined" not in scenario["markup"]
    assert "null" not in scenario["markup"]


def test_case_only_completed_payload_closes_the_whole_flow(
    status_module_result: dict,
) -> None:
    case_only = status_module_result["scenarios"]["missingJob"]
    assert _states(case_only) == ["completed"] * 4
    assert case_only["viewModel"]["overallLabel"] == "已完成"
    assert case_only["viewModel"]["hasUsableResult"] is True
    assert case_only["viewModel"]["partialSummary"] is None
    assert case_only["viewModel"]["completeFailure"] is False
    assert case_only["viewModel"]["unknown"] is False


def test_missing_error_code_uses_a_safe_fallback(status_module_result: dict) -> None:
    missing = status_module_result["scenarios"]["missingError"]
    assert missing["viewModel"]["completeFailure"] is True
    public_category = missing["viewModel"]["failureCategory"]
    assert public_category in {"素材获取未完成", "状态暂时不可确认"}
    assert public_category in missing["markup"]
    assert "undefined" not in missing["markup"]
    assert "null" not in missing["markup"]


def test_multiple_failures_are_deduplicated_and_summarized_with_counts(
    status_module_result: dict,
) -> None:
    multiple = status_module_result["scenarios"]["multipleFailures"]
    markup = multiple["markup"]
    assert multiple["viewModel"]["partialSummary"] is not None
    assert markup.count("语音文本不可用") == 1
    assert markup.count("画面文字不可用") == 1
    assert markup.count("自动拆解未生成") == 1
    assert "1 项结果可用" in markup
    assert re.search(r"3 项(?:未完成|失败或缺失)", markup)


def test_missing_artifact_files_count_as_one_material_package_capability(
    status_module_result: dict,
) -> None:
    grouped = status_module_result["scenarios"]["groupedMissingArtifacts"]
    summary = grouped["viewModel"]["partialSummary"]
    assert summary is not None
    assert summary["successfulCount"] == 1
    assert summary["failedCount"] == 1
    assert summary["categories"] == ["素材包未完整"]
    assert grouped["markup"].count("素材包未完整") == 1
    assert "1 项结果可用" in grouped["markup"]
    assert re.search(r"1 项(?:未完成|失败或缺失)", grouped["markup"])


def test_duplicate_material_signals_count_once_but_optional_capabilities_stay_separate(
    status_module_result: dict,
) -> None:
    combined = status_module_result["scenarios"]["duplicateMaterialSignals"]
    summary = combined["viewModel"]["partialSummary"]
    assert summary is not None
    assert summary["successfulCount"] == 1
    assert summary["failedCount"] == 3
    assert set(summary["categories"]) == {
        "素材包未完整",
        "语音文本不可用",
        "画面文字不可用",
    }
    assert combined["markup"].count("素材包未完整") == 1
    assert combined["markup"].count("语音文本不可用") == 1
    assert combined["markup"].count("画面文字不可用") == 1
    assert re.search(r"3 项(?:未完成|失败或缺失)", combined["markup"])


def test_loaded_case_unavailable_analysis_overrides_status_only_success(
    status_module_result: dict,
) -> None:
    conflicts = status_module_result["analysisConflicts"]
    assert set(conflicts) == {"notAnalyzed", "notConfigured", "artifactIncomplete"}
    for name, conflict in conflicts.items():
        assert conflict["inputUnchanged"] is True, name
        assert _states(conflict)[2] != "completed", name
        assert conflict["viewModel"]["overallLabel"] != "已完成", name
        public_output = json.dumps(conflict["viewModel"], ensure_ascii=False)
        assert "AI 拆解报告" not in public_output, name

    for name in ("notAnalyzed", "notConfigured"):
        conflict = conflicts[name]
        assert _states(conflict) == ["completed", "completed", "partial", "partial"]
        assert conflict["viewModel"]["hasUsableResult"] is True
        assert conflict["viewModel"]["partialSummary"]["availableResults"] == [
            "基础素材包"
        ]
        assert conflict["viewModel"]["unknown"] is False


def test_real_job_or_case_analysis_payload_remains_stronger_than_status_conflict(
    status_module_result: dict,
) -> None:
    for name, evidence in status_module_result["actualAnalysisEvidence"].items():
        assert evidence["inputUnchanged"] is True, name
        assert _states(evidence) == ["completed"] * 4, name
        assert evidence["viewModel"]["overallLabel"] == "已完成", name
        assert evidence["viewModel"]["hasUsableResult"] is True, name
        assert evidence["viewModel"]["partialSummary"] is None, name


def test_normal_optional_absence_never_turns_a_complete_result_partial(
    semantic_edge_result: dict,
) -> None:
    for status, scenario in semantic_edge_result["neutralOptional"].items():
        assert _states(scenario) == ["completed"] * 4, status
        assert scenario["viewModel"]["partialSummary"] is None, status
        assert scenario["viewModel"]["overallLabel"] == "已完成", status


def test_explicit_optional_failures_still_produce_a_partial_summary(
    semantic_edge_result: dict,
) -> None:
    for status, scenario in semantic_edge_result["explicitOptionalFailure"].items():
        assert _states(scenario)[2:] == ["partial", "partial"], status
        assert scenario["viewModel"]["partialSummary"] is not None, status
        assert scenario["viewModel"]["completeFailure"] is False, status


def test_mismatched_case_is_never_used_to_complete_a_different_job(
    semantic_edge_result: dict,
) -> None:
    scenario = semantic_edge_result["mismatchedCase"]
    assert scenario["viewModel"]["unknown"] is True
    assert _states(scenario) != ["completed"] * 4
    assert scenario["viewModel"]["partialSummary"]["availableResults"] == [
        "基础素材包"
    ]
    assert "AI 拆解报告" not in json.dumps(
        scenario["viewModel"], ensure_ascii=False
    )


def test_workbench_poll_sequence_waits_for_case_before_terminal_projection(
    semantic_edge_result: dict,
) -> None:
    sequence = semantic_edge_result["sequence"]
    assert _states(sequence["running"]) == [
        "completed", "completed", "active", "pending"
    ]
    assert _states(sequence["successBeforeCaseRefresh"]) == [
        "completed", "completed", "active", "pending"
    ]
    assert sequence["successBeforeCaseRefresh"]["viewModel"]["unknown"] is True
    assert sequence["successBeforeCaseRefresh"]["viewModel"]["partialSummary"] is None
    assert _states(sequence["successAfterCaseRefresh"]) == ["completed"] * 4

    assert _states(sequence["failureBeforeCaseRefresh"]) == [
        "completed", "completed", "active", "pending"
    ]
    assert sequence["failureBeforeCaseRefresh"]["viewModel"]["unknown"] is True
    assert sequence["failureBeforeCaseRefresh"]["viewModel"]["completeFailure"] is False
    assert _states(sequence["failureAfterCaseRefresh"])[2:] == [
        "partial", "partial"
    ]

    case_only = semantic_edge_result["caseOnlySequence"]
    assert _states(case_only["running"]) == [
        "completed", "completed", "active", "pending"
    ]
    assert _states(case_only["successBeforeCaseRefresh"]) == [
        "completed", "completed", "active", "pending"
    ]
    assert case_only["successBeforeCaseRefresh"]["viewModel"]["unknown"] is True
    assert _states(case_only["successAfterCaseRefresh"]) == ["completed"] * 4

    raw = semantic_edge_result["rawSequence"]
    assert _states(raw["terminalBeforeCaseRefresh"]) == [
        "completed", "completed", "active", "pending"
    ]
    assert raw["terminalBeforeCaseRefresh"]["viewModel"]["overallLabel"] == "状态更新中"
    assert _states(raw["terminalAfterIncompleteCase"]) == [
        "completed", "partial", "completed", "partial"
    ]
    assert raw["terminalAfterIncompleteCase"]["viewModel"]["overallLabel"] == "部分结果可用"
    assert _states(raw["terminalAfterCompleteCase"]) == ["completed"] * 4


def test_running_or_stale_case_snapshots_never_render_a_terminal_failure(
    semantic_edge_result: dict,
) -> None:
    transient = semantic_edge_result["transientArtifact"]
    for name, scenario in transient.items():
        states = _states(scenario)
        assert "failed" not in states, name
        assert "partial" not in states, name
        assert states[2] == "active", name
    assert transient["stale"]["viewModel"]["unknown"] is True


def test_raw_analyze_case_top_level_result_is_real_completion_evidence(
    semantic_edge_result: dict,
) -> None:
    scenario = semantic_edge_result["rawTopLevelAnalysis"]
    assert _states(scenario) == ["completed"] * 4
    assert scenario["viewModel"]["overallLabel"] == "已完成"
    assert scenario["viewModel"]["hasUsableResult"] is True
    assert scenario["viewModel"]["partialSummary"] is None


def test_legacy_workbench_unknowns_degrade_but_raw_failed_remains_failed(
    semantic_edge_result: dict,
) -> None:
    legacy = semantic_edge_result["legacy"]
    for name in ("workbenchBlankError", "workbenchFutureError"):
        scenario = legacy[name]
        assert scenario["viewModel"]["unknown"] is True, name
        assert "failed" not in _states(scenario), name
        assert scenario["viewModel"]["overallLabel"] == "状态更新中", name

    raw_failed = legacy["rawFailedWithoutError"]
    assert raw_failed["viewModel"]["completeFailure"] is True
    assert "failed" in _states(raw_failed)

    hint_only = legacy["unverifiedAvailableHint"]
    assert hint_only["viewModel"]["unknown"] is True
    assert hint_only["viewModel"]["hasUsableResult"] is False
    assert hint_only["viewModel"]["partialSummary"] is None

    flow_only = legacy["flowOnlyComplete"]
    assert flow_only["viewModel"]["unknown"] is True
    assert _states(flow_only) != ["completed"] * 4
    assert flow_only["viewModel"]["overallLabel"] == "状态更新中"


def test_loaded_case_artifact_false_overrides_stale_job_case_success_evidence(
    status_module_result: dict,
) -> None:
    conflict = status_module_result["scenarios"]["staleCaseArtifactSuccess"]
    assert conflict["viewModel"]["hasUsableResult"] is False
    assert conflict["viewModel"]["partialSummary"] is None
    assert _states(conflict)[1] == "failed"
    assert "基础素材包" not in json.dumps(
        conflict["viewModel"], ensure_ascii=False
    )


def test_raw_sensitive_error_details_never_reach_view_model_or_markup(
    status_module_result: dict,
) -> None:
    sensitive = status_module_result["scenarios"]["sensitive"]
    category = status_module_result["categoryCases"]["secretSource"]
    public_output = json.dumps(sensitive["viewModel"], ensure_ascii=False) + sensitive["markup"] + category
    for secret_fragment in (
        "Authorization",
        "Bearer",
        "eyJhbGciOi",
        "Cookie",
        "sessionid-private",
        "raw-token",
        "/Users/alice",
        "private.mp4",
    ):
        assert secret_fragment not in public_output


def test_failure_categories_are_bounded_public_language(status_module_result: dict) -> None:
    assert status_module_result["categoryCases"] == {
        "download": "素材获取未完成",
        "caseBuild": "素材包未完整",
        "analysis": "自动拆解未生成",
        "asr": "语音文本不可用",
        "ocr": "画面文字不可用",
        "enrichment": "证据补充未完成",
        "unknown": "状态暂时不可确认",
        "secretSource": "自动拆解未生成",
    }


def test_markup_is_semantic_accessible_and_read_only(status_module_result: dict) -> None:
    markup = status_module_result["scenarios"]["middleActive"]["markup"]
    assert re.search(r"<section\b", markup)
    assert re.search(r"<ol\b[^>]*aria-label=", markup)
    assert len(re.findall(r"<li\b", markup)) == 4
    assert 'aria-current="step"' in markup
    assert "进行中" in markup
    assert all(label in markup for label in EXPECTED_STAGE_LABELS)
    assert "<button" not in markup
    assert "tabindex" not in markup


def test_every_scenario_uses_only_the_five_legal_stage_states(
    status_module_result: dict,
) -> None:
    for name, scenario in status_module_result["scenarios"].items():
        states = _states(scenario)
        assert len(states) == 4, name
        assert set(states) <= ALLOWED_STATES, name


def test_extracted_module_has_no_network_timer_or_dom_side_effects() -> None:
    source = _module_source()
    forbidden_patterns = {
        "fetch": r"\bfetch\s*\(",
        "XHR": r"\bXMLHttpRequest\b",
        "WebSocket": r"\bWebSocket\b",
        "EventSource": r"\bEventSource\b",
        "setTimeout": r"\bsetTimeout\s*\(",
        "setInterval": r"\bsetInterval\s*\(",
        "document": r"\bdocument\s*[.[]",
        "localStorage": r"\blocalStorage\b",
        "sessionStorage": r"\bsessionStorage\b",
        "navigator": r"\bnavigator\s*[.[]",
    }
    for name, pattern in forbidden_patterns.items():
        assert re.search(pattern, source) is None, name


def test_template_keeps_exactly_four_read_only_accessible_status_stages() -> None:
    status_template = _single_item_status_template()
    assert re.findall(
        r'data-single-item-stage="([^"]+)"', status_template
    ) == ["received", "acquisition", "analysis", "complete"]
    assert re.findall(
        r'<span class="single-item-stage-name">\d+\. ([^<]+)</span>',
        status_template,
    ) == EXPECTED_STAGE_LABELS
    assert status_template.count('class="single-item-stage pending"') == 4
    assert status_template.count('aria-live="polite"') == 1
    assert not re.search(
        r'id="single-item-partial-summary"[^>]*(?:role="status"|aria-live=)',
        status_template,
    )
    assert re.search(
        r'id="single-item-status-announcement"[^>]*role="status"[^>]*aria-live="polite"[^>]*aria-atomic="true"',
        status_template,
    )
    assert 'aria-label="单作品任务进度"' in status_template
    assert 'aria-busy="false"' in status_template
    for interactive_tag in ("<button", "<a ", "<input", "<form"):
        assert interactive_tag not in status_template


def test_app_request_and_polling_baselines_do_not_drift() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    assert source.count("fetch(") == 42
    assert source.count("/iterations") == 4
    assert source.count("/execution-pack`") == 1
    assert source.count("/generate-execution-pack`") == 1
    assert len(re.findall(r"window\.setTimeout\(resolve,\s*700\)", source)) == 1
    assert len(re.findall(r"window\.setTimeout\(resolve,\s*900\)", source)) == 4

    single_poll = _source_between(
        source,
        "async function pollJob(",
        "copyHomePromptButton.addEventListener",
    )
    assert len(re.findall(r"window\.setTimeout\(resolve,\s*700\)", single_poll)) == 1
    assert re.search(r"window\.setTimeout\(resolve,\s*900\)", single_poll) is None


def test_polling_context_isolated_and_known_terminal_state_never_becomes_stale() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    run_single = _source_between(
        source,
        "async function runSingleValue(value)",
        'singleForm.addEventListener("submit"',
    )
    assert "const observationGeneration = startSingleItemObservation();" in run_single
    assert run_single.index("const imported = await readJsonResponse(importResponse);") < run_single.index(
        'isCurrentSingleItemObservation("", observationGeneration)'
    ) < run_single.index("currentAwemeId = imported.video.aweme_id;")
    assert "resolveQualities([currentAwemeId], observationGeneration)" in run_single
    assert "downloadCandidate(selectedCandidate, observationGeneration)" in run_single

    download_candidate = _source_between(
        source,
        "async function downloadCandidate(",
        'buildCaseButton.addEventListener("click"',
    )
    assert "bindSingleItemObservation(payload.job_id, observationGeneration)" in download_candidate
    assert "startSingleItemObservation(payload.job_id)" not in download_candidate

    build_case = _source_between(
        source,
        'buildCaseButton.addEventListener("click"',
        "async function pollJob(",
    )
    assert "const observationGeneration = startSingleItemObservation();" in build_case
    assert "bindSingleItemObservation(payload.job_id, observationGeneration)" in build_case
    assert "startSingleItemObservation(payload.job_id)" not in build_case

    open_target = _source_between(
        source,
        "async function openWorkbenchSingleTarget",
        "async function monitorWorkbenchSingleJob",
    )
    fetch_index = open_target.index("const job = await fetchWorkbenchJob(jobId);")
    for reset in (
        "currentSingleJob = null;",
        "loadedHomeCase = null;",
        'singleItemFlow = {stage: "idle", status: "pending", error_code: ""};',
        'currentLocalVideoId = "";',
        'homeCaseView.classList.add("hidden");',
        'resultCard.classList.add("hidden");',
        "singleButton.disabled = false;",
        'singleButton.textContent = "解析";',
        "buildCaseButton.disabled = false;",
    ):
        assert reset in open_target
        assert open_target.index(reset) < fetch_index

    render_job = _source_between(
        source,
        "function renderJobStatus(job, fallbackMessage = \"\")",
        "function isProfileBuildJobActive",
    )
    assert "switchedJob || reachedTerminal" in render_job
    assert "loadedHomeCase = null;" in render_job
    assert "if (nextJobId !== singleItemActiveJobId)" in render_job
    assert render_job.count('activeHomeRoute !== "single"') >= 1
    assert render_job.count('activeHomeRoute !== "profile"') >= 1
    assert "terminalRegression" in render_job
    assert "__singleItemCaseVerificationPending" in render_job

    assert "const observationGeneration = startSingleItemObservation(jobId);" in open_target
    assert "monitorWorkbenchSingleJob(jobId, observationGeneration)" in open_target

    poll_job = _source_between(
        source,
        "async function pollJob(",
        "copyHomePromptButton.addEventListener",
    )
    assert poll_job.count("isCurrentSingleItemObservation(jobId, observationGeneration)") >= 4
    assert "pollJob(jobId, onSuccess, onProgress, observationGeneration)" in poll_job
    assert 'const terminalStatusKnown = ["success", "failed"].includes' in poll_job
    assert (
        'if (!terminalStatusKnown) {\n'
        '      currentSingleJob = {...(currentSingleJob || {}), status: "stale"};'
    ) in poll_job

    monitor = _source_between(
        source,
        "async function monitorWorkbenchSingleJob(",
        "async function monitorWorkbenchProfileScanJob",
    )
    assert monitor.count("isCurrentSingleItemObservation(jobId, observationGeneration)") >= 3
    assert "monitorWorkbenchSingleJob(jobId, observationGeneration)" in monitor

    show_analysis = _source_between(
        source,
        "async function showAnalysisInline",
        "async function readJsonResponse",
    )
    assert show_analysis.index("await loadCasePayload(caseId)") < show_analysis.index(
        "isCurrentSingleItemObservation(options.jobId, options.observationGeneration)"
    ) < show_analysis.index("renderHomeCase(caseData)")

    open_target_listener = _source_between(
        source,
        'document.addEventListener("workbench:open-target"',
        "function restoreLibraryResumeTarget",
    )
    single_listener = _source_between(
        open_target_listener,
        'if (route === "single")',
        "try {\n    const restored = await openWorkbenchProfileTarget",
    )
    assert "const restorePromise = openWorkbenchSingleTarget(target, openUrl);" in single_listener
    assert single_listener.count(
        "isCurrentSingleItemObservation(observationJobId, observationGeneration)"
    ) >= 2

    recovered_single = _source_between(
        source,
        "async function renderRecoveredSingleJob",
        "async function openWorkbenchSingleTarget",
    )
    assert recovered_single.count(
        "isCurrentSingleItemObservation(observationJobId, observationGeneration)"
    ) >= 3

    set_route = _source_between(
        source,
        "function setHomeRoute(route, updateHash = true)",
        "function routeFromHash",
    )
    assert 'activeHomeRoute === "single" && activeRoute !== "single"' in set_route
    assert "stopSingleItemObservation();" in set_route
    assert set_route.index("stopSingleItemObservation();") < set_route.index(
        "activeHomeRoute = activeRoute;"
    )

    profile_queue = _source_between(
        source,
        "async function pollProfileQueue",
        "// Creator Clone: enrichment queue",
    )
    assert profile_queue.count('activeHomeRoute !== "profile"') >= 3

    profile_distill = _source_between(
        source,
        "async function pollCreatorCloneDistillJob",
        "// Creator Clone: distillation",
    )
    assert profile_distill.count('activeHomeRoute !== "profile"') >= 2

    profile_monitor = _source_between(
        source,
        "async function monitorWorkbenchProfileScanJob",
        "async function openWorkbenchProfileTarget",
    )
    assert profile_monitor.count('activeHomeRoute !== "profile"') >= 3

    place_job_card = _source_between(
        source,
        "function placeJobCard",
        "function scrollProfileTaskPanel",
    )
    assert 'scope === "single" && activeHomeRoute !== "single"' in place_job_card
    assert 'scope === "profile" && activeHomeRoute !== "profile"' in place_job_card
    assert place_job_card.count("return true;") >= 3

    build_profile_queue = _source_between(
        source,
        "async function buildSelectedProfileQueue",
        "function topCreatorSampleViewItemsBy",
    )
    assert build_profile_queue.count('activeHomeRoute !== "profile"') >= 1

    distill_profile = _source_between(
        source,
        "async function distillSelectedCreatorClone",
        "async function batchDistillSelectedCreatorClone",
    )
    assert distill_profile.count('activeHomeRoute !== "profile"') >= 1

    batch_distill_profile = _source_between(
        source,
        "async function batchDistillSelectedCreatorClone",
        "function setWorkbenchStatus",
    )
    assert batch_distill_profile.count('activeHomeRoute !== "profile"') >= 1


def test_pre_job_observation_cannot_rebind_after_a_newer_target_opens() -> None:
    if NODE_BINARY is None:
        pytest.skip("Node.js is unavailable")
    source = APP_JS.read_text(encoding="utf-8")
    helpers = _source_between(
        source,
        "function startSingleItemObservation",
        "function setSingleItemFlow",
    )
    place_job_card = _source_between(
        source,
        "function placeJobCard",
        "function scrollProfileTaskPanel",
    )
    script = (
        "const helperSource = "
        + json.dumps(helpers)
        + ";\nconst placeJobCardSource = "
        + json.dumps(place_job_card)
        + ";\n"
        + r"""
let singleItemObservationGeneration = 0;
let singleItemActiveJobId = "";
const singleButton = {disabled: false, textContent: "解析"};
const buildCaseButton = {disabled: false};
eval(helperSource);

const oldGeneration = startSingleItemObservation();
const newerGeneration = startSingleItemObservation("job_newer");
const lateBindAccepted = bindSingleItemObservation("job_old", oldGeneration);
const stateAfterLateBind = {
  generation: singleItemObservationGeneration,
  jobId: singleItemActiveJobId,
};

const freshGeneration = startSingleItemObservation();
const freshBindAccepted = bindSingleItemObservation("job_fresh", freshGeneration);
const duplicateBindAccepted = bindSingleItemObservation("job_duplicate", freshGeneration);
const freshIsCurrent = isCurrentSingleItemObservation("job_fresh", freshGeneration);

let currentJobCardScope = "single";
let activeHomeRoute = "single";
const jobCard = {insertedAfter: ""};
const resultCard = {insertAdjacentElement(_position, element) { element.insertedAfter = "single"; }};
const creatorCloneNextBar = {insertAdjacentElement(_position, element) { element.insertedAfter = "profile"; }};
eval(placeJobCardSource);
const activeSingleGeneration = startSingleItemObservation("job_single");
singleButton.disabled = true;
singleButton.textContent = "解析中...";
buildCaseButton.disabled = true;
stopSingleItemObservation();
const lateProfilePlacementAccepted = placeJobCard("profile");
const scopeAfterLateProfilePlacement = currentJobCardScope;
activeHomeRoute = "profile";
const profilePlacementAccepted = placeJobCard("profile");
process.stdout.write(JSON.stringify({
  newerGeneration,
  lateBindAccepted,
  stateAfterLateBind,
  freshGeneration,
  freshBindAccepted,
  duplicateBindAccepted,
  freshIsCurrent,
  routeExitInvalidatedSingle: !isCurrentSingleItemObservation("job_single", activeSingleGeneration),
  singleButtonReset: !singleButton.disabled && singleButton.textContent === "解析",
  buildCaseButtonReset: !buildCaseButton.disabled,
  lateProfilePlacementAccepted,
  scopeAfterLateProfilePlacement,
  profilePlacementAccepted,
  currentJobCardScope,
  jobCardInsertedAfter: jobCard.insertedAfter,
  finalGeneration: singleItemObservationGeneration,
  finalJobId: singleItemActiveJobId,
}));
"""
    )
    result = _run_node(script)
    assert result["lateBindAccepted"] is False
    assert result["stateAfterLateBind"] == {
        "generation": result["newerGeneration"],
        "jobId": "job_newer",
    }
    assert result["freshBindAccepted"] is True
    assert result["duplicateBindAccepted"] is False
    assert result["freshIsCurrent"] is True
    assert result["routeExitInvalidatedSingle"] is True
    assert result["singleButtonReset"] is True
    assert result["buildCaseButtonReset"] is True
    assert result["lateProfilePlacementAccepted"] is False
    assert result["scopeAfterLateProfilePlacement"] == "single"
    assert result["profilePlacementAccepted"] is True
    assert result["currentJobCardScope"] == "profile"
    assert result["jobCardInsertedAfter"] == "profile"
    assert result["finalGeneration"] > result["freshGeneration"]
    assert result["finalJobId"] == ""


def test_late_profile_poll_cannot_steal_a_new_single_item_context() -> None:
    if NODE_BINARY is None:
        pytest.skip("Node.js is unavailable")
    source = APP_JS.read_text(encoding="utf-8")
    profile_monitor = _source_between(
        source,
        "async function monitorWorkbenchProfileScanJob",
        "async function openWorkbenchProfileTarget",
    )
    script = "const monitorSource = " + json.dumps(profile_monitor) + ";\n" + r"""
let activeHomeRoute = "profile";
let releaseFetch;
let placeCalls = 0;
let renderCalls = 0;
let statusWrites = 0;
const profileScanStatus = {
  value: "",
  set textContent(value) { this.value = value; statusWrites += 1; },
  get textContent() { return this.value; },
};
const window = {setTimeout(resolve) { resolve(); }};
function fetchWorkbenchJob() {
  return new Promise((resolve) => { releaseFetch = resolve; });
}
function placeJobCard() { placeCalls += 1; }
function renderJobStatus() { renderCalls += 1; }
function renderWorkbenchRestoredJobStatus() { renderCalls += 1; }
function profileBuildJobAgeSeconds() { return 0; }
async function refreshProfilePoolFromPersistedSet() {}
eval(monitorSource);

(async () => {
  const pending = monitorWorkbenchProfileScanJob("job_profile");
  activeHomeRoute = "single";
  releaseFetch({
    id: "job_profile",
    type: "profile-scan",
    status: "running",
    progress: 25,
    result_json: {},
  });
  const result = await pending;
  process.stdout.write(JSON.stringify({result, placeCalls, renderCalls, statusWrites}));
})().catch((error) => { console.error(error); process.exit(1); });
"""
    result = _run_node(script)
    assert result == {
        "result": False,
        "placeCalls": 0,
        "renderCalls": 0,
        "statusWrites": 0,
    }


def test_late_poll_responses_cannot_replace_the_active_or_terminal_job() -> None:
    if NODE_BINARY is None:
        pytest.skip("Node.js is unavailable")
    source = APP_JS.read_text(encoding="utf-8")
    render_job = _source_between(
        source,
        "function renderJobStatus(job, fallbackMessage = \"\")",
        "function isProfileBuildJobActive",
    )
    script = "const renderSource = " + json.dumps(render_job) + ";\n" + r"""
let currentJobCardScope = "single";
let activeHomeRoute = "single";
let singleItemActiveJobId = "job_current";
let currentSingleJob = {id: "job_current", status: "success", result_json: {}};
let loadedHomeCase = {case_id: "case_current"};
const progressBar = {style: {width: ""}};
const jobMessage = {className: "", textContent: ""};
function renderSingleItemStatus() {}
function singleItemJobMessage() { return "状态"; }
function renderJobPhase() {}
function getCaseId(result) { return result.case_id || result.case?.case_id || ""; }
eval(renderSource);

const sameJobRegressionAccepted = renderJobStatus({
  id: "job_current", status: "running", progress: 40, result_json: {},
});
const otherJobAccepted = renderJobStatus({
  id: "job_old", status: "running", progress: 70, result_json: {},
});
const preservedTerminal = {...currentSingleJob};

singleItemActiveJobId = "job_terminal";
currentSingleJob = {id: "job_terminal", status: "running", result_json: {}};
loadedHomeCase = {case_id: "case_terminal"};
const terminalAccepted = renderJobStatus({
  id: "job_terminal",
  type: "download-build-analyze-case",
  status: "success",
  progress: 100,
  result_json: {
    case_id: "case_terminal",
    case: {case_id: "case_terminal", local_video_id: "local_terminal"},
    analysis_status: "success",
    analysis: {analysis_result: {summary: "result"}},
  },
});
process.stdout.write(JSON.stringify({
  sameJobRegressionAccepted,
  otherJobAccepted,
  preservedTerminal,
  terminalAccepted,
  terminalProjection: currentSingleJob,
  caseCleared: loadedHomeCase === null,
}));
"""
    result = _run_node(script)
    assert result["sameJobRegressionAccepted"] is False
    assert result["otherJobAccepted"] is False
    assert result["preservedTerminal"]["status"] == "success"
    assert result["terminalAccepted"] is True
    assert result["caseCleared"] is True
    assert result["terminalProjection"]["__singleItemCaseVerificationPending"] is True


def test_live_region_updates_only_when_the_public_announcement_changes(
    semantic_edge_result: dict,
) -> None:
    source = _module_source()
    assert source.count('aria-live="polite"') == 0
    assert "if (elements.announcement.textContent !== announcement)" in source
    announcements = semantic_edge_result["announcements"]
    assert "获取素材" in announcements["acquisition"]
    assert "生成分析" in announcements["analysis"]
    assert announcements["acquisition"] != announcements["analysis"]
    assert "语音文本不可用" in announcements["partial"]


def test_single_item_failure_ui_never_interpolates_raw_error_messages() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    single_scopes = {
        "singleItemJobMessage": _source_between(
            source,
            "function singleItemJobMessage(job, fallbackMessage = \"\")",
            "renderSingleItemStatus();",
        ),
        "recoveredSingleJob": _source_between(
            source,
            "async function renderRecoveredSingleJob",
            "async function openWorkbenchSingleTarget",
        ),
        "runSingleValue": _source_between(
            source,
            "async function runSingleValue(value)",
            'singleForm.addEventListener("submit"',
        ),
        "downloadCandidate": _source_between(
            source,
            "async function downloadCandidate(",
            'buildCaseButton.addEventListener("click"',
        ),
        "buildCase": _source_between(
            source,
            'buildCaseButton.addEventListener("click"',
            "async function pollJob(",
        ),
        "pollJob": _source_between(
            source,
            "async function pollJob(",
            "copyHomePromptButton.addEventListener",
        ),
    }
    open_target_listener = _source_between(
        source,
        'document.addEventListener("workbench:open-target"',
        "function restoreLibraryResumeTarget",
    )
    single_scopes["singleResumeTarget"] = _source_between(
        open_target_listener,
        'if (route === "single")',
        "const restored = await openWorkbenchProfileTarget",
    )

    for name, scope in single_scopes.items():
        assert re.search(r"\b(?:error|job)\.message\b", scope) is None, name

    workflow_result_scope = _source_between(
        source,
        "function renderWorkflowResult(result)",
        "function getCaseId(result)",
    )
    assert "JSON.stringify(result" not in workflow_result_scope
    assert "showJson(jobResult, result)" not in single_scopes["recoveredSingleJob"]

    assert "singleItemFailureCategory(error" in single_scopes["runSingleValue"]
    assert "singleItemFailureCategory(job" in single_scopes["pollJob"]
    assert "singleItemFailureCategory(error" in single_scopes["singleResumeTarget"]

    run_single = single_scopes["runSingleValue"]
    assert run_single.count('currentAwemeId = "";') == 1
    assert run_single.index('currentAwemeId = "";') < run_single.index(
        'setSingleItemFlow("received", "active")'
    )
    catch_scope = _source_between(
        run_single,
        "} catch (error) {",
        "} finally {",
    )
    assert (
        'setSingleItemFlow(currentAwemeId ? "acquisition" : "received", '
        '"failed", error.error_code);'
    ) in catch_scope
