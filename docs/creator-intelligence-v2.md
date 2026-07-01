# Creator Intelligence Platform v2

## North Star

This project is no longer just a short-video analyzer, profile scanner, or prompt tool.

The v2 product goal is:

```text
Creator Intelligence System
= creator content -> structured cognition model -> strategy output
```

Engineering expression:

```text
Input -> Creator Behavior Model -> Strategy Output
```

## System Layers

### 1. Ingestion Layer

Purpose: convert creator content into normalized samples.

Current inputs:

- Douyin profile scan with optional cookie-assisted API.
- Browser DOM helper.
- Manual links.
- JSON / CSV style structured import.
- Existing case import.

Boundary:

- Do not add new crawler capabilities during v2 architecture work.
- Do not bypass platform risk control, captcha, or signing.
- Do not change the single-video parsing flow.

### 2. Cognitive Modeling Layer

Purpose: convert samples into understandable creator behavior representations.

Core objects:

- `CreatorProfile`: identity, audience, direction, style bias.
- `Sample`: source, metrics, media type, evidence level, processing status.
- `Evidence`: frames, OCR, ASR, comments, interaction signals.
- `BehaviorRepresentation`: performance segmentation, evidence matrix, topic buckets, hooks, visual patterns, expression patterns, validation notes.

This is the system's moat. The LLM should not receive raw mixed UI payloads directly; it should receive a structured cognitive representation.

### 3. Generation Layer

Purpose: convert structured cognition into creator strategy output.

The output must be schema-driven, not freeform prompt-driven:

```json
{
  "positioning": "",
  "content_strategy": [],
  "hooks": [],
  "templates": [],
  "anti_patterns": [],
  "idea_bank": [],
  "validation_rules": []
}
```

## Required v2 Architecture

### Workflow Engine

The workflow engine is the single source of truth.

The UI must not own workflow progress. The UI renders state and dispatches actions.

Recommended states:

```text
IMPORT
-> INGESTED
-> SAMPLE_READY
-> SAMPLE_SELECTED
-> EVIDENCE_READY
-> DISTILLING
-> DONE
```

Recommended API shape:

```text
get_state(project_id)
dispatch(action)
transition(event)
```

UI rule:

```text
UI = render(workflow_state)
```

### Unified Data Model

Current problem:

```text
profileItems / samples / case / payload / cloneResult
```

These are mixed across UI, API, and prompt construction.

v2 target:

```text
CreatorProject
CreatorProfile
Sample
Evidence
BehaviorRepresentation
CreatorClone
```

The same object names should be used consistently across service code, routes, templates, and JS view models.

### Structured Generation Engine

Current problem:

```text
data -> LLM
```

v2 target:

```text
sample data -> cognitive representation -> structured generation -> report
```

Prompt optimization should move toward schema contracts:

- fixed input contract
- fixed output schema
- validation and fallback
- report rendering from schema fields

## Non-Goals For This Branch

- Do not expand crawler/provider capabilities.
- Do not add new platform adapters.
- Do not change the single-work parsing flow.
- Do not bypass risk control, captcha, login, or platform signatures.
- Do not keep stacking UI-only fixes without aligning them to workflow state.
- Do not add TTS, subtitles, publishing, or generation modules.

## First Implementation Milestones

### M1: Architecture Map

- Add a workflow state model.
- Add normalized domain models without removing legacy fields yet.
- Add adapters that translate current `profileItems`, `samples`, and `case` payloads into the new model.

Initial code entry points:

- `app/services/creator_intelligence/models.py`
  - `CreatorProfile`
  - `CreatorSample`
  - `Evidence`
  - `BehaviorRepresentation`
  - `CreatorCloneStrategy`
- `app/services/creator_intelligence/adapters.py`
  - translates the current `CloneSampleSet` / `CloneSample` model into `CreatorProject`.

### M2: Workflow Engine Skeleton

