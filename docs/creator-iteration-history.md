# Creator Iteration History v1

## Problem

The Creator Intelligence workflow already covers:

```text
Observe -> Understand -> Distill -> Create -> Execute -> Measure
```

Before this change, a Creator project had one root-level Execution Pack, one
Execution Record, and one Outcome Timeline. A second production cycle would
replace the first cycle's current artifacts instead of preserving it as an
independent historical round.

## Product Goal

Creator Iteration History makes the production loop repeatable while keeping
the Creator analysis stable:

```text
Creator project
|- Creator Report
|- Strategy Plan
|- samples
|- iteration 1: Pack -> Record -> Outcome
|- iteration 2: Pack -> Record -> Outcome
`- iteration N: Pack -> Record -> Outcome
```

Starting a new iteration records a new writable storage context. It does not
select a topic, generate a Pack, create a Job, or call an LLM.

## Asset Ownership

Project-level assets remain in the Creator project root:

- `samples.json`
- `creator_clone_result.json`
- `creator_strategy_plan.json`
- Creator report HTML and Markdown
- other existing Creator project metadata

Iteration-level assets are:

- `creator_execution_pack.json`
- `creator_execution_record.json`
- `creator_outcome_snapshots.json`

The three artifact schemas remain version `1.0` and do not gain an
`iteration_id` field. Iteration identity belongs to the index and storage path.

## CreatorIterationIndexV1

The optional index is stored at:

```text
outputs/creator_clones/{project_id}/creator_iterations.json
```

Its version is `1.0` and it contains:

```json
{
  "version": "1.0",
  "project_id": "clone_example",
  "current_iteration_id": "iteration_0123456789abcdef0123456789abcdef",
  "iterations": [],
  "created_at": "2026-08-24T00:00:00+00:00",
  "updated_at": "2026-08-24T00:00:00+00:00"
}
```

The index is limited to 128 iteration references and 256 KiB. Identifiers,
sequence ordering, state, storage mode, timestamps, current identity, and the
single-active-iteration invariant are validated on every read. Invalid JSON or
an invalid invariant fails closed with `ITERATION_INDEX_INVALID`; the service
does not silently fall back to root storage.

## CreatorIterationRefV1

Each reference contains:

- `iteration_id`
- `sequence`
- `storage_mode`
- `state`
- `created_at`
- `closed_at`
- `close_reason`
- `close_note`
- `legacy_created_at_inferred`

New IDs are server-generated as `iteration_` plus 32 lowercase UUID v4 hex
characters. The fixed compatibility ID is `iteration_legacy_001`.

Storage modes are `legacy_root` and `iteration_dir`. States are `active` and
`closed`. Close reasons are `execution_completed`, `execution_archived`,
`cancelled`, `superseded`, `not_published`, and `other`.

An active reference has no close timestamp, reason, or note. A closed reference
has a timezone-aware close timestamp and a valid reason. Close notes are limited
to 500 characters and redact credential assignments, bearer values, OpenAI-style
keys, URLs, and local absolute paths.

## Virtual Legacy Behavior

If the index does not exist but any legacy root artifact exists, read operations
represent the root as a virtual active iteration:

```text
iteration_id = iteration_legacy_001
sequence = 1
storage_mode = legacy_root
```

If neither the index nor a root artifact exists, the list is empty and there is
no current iteration in the history DTO. Current artifact APIs still resolve to
the root so the first Pack can be generated through the existing workflow.

GET list, detail, and artifact requests do not create the index, directories, or
files. Virtual legacy is an in-memory compatibility view.

## Non-destructive Materialization

The index is materialized only by an explicit `start-next` write. When legacy
artifacts exist, the write:

1. records a `legacy_root` reference;
2. closes that reference;
3. adds a new active `iteration_dir` reference;
4. points `current_iteration_id` to the new reference;
5. atomically writes the index.

It does not move, copy, delete, or rewrite any legacy artifact. It does not
create an `iterations/iteration_legacy_001/` directory. The legacy creation time
is inferred from the earliest valid server-owned Pack, Record, or Outcome
timestamp. If none is available, current UTC is used and the summary marks the
time as inferred.

No real output migration is performed by this PR.

## Storage Layout

Legacy artifacts retain their original locations:

```text
outputs/creator_clones/{project_id}/creator_execution_pack.json
outputs/creator_clones/{project_id}/creator_execution_record.json
outputs/creator_clones/{project_id}/creator_outcome_snapshots.json
```

New iteration artifacts use:

```text
outputs/creator_clones/{project_id}/iterations/{iteration_id}/
  creator_execution_pack.json
  creator_execution_record.json
  creator_outcome_snapshots.json
