"""Creator Intelligence v2 service package.

The package is intentionally small at first. It provides stable domain
contracts and a workflow engine that legacy creator-clone code can adapt into
without changing the existing v1 user flow.
"""

from app.services.creator_intelligence.adapters import (
    project_from_clone_sample_set,
    project_from_clone_selection,
    samples_from_browser_dom,
    samples_from_case_import,
    samples_from_cookie_api,
    samples_from_json_csv,
    samples_from_manual_links,
)
from app.services.creator_intelligence.cognition import build_behavior_representation
from app.services.creator_intelligence.models import (
    BehaviorRepresentation,
    CreatorCloneStrategy,
    CreatorClone,
    CreatorProfile,
    CreatorProject,
    CreatorSample,
    Evidence,
    EvidenceBundle,
    EvidenceLevel,
    MediaKind,
    Platform,
    Sample,
    SampleSet,
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
    "CreatorClone",
    "CreatorProfile",
    "CreatorProject",
    "CreatorSample",
    "Evidence",
    "EvidenceBundle",
    "EvidenceLevel",
    "MediaKind",
    "Platform",
    "Sample",
    "SampleSet",
    "SampleMetrics",
    "WorkflowAction",
    "WorkflowEngine",
    "WorkflowSnapshot",
    "WorkflowState",
    "build_behavior_representation",
    "project_from_clone_sample_set",
    "project_from_clone_selection",
    "samples_from_browser_dom",
    "samples_from_case_import",
    "samples_from_cookie_api",
    "samples_from_json_csv",
    "samples_from_manual_links",
]