- Introduce `WorkflowEngine`.
- Implement state transitions for the current creator distillation flow.
- Keep existing routes working, but have them read/write workflow state.

Initial code entry points:

- `app/services/creator_intelligence/workflow.py`
  - `WorkflowState`
  - `WorkflowAction`
  - `WorkflowEngine`
  - `WorkflowSnapshot`
- `app/services/creator_intelligence/cognition.py`
  - builds the first `BehaviorRepresentation` from normalized samples, metrics, and evidence.

Bridge into the existing API:

- `GET /api/creator-clone/sets/{set_id}` now returns `creator_intelligence.workflow`.
- When samples are selected, the same payload also returns `creator_intelligence.behavior_model`.
- `POST /api/creator-clone/sets/{set_id}/workflow` now accepts the first explicit workflow action: `SELECT_SAMPLES`.
- `GET /api/creator-intelligence/projects/{project_id}` exposes the v2 contract directly as `project`, `workflow`, `behavior_model`, and `strategy_output`.
- `POST /api/creator-intelligence/projects/{project_id}/workflow` provides the v2 workflow dispatch surface.
- Legacy creator-clone responses also include `creator_intelligence.project` so frontend code can migrate without losing the normalized project model.

### M3: UI State-Driven Wizard

- Replace scattered button-driven state with `render(workflow_state)`.
- Keep visual layout familiar, but remove duplicated state calculations.

Initial integration:

- Frontend wizard state now reads `creator_intelligence.workflow.ui.next_action`
  and `creator_intelligence.workflow.ui.stage`; local UI state is only a display
  fallback before a project exists.
- The primary button executes the engine-provided `next_action.command`
  (`import_input`, `select_recommended_samples`, `build_evidence`,
  `start_distillation`, `start_batch_distillation`, `export_report`) instead of
  branching on frontend-derived workflow states.
- Recommended selection, enrichment, and distillation entry points now sync selected samples through the workflow dispatch API before advancing.
- Recent project restore now reads `/api/creator-intelligence/projects/{project_id}` first, then adapts the v2 project payload into the existing table view while legacy UI is being retired.

### M4: Cognition Layer Contract

- Build `BehaviorRepresentation` from samples, evidence, metrics, and segmentation.
- Make LLM prompt builders consume this representation instead of raw mixed payloads.

Initial integration:

- Existing creator clone prompt builders now include a compact `BehaviorRepresentation` payload.
- Legacy prompt fields are still present for compatibility and can be removed in a later cleanup once rendering and tests rely on the v2 contract.

### M5: Structured Generation Contract

- Lock the `CreatorClone` output schema.
- Validate model output.
- Render public reports from schema, not from arbitrary markdown-like fields.

Initial integration:

- `normalize_creator_clone_result()` now always emits `creator_clone_strategy`.
- Legacy model outputs such as `creator_positioning`, `transferable_formulas`, `creator_clone_spec`, and `candidate_ideas` are mapped into the v2 strategy schema for backward compatibility.
- `GET /api/creator-clone/sets/{set_id}` restores workflow state as `DONE` when a saved strategy output exists.
- Sync and async distillation responses both return `creator_intelligence.strategy_output` when a strategy exists.
- The public report now renders the schema-driven `strategy_output` first, with legacy clone fields kept as fallback and supporting detail.
- Restoring a `DONE` project with saved `strategy_output` now reconstructs the report view immediately instead of requiring the user to rerun distillation.

## Success Criteria

- One workflow state source controls the creator distillation flow.
- UI refresh can restore the current project without recomputing random frontend state.
- Samples, evidence, and creator clone output have stable contracts.
- LLM prompts are generated from a cognitive representation layer.
- Existing v1 capabilities remain usable while v2 internals become cleaner.

## Current Completion Evidence

This section records the current branch state so the v2 refactor can be reviewed
against the North Star instead of judged as a collection of unrelated patches.

### Workflow Engine As Single State Contract

Implemented:

