# Creator Execution Pack v1

## Purpose

Creator Execution Pack extends the existing creator-intelligence chain by one
explicit Create step:

```text
Creator Report
-> Creator Strategy Plan
-> user selects one next_topic
-> Creator Execution Pack
```

The output answers a practical question: what should the user shoot next, how
should it open, what should each shot contain, and how should it be packaged for
publishing? It is a production-ready brief that the user can edit before
shooting. It is not a second creator analysis and does not replace the report or
Strategy Plan.

Generation is always user initiated through `用这个选题生成`. Completing a
report or generating a Strategy Plan never starts Execution Pack generation
automatically.

## Inputs

The service reads existing, persisted creator assets only:

- `samples.json`, limited to the selected representative samples;
- `creator_clone_result.json`, including `creator_clone_strategy`,
  `creator_report_view_model`, and `report_quality`;
- `creator_strategy_plan.json`, including `next_topics`, script and shot
  templates, title/cover suggestions, checklist, and low-confidence notes;
- the zero-based `topic_index` explicitly selected by the user.

It does not scan a profile, call Douyin, download media, run ASR/OCR, enrich a
Case, or repeat creator distillation. A valid Creator Report and Strategy Plan
are required; missing upstream assets return explicit not-ready errors rather
than silently generating them.

## API

Generate synchronously with the existing bounded LLM provider:

```http
POST /api/creator-intelligence/projects/{project_id}/generate-execution-pack
Content-Type: application/json

{"topic_index": 0}
```

Read the current persisted pack:

```http
GET /api/creator-intelligence/projects/{project_id}/execution-pack
```

Both successful responses use `Cache-Control: no-store`. Generation does not
create a `Job` and the page does not poll. The selected topic button has a local
busy state and is restored after success or failure.

Relevant errors:

- `CREATOR_REPORT_NOT_READY`
- `STRATEGY_PLAN_NOT_READY`
- `EXECUTION_TOPIC_INVALID`
- `EXECUTION_PACK_NOT_READY`
- existing shared LLM configuration, authentication, quota, timeout, upstream,
  and response-validation errors

## Output Contract

`CreatorExecutionPackV1` has `version: "1.0"` and the following stable top-level
fields:

```text
version
project_id
topic_index
generated_at
topic
creative_basis
hook
script
shot_plan
cover
titles
publish_copy
hashtags
editing_notes
production_checklist
evidence_refs
confidence
warnings
source
```

Important bounds:

- `shot_plan`: 4-10 concrete shots;
- script `beats`: 1-8;
- `titles`: 3-5 publishable candidates, not placeholders such as `标题1`;
- `hashtags`: 5-10;
- `production_checklist`: at least 5, at most 12;
- `evidence_refs`: at most 8;
- `confidence`: `high`, `medium`, or `low`.

The server owns `project_id`, `topic_index`, `generated_at`, `source`, and the
normalized topic. The model cannot replace the user-selected Strategy Plan
topic. A response with a different topic title fails schema validation; other
topic fields are replaced with the server-normalized selected topic.

## Evidence Rules

The prompt receives only bounded structured evidence and an allowlist of
selected `sample_id` values. The validator checks references against:

- selected representative sample IDs;
- exact Creator Report rule values;
- exact Strategy Plan values;
- the server-owned selected topic.

Unknown sample references are dropped. Unverifiable report/plan references are
dropped. The final pack records a warning when references are removed and never
persists a model-invented sample ID. At least the selected Strategy Plan topic
remains as a verified evidence reference.

`creative_basis` is also bounded. Representative samples must match selected
sample IDs, while creator rules, hook patterns, and formulas are checked against
the upstream catalogs when those catalogs are available.

The prompt explicitly forbids copying the original creator's exact title,
script, or person-specific material. It asks the model to transfer patterns,
not duplicate content.

## Partial Evidence

Partial enrichment is a supported state. For example, five enriched samples and
one failed sample do not block generation when the Creator Report and Strategy
Plan are ready.

The pack lowers confidence and adds warnings when:

- one or more selected samples failed enrichment;
- evidence is incomplete for some selected samples;
- `report_quality` is below 70;
- the Strategy Plan contains `low_confidence_notes`.

A report score below 70 or Strategy Plan low-confidence notes cap the pack at
`low`. Incomplete or failed sample evidence otherwise caps `high` at `medium`.
The UI displays `建议人工复核` but still allows the workflow to advance.

## LLM Bounds

Execution Pack reuses the existing runtime settings, provider, shared
`DistillDeadline`, error classification, and `LLMExecutionEngine`.

- total request budget: 180 seconds;
- one main logical generation request;
- at most one compact repair/retry;
- invalid JSON and retryable 502/503-style upstream failures may use that retry;
- 401, 403, 429, and quota failures are terminal and are not retried;
- no route-level retry and no persistent Job retry are added.

The output must pass strict JSON/schema validation. Missing production fields do
not receive invented server defaults; generation fails after the bounded repair
opportunity.

## Persistence

Without an iteration index, successful generation keeps the legacy path:

```text
outputs/creator_clones/{project_id}/creator_execution_pack.json
```

After the user starts a new iteration, the current Pack is stored at:

```text
outputs/creator_clones/{project_id}/iterations/{iteration_id}/creator_execution_pack.json
```

The file is UTF-8 JSON, atomically replaced with `os.replace`, and is fully
rebuildable from upstream assets plus a new user-triggered LLM call. Each
iteration stores one current Pack; regeneration safely overwrites that Pack and
does not modify:

- `samples.json`;
- `creator_clone_result.json`;
- `creator_strategy_plan.json`.

Output normalization removes external URLs, signed media URLs, local absolute
paths, Cookie/Authorization text, and OpenAI-style keys. `source` is a small
server-owned diagnostic summary containing filenames, counts, quality score,
topic index, and bounded attempt metadata only.

## UI

The feature remains inside the existing Creator Report / Strategy Plan area:

- every Strategy Plan topic exposes `用这个选题生成`;
- the local busy state locks all topic actions during the request;
- the result prioritizes topic, Hook, script, shot plan, cover, and titles;
- publishing, editing, and checklist sections remain directly readable;
- evidence and warnings are progressively disclosed under collapsed
  `为什么这样生成` details;
- `复制完整执行方案` produces plain text without a third-party library;
- the shot and support grids collapse to one column below 720 px.

An existing pack is read back when the Creator report is hydrated. Reading the
pack never calls the LLM.

## Non-goals

Creator Execution Pack v1 does not:

- generate an actual video or image;
- call TTS;
- edit or compose media;
- publish to Douyin or another platform;
- search real-time trends or hashtags;
- automatically select a topic;
- modify the Representative Selector;
- harden Douyin providers, CDN redirects, or the standalone Login Plugin.

Those concerns remain separate backlog items. v1 ends at an editable production
brief.

## Known Limitations

- `topic_index` is stable only for the current persisted Strategy Plan. GET
  rejects an existing pack when the selected topic at that index no longer
  matches, but v1 does not fingerprint every upstream field. A regenerated
  plan with the same title at the same index should still be followed by an
  explicit Execution Pack regeneration.
- One Execution Pack is current per Creator iteration. Creator Iteration History
  preserves closed rounds and exposes their Pack through a read-only history
  browser without changing the `CreatorExecutionPackV1` schema.
- Evidence matching is exact and intentionally conservative; paraphrased model
  references may be dropped even when semantically similar.
- The feature depends on the configured OpenAI-compatible provider and does not
  provide an offline deterministic execution-pack generator.
- No real LLM is called during automated development or tests.
