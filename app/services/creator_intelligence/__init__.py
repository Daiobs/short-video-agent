"""Creator Intelligence v2 service package.

The package is intentionally small at first. It provides stable domain
contracts and a workflow engine that legacy creator-clone code can adapt into
without changing the existing v1 user flow.
"""

from app.services.creator_intelligence.adapters import project_from_clone_sample_set, project_from_clone_selection
from app.services.creator_intelligence.cognition import build_behavior_representation
from app.services.creator_intelligence.models import (
    BehaviorRepresentation,
    CreatorCloneStrategy,
    CreatorProfile,
    CreatorProject,
    CreatorSample,
    Evidence,
    EvidenceLevel,
    MediaKind,
    Platform,
    SampleMetrics,
)
from app.services.creator_intelligence.workflow import (
    WorkflowAction,
    WorkflowEngine,
    WorkflowSnapshot,
    WorkflowState,
)

__all__ = [
    "BehaviorRepresentation",
    "CreatorCloneStrategy",
    "CreatorProfile",
    "CreatorProject",
    "CreatorSample",
    "Evidence",
    "EvidenceLevel",
    "MediaKind",
    "Platform",
    "SampleMetrics",
    "WorkflowAction",
    "WorkflowEngine",
    "WorkflowSnapshot",
    "WorkflowState",
    "build_behavior_representation",
    "project_from_clone_sample_set",
    "project_from_clone_selection",
]