```

The new iteration directory is created lazily by the first artifact write.

## Current Resolver

Existing current APIs keep their URLs and request bodies. Internally they resolve
one immutable `IterationStorageContext` containing project, iteration, sequence,
storage mode, base directory, current status, and index revision.

- no index: current paths remain the Creator root;
- indexed `legacy_root`: current paths remain the Creator root;
- indexed `iteration_dir`: current paths share that registered iteration folder.

Explicit historical resolution accepts only an iteration registered in the
validated index. The sole no-index exception is virtual
`iteration_legacy_001` when a root artifact exists. Path traversal, unregistered
directories, invalid IDs, and symbolic-link artifacts are rejected.

## Start-next Lifecycle

The endpoint is:

```text
POST /api/creator-intelligence/projects/{project_id}/iterations/start-next
```

When the current Record is `completed` or `archived`, it closes naturally with
`execution_completed` or `execution_archived`. If the Record is absent, `draft`,
or `in_progress`, the request must explicitly set `close_current=true` and choose
`cancelled`, `superseded`, `not_published`, or `other`.

The whole index transition runs under one process-local re-entrant lock. Repeated
or concurrent local requests can create at most one next iteration; the second
request observes the new unfinished current iteration and is rejected. At the
128-iteration limit the existing index is left unchanged.

## Operation Context Pinning

Execution Pack generation pins its context before loading generation inputs and
before the potentially long LLM request. Record and Outcome writes also pin a
context before reading their upstream artifact. Immediately before every atomic
artifact write, the service checks that the pinned context is still the current
context with the same index revision.

If another request starts a new iteration in between, the write is rejected with
`ITERATION_CONTEXT_CHANGED`. The result is written to neither the old iteration
nor the new one. The user can explicitly repeat the operation in the latest
iteration.

## Historical Read-only Behavior

Historical detail reads persisted artifacts with standalone schema validation:

- Pack validation does not rebind to the current Strategy Plan or sample set;
- Record validation uses its own schema and project identity;
- Outcome validation uses its own schema and preserves `null` versus `0`.

One missing or invalid artifact does not break the whole iteration list. The
availability value is `ready`, `missing`, or `invalid`. Historical routes expose
GET only; there is no historical POST, PATCH, DELETE, or switch-to-current API.

## API

```text
GET  /api/creator-intelligence/projects/{project_id}/iterations
GET  /api/creator-intelligence/projects/{project_id}/iterations/{iteration_id}
GET  /api/creator-intelligence/projects/{project_id}/iterations/{iteration_id}/artifacts/{artifact_name}
POST /api/creator-intelligence/projects/{project_id}/iterations/start-next
```

Allowed artifact names are `execution-pack`, `execution-record`, and `outcome`.
Successful responses use `Cache-Control: no-store`. The list includes a
server-owned `current_policy`; the browser does not duplicate the complete close
decision logic.

## UI

The Creator report and Strategy area includes a compact current-iteration header,
a server-policy-driven `Start next iteration` form, and a collapsed history list.
Starting a new round keeps the Creator Report, Strategy Plan, project identity,
and sample pool, while clearing the page's current Pack, Record, and Outcome.

Historical details reuse existing renderers in explicit read-only mode. They do
not show execution, feedback, publication, snapshot creation, or snapshot edit
controls. Unknown metrics render as an em dash; an observed zero renders as `0`.
The module uses direct requests and no polling loop.

## Persistence and Security

Index writes use a same-directory temporary file, UTF-8 encoding, flush, file
`fsync`, `os.replace`, temporary cleanup, and a directory `fsync`. A failed
replace preserves the previous index. Identifier and symbolic-link checks run
before path use.

The index does not store Cookie, Authorization, API keys, Login State, request
headers, local paths, media URLs, prompts, or model responses. API errors expose
safe error codes rather than paths or tracebacks. Tests use isolated temporary
output and SQLite directories.

## Legacy Compatibility

The existing Pack, Record, and Outcome API URLs are unchanged and operate on the
current iteration. Without an index they retain the exact root layout used by
PRs #25, #26, and #27. Their artifact schemas, LLM timeout contract, Record
lifecycle, publication gate, snapshot limit, storage limit, and missing-versus-zero
semantics are unchanged.

## Real-data Safety

Development and automated tests do not run `start-next` against real Creator
projects. They do not create a real `creator_iterations.json`, call a real LLM,
scan Douyin, download media, read Login State, or write real Outcome values.

## Single-process Lock Limitation

Write coordination is local to one Python process. It is suitable for the current
local-first single-process runtime. Multiple web workers would require a shared
filesystem or distributed lock before enabling concurrent iteration writes.

## Non-goals

v1 does not implement learning reviews, automatic Strategy optimization,
automatic topic selection, automatic Pack generation, cross-iteration charts,
cross-Creator comparisons, automatic metrics collection, publishing, media
generation, provider or CDN hardening, Login Plugin changes, or database
migrations.

## Known Backlog

- shared locking for multiple workers;
- cross-iteration comparison and learning review;
- an explicit retention/export policy after the 128-iteration bound;
- Library-level top cards for individual iterations, if later product research
  shows that the Creator-local history browser is insufficient.
