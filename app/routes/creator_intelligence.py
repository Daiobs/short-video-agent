from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.errors import AppError, ErrorCode
from app.routes.common import error_response
from app.services.creator_clone import (
    creator_intelligence_payload_for_sample_set,
    export_paths,
    load_sample_set,
    normalize_sample_set_selected_ids,
    update_sample_set_selection,
)
from app.services.creator_intelligence import WorkflowAction, WorkflowEngine, project_from_clone_sample_set


router = APIRouter(prefix="/api/creator-intelligence", tags=["creator-intelligence"])


class CreatorIntelligenceWorkflowDispatchRequest(BaseModel):
    action: str
    selected_sample_ids: list[str] = Field(default_factory=list)


def project_payload_for_sample_set(sample_set) -> dict:
    project = project_from_clone_sample_set(sample_set)
    intelligence = creator_intelligence_payload_for_sample_set(sample_set)
    return {
        "ok": True,
        "project": project.to_dict(),
        "workflow": intelligence.get("workflow") or {},
        "behavior_model": intelligence.get("behavior_model") or None,
        "strategy_output": intelligence.get("strategy_output") or None,
        "exports": export_paths(sample_set.set_id),
    }


@router.get("/projects/{project_id}")
def get_creator_intelligence_project(project_id: str):
    try:
        sample_set = load_sample_set(project_id)
        return project_payload_for_sample_set(sample_set)
    except AppError as error:
        return error_response(error)


@router.post("/projects/{project_id}/workflow")
def dispatch_creator_intelligence_workflow(project_id: str, payload: CreatorIntelligenceWorkflowDispatchRequest):
    try:
        action = WorkflowAction(payload.action)
        if action != WorkflowAction.SELECT_SAMPLES:
            raise AppError(ErrorCode.PROFILE_SCAN_FAILED, f"当前仅支持 {WorkflowAction.SELECT_SAMPLES.value} workflow action。")
        sample_set = load_sample_set(project_id)
        selected_sample_ids = normalize_sample_set_selected_ids(sample_set, payload.selected_sample_ids)
        engine = WorkflowEngine.from_project(project_from_clone_sample_set(sample_set))
        engine.dispatch(action, {"selected_sample_ids": selected_sample_ids})
        sample_set = update_sample_set_selection(project_id, selected_sample_ids)
        return project_payload_for_sample_set(sample_set)
    except ValueError as error:
        return error_response(AppError(ErrorCode.PROFILE_SCAN_FAILED, str(error)))
    except AppError as error:
        return error_response(error)