- `app/services/creator_intelligence/workflow.py` defines `WorkflowState`,
  `WorkflowAction`, `WorkflowSnapshot`, and `WorkflowEngine`.
- `app/services/creator_intelligence/dispatch.py` centralizes workflow action
  dispatch through `dispatch_creator_workflow()` for both new v2 routes and
  legacy creator-clone routes.
- `POST /api/creator-intelligence/projects/{project_id}/workflow` supports
  `SELECT_SAMPLES`, `MARK_EVIDENCE_READY`, and `START_DISTILLATION`.
- `POST /api/creator-clone/sets/{set_id}/workflow` remains available for legacy
  callers but delegates to the same dispatch service.

Verification:

- `tests/test_creator_intelligence_v2.py`
  - `test_workflow_engine_controls_creator_distillation_state`
  - `test_creator_intelligence_workflow_api_dispatches_selection`
  - `test_creator_intelligence_workflow_api_advances_evidence_and_distillation_state`
  - `test_creator_clone_legacy_workflow_endpoint_advances_distillation_state`
  - `test_shared_creator_workflow_dispatch_service_selects_samples`

### Unified Creator Project Model

Implemented:

- `CreatorProject`, `CreatorProfile`, `CreatorSample`, `Evidence`,
  `BehaviorRepresentation`, and `CreatorCloneStrategy` are stable domain
  objects in `app/services/creator_intelligence/models.py`.
- `app/services/creator_intelligence/adapters.py` converts the current
  `CloneSampleSet` / `CloneSample` storage model into a normalized
  `CreatorProject`.
- `CloneSampleSet` / `CloneSample` are retained as legacy on-disk DTOs only;
  v2 workflow, cognition, and strategy output cross the boundary through
  `project_from_clone_sample_set()` / `CreatorProject`.
- Legacy response payloads now include `creator_intelligence.project`.
- Frontend view-model helpers adapt old `set` payloads into `CreatorProject`
  and prefer `CreatorProject.samples` over the legacy `profileItems` array.
- Queue evidence updates are synced back into the frontend `CreatorProject`
  view model.

Verification:

- `tests/test_creator_intelligence_v2.py`
  - `test_clone_sample_set_adapts_to_creator_project`
  - `test_creator_clone_set_endpoint_exposes_creator_intelligence_state`
  - `test_creator_intelligence_project_api_exposes_v2_contract`
- `tests/test_p0_workflow.py`
  - static frontend assertions for `creatorProjectFromCloneSet`,
    `activeProfileItems`, and `syncCreatorProjectSamplesFromProfileItems`.

### Cognitive Modeling Layer

Implemented:

- `app/services/creator_intelligence/cognition.py` builds
  `BehaviorRepresentation` from selected samples, media mix, evidence matrix,
  performance segments, and evidence constraints.
- Creator clone prompt builders include the compact behavior representation so
  the LLM path is no longer only raw UI data -> LLM.
- Enrichment jobs now return `creator_intelligence.behavior_model` when a
  sample set is updated with case evidence.

Verification:

- `tests/test_creator_intelligence_v2.py`
  - `test_behavior_representation_builds_evidence_and_segments`
  - `test_selection_adapter_keeps_behavior_model_scoped_to_selected_samples`
- `tests/test_p0_workflow.py`
  - `test_profile_build_cases_queue_backfills_asr_ocr_evidence_into_sample_set`

### Structured Generation Contract

Implemented:

- `CreatorCloneStrategy.empty_schema()` defines the v2 strategy contract:
  `positioning`, `content_strategy`, `hooks`, `templates`, `anti_patterns`,
  `idea_bank`, and `validation_rules`.
- All creator distillation prompt variants now include the stable
  `CreatorCloneSchema` contract and state that the workflow/public report only
  trusts `creator_clone_strategy`.
- `normalize_creator_clone_result()` always emits `creator_clone_strategy`,
  mapping legacy model fields into the schema.
