from __future__ import annotations

import json
from typing import Annotated, Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StrictInt, StrictStr, field_validator
from pydantic_core import PydanticCustomError

from app.errors import AppError, ErrorCode
from app.routes.common import error_response
from app.services.creator_clone import (
    creator_clone_dir,
    creator_intelligence_payload_for_sample_set,
    export_paths,
    load_sample_set,
)
from app.services.creator_intelligence import BehaviorRepresentation
from app.services.creator_intelligence import CreatorRuntimeEngine
from app.services.creator_intelligence import project_from_clone_sample_set
from app.services.creator_intelligence import WorkflowAction
from app.services.creator_intelligence.generator import generate_creator_strategy_plan
from app.services.creator_intelligence.execution_pack import (
    generate_creator_execution_pack,
    load_creator_execution_pack,
)
from app.services.creator_intelligence.execution_record import (
    load_creator_execution_record,
    start_creator_execution_record,
    update_creator_execution_record,
)
from app.services.creator_intelligence.outcome_snapshot import (
    append_creator_outcome_snapshot,
    load_creator_outcome_timeline,
    normalize_optional_outcome_timestamp,
    normalize_outcome_publication_url,
    update_creator_outcome_snapshot,
    upsert_creator_outcome_timeline,
)
from app.services.creator_intelligence.iteration_history import (
    get_creator_iteration,
    get_creator_iteration_artifact,
    list_creator_iterations,
    start_next_creator_iteration,
)


router = APIRouter(prefix="/api/creator-intelligence", tags=["creator-intelligence"])


class CreatorIntelligenceWorkflowDispatchRequest(BaseModel):
    action: str
    selected_sample_ids: list[str] = Field(default_factory=list)


class CreatorExecutionPackGenerateRequest(BaseModel):
    topic_index: int = Field(ge=0, le=100)


class CreatorExecutionProductionStatusPatch(BaseModel):
    shooting: Literal["pending", "completed", "skipped"] | None = None
    editing: Literal["pending", "completed", "skipped"] | None = None
    publishing: Literal["pending", "completed", "skipped"] | None = None


class CreatorExecutionFeedbackPatch(BaseModel):
    was_used: bool | None = None
    difficulty: Literal["", "easy", "normal", "hard"] | None = None
    quality_rating: int | None = Field(default=None, ge=1, le=5)
    result_rating: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = Field(default=None, max_length=1000)


class CreatorExecutionRecordPatchRequest(BaseModel):
    status: Literal["draft", "in_progress", "completed", "archived"] | None = None
    production_status: CreatorExecutionProductionStatusPatch | None = None
    feedback: CreatorExecutionFeedbackPatch | None = None


OutcomeMetricValue = Annotated[StrictInt, Field(ge=0)] | None


class CreatorOutcomePublicationRequest(BaseModel):
    platform: Literal["douyin", "xhs", "bili", "other"] = "douyin"
    platform_item_id: StrictStr = Field(default="", max_length=160)
    published_url: StrictStr = Field(default="", max_length=2048)
    published_at: StrictStr | None = None

    @field_validator("published_url")
    @classmethod
    def validate_published_url(cls, value: str) -> str:
        try:
            return normalize_outcome_publication_url(value)
        except ValueError as error:
            raise PydanticCustomError("outcome_url_invalid", str(error)) from error

    @field_validator("published_at")
    @classmethod
    def validate_published_at(cls, value: str | None) -> str | None:
        try:
            return normalize_optional_outcome_timestamp(value, "publication.published_at")
        except ValueError as error:
            raise PydanticCustomError("outcome_timestamp_invalid", str(error)) from error


class CreatorOutcomeMetricsRequest(BaseModel):
    views: OutcomeMetricValue = None
    likes: OutcomeMetricValue = None
    comments: OutcomeMetricValue = None
    shares: OutcomeMetricValue = None
    collects: OutcomeMetricValue = None


class CreatorIterationStartNextRequest(BaseModel):
    close_current: bool = False
    close_reason: Literal["", "cancelled", "superseded", "not_published", "other"] = ""
    close_note: str = Field(default="", max_length=500)


def project_payload_for_sample_set(
    sample_set,
    *,
    workflow: dict | None = None,
    behavior_model: BehaviorRepresentation | dict | None = None,
    strategy_output: dict | None = None,
) -> dict:
    project = project_from_clone_sample_set(sample_set)
    intelligence = creator_intelligence_payload_for_sample_set(sample_set)
    behavior_payload = behavior_model.to_dict() if hasattr(behavior_model, "to_dict") else behavior_model
    strategy_payload = strategy_output if strategy_output is not None else intelligence.get("strategy_output")
    runtime_state = intelligence.get("runtime_state") if isinstance(intelligence.get("runtime_state"), dict) else {}
    return {
        "ok": True,
        "project": project.to_dict(),
        "workflow": workflow or intelligence.get("workflow") or {},
        "behavior_model": behavior_payload or intelligence.get("behavior_model") or None,
        "strategy_output": strategy_payload if strategy_payload is not None else {},
        "result": intelligence.get("result") or {},
        "runtime_state": runtime_state or CreatorRuntimeEngine.from_sample_set(sample_set).state.to_dict(),
        "exports": export_paths(sample_set.set_id),
    }


