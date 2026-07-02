from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
from app.services.creator_intelligence.llm_execution import LLMExecutionEngine, LLMExecutionResult
from app.services.creator_intelligence.models import (
    BehaviorRepresentation,
    CreatorProject,
    CreatorSample,
    validate_creator_clone_schema,
)


@dataclass(frozen=True)
class ExecutionLayer:
    """Creator Intelligence execution facade.

    P5 keeps product behavior intact while making this the single runtime-facing
    gateway for ingestion normalization, feature extraction, and structured LLM
    generation. Existing adapter/cognition/LLM modules remain implementation
    details behind this layer.
    """

    def normalize_sample_set(self, sample_set: Any) -> CreatorProject:
        return project_from_clone_sample_set(sample_set)

    def normalize_selection(self, sample_set: Any, selected_samples: list[Any]) -> CreatorProject:
        return project_from_clone_selection(sample_set, selected_samples)

    def normalize_ingestion(self, source: str, items: list[dict[str, Any]]) -> tuple[CreatorSample, ...]:
        adapters = {
            "manual_links": samples_from_manual_links,
            "browser_dom": samples_from_browser_dom,
            "json_csv": samples_from_json_csv,
            "case_import": samples_from_case_import,
            "cookie_api": samples_from_cookie_api,
        }
        adapter = adapters.get(str(source or "").strip(), samples_from_json_csv)
        return adapter(items)

    def extract_behavior_model(self, project: CreatorProject) -> BehaviorRepresentation:
        return build_behavior_representation(project)

    def generate_creator_clone(
        self,
        provider: Any,
        prompt: str,
        image_paths: list[Path] | None = None,
        *,
        max_retries: int = 3,
    ) -> LLMExecutionResult:
        return LLMExecutionEngine(provider, max_retries=max_retries).execute_creator_clone(prompt, image_paths or [])

    def validate_strategy_output(self, value: dict[str, Any] | None) -> dict[str, Any]:
        return validate_creator_clone_schema(value or {})
