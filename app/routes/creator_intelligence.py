from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.errors import AppError, ErrorCode
from app.routes.common import error_response
from app.services.creator_clone import (
    creator_intelligence_payload_for_sample_set,
    export_paths,
    load_sample_set,
)
from app.services.creator_intelligence import BehaviorRepresentation
from app.services.creator_intelligence import project_from_clone_sample_set
from app.services.creator_intelligence.dispatch import dispatch_creator_workflow


router = APIRouter(prefix="/api/creator-intelligence", tags=["creator-intelligence"])


class CreatorIntelligenceWorkflowDispatchRequest(BaseModel):
    action: str
    selected_sample_ids: list[str] = Field(default_factory=list)


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
    return {
        "ok": True,
        "project": project.to_dict(),
        "workflow": workflow or intelligence.get("workflow") or {},
        "behavior_model": behavior_payload or intelligence.get("behavior_model") or None,
        "strategy_output": strategy_output or intelligence.get("strategy_output") or None,
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
        result = dispatch_creator_workflow(
            project_id,
            payload.action,
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