@router.get("/projects/{project_id}")
def get_creator_intelligence_project(project_id: str):
    try:
        sample_set = load_sample_set(project_id)
        return project_payload_for_sample_set(sample_set)
    except AppError as error:
        return error_response(error)


@router.post("/projects/{project_id}/generate-strategy")
def generate_creator_intelligence_strategy(project_id: str):
    try:
        sample_set = load_sample_set(project_id)
        result_path = creator_clone_dir(project_id) / "creator_clone_result.json"
        if not result_path.is_file():
            return error_response(AppError(ErrorCode.CREATOR_REPORT_NOT_READY), status_code=400)
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return error_response(AppError(ErrorCode.CREATOR_REPORT_NOT_READY), status_code=400)
        if not isinstance(result, dict) or not result.get("creator_clone_strategy"):
            return error_response(AppError(ErrorCode.CREATOR_REPORT_NOT_READY), status_code=400)

        content_profile = result.get("content_profile") if isinstance(result.get("content_profile"), dict) else {}
        view_model = result.get("creator_report_view_model") if isinstance(result.get("creator_report_view_model"), dict) else {}
        value_upgrade = view_model.get("value_upgrade") if isinstance(view_model.get("value_upgrade"), dict) else {}
        diagnostics = value_upgrade.get("diagnostics") if isinstance(value_upgrade.get("diagnostics"), dict) else {}
        report_quality = result.get("report_quality") if isinstance(result.get("report_quality"), dict) else {}
        evidence_gaps = result.get("evidence_gaps") if isinstance(result.get("evidence_gaps"), list) else []
        plan = generate_creator_strategy_plan(
            creator_clone_strategy=result.get("creator_clone_strategy") or {},
            report_view_model=view_model,
            report_quality=report_quality,
            diagnostics=diagnostics,
            evidence_gaps=evidence_gaps,
            content_profile=content_profile.get("effective") or sample_set.content_profile or "general",
            selected_sample_evidence_summary=_selected_sample_evidence_summary(sample_set, result),
        )
        plan_path = creator_clone_dir(project_id) / "creator_strategy_plan.json"
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "ok": True,
            "strategy_plan": plan,
            "source": {
                "project_id": project_id,
                "report_quality_score": report_quality.get("quality_score", report_quality.get("score", 0)),
                "diagnostics": diagnostics,
            },
        }
    except AppError as error:
        return error_response(error)


@router.post("/projects/{project_id}/generate-execution-pack")
def generate_creator_intelligence_execution_pack(
    project_id: str,
    payload: CreatorExecutionPackGenerateRequest,
):
    try:
        execution_pack = generate_creator_execution_pack(project_id, payload.topic_index)
        return JSONResponse(
            content={"ok": True, "execution_pack": execution_pack},
            headers={"Cache-Control": "no-store"},
        )
    except AppError as error:
        return error_response(error)


@router.get("/projects/{project_id}/execution-pack")
def get_creator_intelligence_execution_pack(project_id: str):
    try:
        execution_pack = load_creator_execution_pack(project_id)
        return JSONResponse(
            content={"ok": True, "execution_pack": execution_pack},
            headers={"Cache-Control": "no-store"},
        )
    except AppError as error:
        return error_response(error)


@router.post("/projects/{project_id}/execution-record/start")
def start_creator_intelligence_execution_record(project_id: str):
    try:
        execution_record = start_creator_execution_record(project_id)
        return JSONResponse(
            content={"ok": True, "execution_record": execution_record},
            headers={"Cache-Control": "no-store"},
        )
    except AppError as error:
        return error_response(error)


@router.get("/projects/{project_id}/execution-record")
def get_creator_intelligence_execution_record(project_id: str):
    try:
        execution_record = load_creator_execution_record(project_id)
        return JSONResponse(
            content={"ok": True, "execution_record": execution_record},
            headers={"Cache-Control": "no-store"},
        )
    except AppError as error:
        return error_response(error)


@router.patch("/projects/{project_id}/execution-record")
def patch_creator_intelligence_execution_record(
    project_id: str,
    payload: CreatorExecutionRecordPatchRequest,
):
    try:
        execution_record = update_creator_execution_record(
            project_id,
            payload.model_dump(exclude_unset=True),
        )
        return JSONResponse(
            content={"ok": True, "execution_record": execution_record},
            headers={"Cache-Control": "no-store"},
        )
    except AppError as error:
        return error_response(error)


@router.put("/projects/{project_id}/outcome")
def put_creator_intelligence_outcome(
    project_id: str,
    payload: CreatorOutcomePublicationRequest,
):
    try:
        outcome = upsert_creator_outcome_timeline(project_id, payload.model_dump())
        return JSONResponse(
            content={"ok": True, "outcome": outcome},
            headers={"Cache-Control": "no-store"},
        )
    except AppError as error:
        return error_response(error)


