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

### M3: UI State-Driven Wizard

- Replace scattered button-driven state with `render(workflow_state)`.
- Keep visual layout familiar, but remove duplicated state calculations.

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

## Success Criteria

- One workflow state source controls the creator distillation flow.
- UI refresh can restore the current project without recomputing random frontend state.
- Samples, evidence, and creator clone output have stable contracts.
- LLM prompts are generated from a cognitive representation layer.
- Existing v1 capabilities remain usable while v2 internals become cleaner.