- Schema-first model responses that return only `creator_clone_strategy` are
  accepted and restored as `creator_intelligence.strategy_output`.
- Sync and async distillation success responses return
  `creator_intelligence.strategy_output`.
- Prompt-only recovery responses also return `creator_intelligence`, so the UI
  can keep a stable project/workflow/behavior contract even without model output.
- The public report renders strategy output first and keeps legacy sections as
  compatibility detail.

Verification:

- `tests/test_creator_intelligence_v2.py`
  - `test_creator_clone_result_exposes_structured_strategy_contract`
- `tests/test_p0_workflow.py`
  - `test_creator_clone_distill_accepts_schema_first_llm_output`
  - `test_creator_clone_distill_with_mock_llm_saves_visual_result`
  - `test_creator_clone_distill_job_with_mock_llm_saves_visual_result`
  - `test_creator_clone_distill_job_unconfigured_returns_prompt`

### State-Driven Frontend Wizard

Implemented:

- The creator distillation wizard renders from
  `creator_intelligence.workflow.ui.stage`, `ui.step_label`, and
  `ui.next_action`; legacy helper names remain as read-only compatibility
  aliases.
- `renderCreatorCloneNextAction()` and `handleWizardPrimaryAction()` now read
  `next_action.command` as the action contract, so JS no longer decides whether
  evidence, direct distillation, batch distillation, or export should be next.
- Old frontend-only action states such as `POOL_EMPTY`, `SELECT_TO_ENRICH`,
  `SELECT_TO_DISTILL`, `ENRICH_EMPTY`, `ENRICH_DONE`, and `EXPORT_EMPTY` are
  no longer present in the main script.
- Selection, enrichment, single distillation, and batch distillation paths
  dispatch workflow actions before changing major UI stages.
- Recent project restore reads `/api/creator-intelligence/projects/{project_id}`
  and reconstructs table/report state from v2 payloads.
- Completed strategy reports restore without rerunning the LLM.

Verification:

- `tests/test_p0_workflow.py`
  - static assertions for `dispatchCreatorIntelligenceWorkflowAction`,
    `markCreatorCloneDistillationStarted`, `profilePayloadFromCreatorIntelligenceProject`,
    retired v1 action states, and restored `DONE` report rendering.
- `tests/test_creator_intelligence_v2.py`
  - `test_cookie_runtime_settings_do_not_change_creator_workflow`

### Async Job Contract Alignment

Implemented:

- `profile-build-cases` success results include `creator_intelligence` when a
  sample set is available.
- `creator-clone-distill` success results include `strategy_output` and
  `DONE` workflow state.
- `creator-clone-distill` prompt-only recovery results include
  `creator_intelligence` with the selected sample workflow state.
- `creator-clone-batch-distill` results include the same v2 payload contract.

Verification:

- `tests/test_p0_workflow.py`
  - profile build queue tests for enriched evidence payloads.
  - distillation job tests for success and prompt-only recovery payloads.

### Compatibility Boundary

Preserved:

- Existing creator-clone endpoints remain callable.
- `app/services/creator_clone.py` is now documented as the legacy persistence
  and compatibility layer for existing sample-set files.
- `app/services/creator_intelligence/{models,adapters,cognition,workflow}.py`
  do not import the legacy creator-clone DTO module; only
  `creator_intelligence.dispatch` crosses the boundary to coordinate persisted
  sample-set state.
- Existing single-work parsing and case analysis flows are not changed by this
  branch.
- No new crawler/provider capability is introduced.
- No risk-control, captcha, signing, or login bypass behavior is added.

Remaining cleanup after this branch:

- Retire remaining legacy frontend names such as `profileItems` once the UI no
  longer needs compatibility adapters.
- Persist all transient workflow transitions if a future product decision needs
  resumable `DISTILLING` state across server restarts.
- Move remaining compatibility prompt details out of `creator_clone.py` once
  older report fields are no longer needed.