@router.get("/projects/{project_id}/outcome")
def get_creator_intelligence_outcome(project_id: str):
    try:
        outcome = load_creator_outcome_timeline(project_id)
        return JSONResponse(
            content={"ok": True, "outcome": outcome},
            headers={"Cache-Control": "no-store"},
        )
    except AppError as error:
        return error_response(error)


@router.post("/projects/{project_id}/outcome/snapshots")
def post_creator_intelligence_outcome_snapshot(
    project_id: str,
    payload: CreatorOutcomeMetricsRequest,
):
    try:
        snapshot, outcome = append_creator_outcome_snapshot(project_id, payload.model_dump())
        return JSONResponse(
            content={"ok": True, "snapshot": snapshot, "outcome": outcome},
            headers={"Cache-Control": "no-store"},
        )
    except AppError as error:
        return error_response(error)


@router.patch("/projects/{project_id}/outcome/snapshots/{snapshot_id}")
def patch_creator_intelligence_outcome_snapshot(
    project_id: str,
    snapshot_id: str,
    payload: CreatorOutcomeMetricsRequest,
):
    try:
        snapshot, outcome = update_creator_outcome_snapshot(
            project_id,
            snapshot_id,
            payload.model_dump(exclude_unset=True),
        )
        return JSONResponse(
            content={"ok": True, "snapshot": snapshot, "outcome": outcome},
            headers={"Cache-Control": "no-store"},
        )
    except AppError as error:
        return error_response(error)


@router.get("/projects/{project_id}/iterations")
def get_creator_intelligence_iterations(project_id: str):
    try:
        return JSONResponse(
            content={"ok": True, **list_creator_iterations(project_id)},
            headers={"Cache-Control": "no-store"},
        )
    except AppError as error:
        return error_response(error)


@router.get("/projects/{project_id}/iterations/{iteration_id}")
def get_creator_intelligence_iteration(project_id: str, iteration_id: str):
    try:
        return JSONResponse(
            content={"ok": True, **get_creator_iteration(project_id, iteration_id)},
            headers={"Cache-Control": "no-store"},
        )
    except AppError as error:
        return error_response(error)


@router.get("/projects/{project_id}/iterations/{iteration_id}/artifacts/{artifact_name}")
def get_creator_intelligence_iteration_artifact(
    project_id: str,
    iteration_id: str,
    artifact_name: Literal["execution-pack", "execution-record", "outcome"],
):
    try:
        return JSONResponse(
            content={
                "ok": True,
                "project_id": project_id,
                "iteration_id": iteration_id,
                "artifact_name": artifact_name,
                "artifact": get_creator_iteration_artifact(project_id, iteration_id, artifact_name),
            },
            headers={"Cache-Control": "no-store"},
        )
    except AppError as error:
        return error_response(error)


@router.post("/projects/{project_id}/iterations/start-next")
def start_next_creator_intelligence_iteration(
    project_id: str,
    payload: CreatorIterationStartNextRequest,
):
    try:
        result = start_next_creator_iteration(
            project_id,
            close_current=payload.close_current,
            close_reason=payload.close_reason,
            close_note=payload.close_note,
        )
        return JSONResponse(
            content={"ok": True, **result},
            headers={"Cache-Control": "no-store"},
        )
    except AppError as error:
        return error_response(error)


@router.post("/projects/{project_id}/workflow")
def dispatch_creator_intelligence_workflow(project_id: str, payload: CreatorIntelligenceWorkflowDispatchRequest):
    try:
        result = CreatorRuntimeEngine.dispatch_sample_set(
            project_id,
            WorkflowAction(payload.action),
            selected_sample_ids=payload.selected_sample_ids,
        )
        return project_payload_for_sample_set(
            result.sample_set,
            workflow=result.workflow,
            behavior_model=result.behavior_model,
            strategy_output=result.strategy_output,
        )
    except ValueError as error:
        return error_response(AppError(ErrorCode.PROFILE_SCAN_FAILED, str(error)))
    except AppError as error:
        return error_response(error)


def _selected_sample_evidence_summary(sample_set, result: dict) -> dict:
    selected_ids = set(sample_set.selected_sample_ids or [])
    selected = [sample for sample in sample_set.samples if sample.sample_id in selected_ids or sample.selected]
    if not selected:
        selected = list(sample_set.samples)
    understanding = {"full": 0, "partial": 0, "metadata_only": 0}
    for sample in selected:
        understanding[sample.understanding_level or "metadata_only"] = understanding.get(sample.understanding_level or "metadata_only", 0) + 1
    return {
        "selected_count": len(selected),
        "sample_count": len(sample_set.samples),
        "understanding": understanding,
        "with_video": sum(1 for sample in selected if sample.has_video),
        "with_keyframes": sum(1 for sample in selected if sample.has_frames),
        "with_asr": sum(1 for sample in selected if sample.has_asr),
        "with_ocr": sum(1 for sample in selected if sample.has_ocr),
        "with_comments": sum(1 for sample in selected if sample.has_comments),
        "confidence": (result.get("sample_overview") or {}).get("confidence") if isinstance(result.get("sample_overview"), dict) else "",
    }
