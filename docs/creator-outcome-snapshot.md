# Creator Outcome Snapshot v1

## Purpose

Creator Outcome Snapshot adds the Measure step to the local Creator Intelligence workflow:

```text
Observe -> Understand -> Distill -> Create -> Execute -> Measure
```

It records the real, manually observed performance of one published execution. It does not judge success, call an LLM, alter the Creator Report, or regenerate a Strategy Plan.

## Relationship to Execution Record

An existing `CreatorExecutionRecordV1` is required. A Timeline can be created only when:

```text
production_status.publishing == completed
```

`publishing=skipped` is not a published outcome and is rejected. The whole Execution Record does not need to have `status=completed`.

At creation, the Outcome copies these server-owned values from the Record:

- `project_id`
- `execution_record_created_at`
- `execution_pack_generated_at`
- `execution_pack_topic_index`
- `selected_topic`

Clients cannot set them. Later feedback edits or Execution Pack regeneration do not rebind an existing Outcome.

## Timeline Schema

`CreatorOutcomeTimelineV1` uses version `1.0`:

```json
{
  "version": "1.0",
  "project_id": "clone_example",
  "execution_record_created_at": "2026-08-10T01:05:00+00:00",
  "execution_pack_generated_at": "2026-08-10T01:00:00+00:00",
  "execution_pack_topic_index": 3,
  "selected_topic": "同一妆造三种状态",
  "expected_metric": "停留与评论",
  "publication": {},
  "snapshots": [],
  "warnings": [],
  "summary": {},
  "created_at": "2026-08-10T02:00:00+00:00",
  "updated_at": "2026-08-10T02:00:00+00:00"
}
```

Snapshots are stored in ascending `captured_at` order. The Timeline is limited to 64 snapshots and 512 KiB.

## Snapshot Schema

Each `CreatorOutcomeSnapshotV1` contains:

```json
{
  "snapshot_id": "snapshot_0123456789abcdef0123456789abcdef",
  "captured_at": "2026-08-10T02:10:00+00:00",
  "source": "manual",
  "metrics": {
    "views": 1000,
    "likes": 100,
    "comments": 10,
    "shares": null,
    "collects": 20
  },
  "derived": {}
}
```

The server generates `snapshot_id`, timezone-aware UTC `captured_at`, `source`, and every derived field. v1 accepts only the server-owned source `manual`.

## Missing-vs-zero Semantics

`null` and `0` have different meanings and remain distinct through requests, persistence, GET, PATCH, and UI rendering:

- `null`: unknown, unavailable, or not entered;
- `0`: explicitly observed as zero.

The UI sends blank inputs as `null`, sends a typed `0` as numeric zero, renders unknown values as `—`, and renders zero as `0`.

## Derived Metrics

The server calculates deterministic metrics without LLM interpretation:

- `known_interactions`: sum of known values among likes, comments, shares, and collects;
- `known_interaction_metric_count`: number of known interaction fields, from 0 through 4;
- `like_rate`, `comment_rate`, `share_rate`, `collect_rate`: calculated only when views are greater than zero and that metric is known;
- `engagement_rate`: calculated only when views are greater than zero and all four interaction values are known.

Rates are stored as floats from 0 to 1. The UI formats them as percentages. It never renders `NaN%` or `Infinity%`.

## Delta Behavior

`delta_from_previous` is calculated independently for views, likes, comments, shares, and collects. A delta exists only when the value is known in both adjacent snapshots. Negative deltas are valid because platform cleanup, correction, rollback, and changed counting rules can reduce a metric.

Correcting a snapshot deterministically recomputes the Timeline, including the following snapshot's delta.

## Publication Identity

Publication fields are manual identity metadata:

- `platform`: `douyin`, `xhs`, `bili`, or `other`;
- `platform_item_id`: optional, maximum 160 characters;
- `published_url`: optional public HTTPS URL;
- `published_at`: optional timezone-aware ISO-8601 timestamp.

The server never requests, resolves, follows, or probes `published_url`. URLs with credentials, local/private hosts, signed media hosts, sensitive query parameters, or non-HTTPS schemes are rejected.

## Execution Pack Binding

At Outcome creation, the current `creator_execution_pack.json` may provide `topic.expected_metric` only when both identity fields exactly match the Execution Record:

```text
Pack.generated_at == Record.execution_pack_generated_at
Pack.topic_index == Record.execution_pack_topic_index
```

If the Pack changed, `expected_metric` remains empty and `warnings` includes `execution_pack_changed_since_record`. The service does not guess or copy a metric from the new Pack.

## API

Create or update publication information, idempotently:

```text
PUT /api/creator-intelligence/projects/{project_id}/outcome
```

Read the Timeline:

```text
GET /api/creator-intelligence/projects/{project_id}/outcome
```

Append a manual snapshot:

```text
POST /api/creator-intelligence/projects/{project_id}/outcome/snapshots
```

Correct snapshot metrics without changing identity or capture time:

```text
PATCH /api/creator-intelligence/projects/{project_id}/outcome/snapshots/{snapshot_id}
```

Successful responses use `Cache-Control: no-store`. There is no DELETE endpoint, Job, polling loop, scheduler, retry, or background worker.

## Persistence

The Timeline is stored beside existing Creator artifacts:

```text
outputs/creator_clones/{project_id}/creator_outcome_snapshots.json
```

Writes use UTF-8 JSON, a temporary file in the same directory, `flush`, `fsync`, and `os.replace`. Outcome operations do not modify:

- `creator_execution_pack.json`
- `creator_execution_record.json`
- `creator_strategy_plan.json`
- `creator_clone_result.json`
- `samples.json`

## Security

Project and snapshot identifiers are validated before constructing a path. API responses and persistence do not include Cookie, Authorization, Bearer values, API keys, Login State, local absolute paths, signed media URLs, request headers, or provider response bodies.

The explicitly entered public `published_url` is preserved after validation. No network operation is performed for that URL, so the feature does not add an SSRF request path.

## Manual-only v1

All publication details and metrics are entered manually. v1 does not read Douyin, Xiaohongshu, or Bilibili publishing data and does not verify whether a metric is authentic.

## Future Provider Seam

The service-level append operation is independent of the UI and reserves server-owned `source`. A future authorized outcome collector can append through the same validation and derivation path with a new source type. No provider is implemented in v1.

## Non-goals

Creator Outcome Snapshot v1 does not:

- call an LLM or produce a Learn decision;
- change Creator Strategy, Creator Report, representative samples, or Execution Pack;
- scan profiles, download media, enrich evidence, or run ASR/OCR;
- publish content or collect platform metrics automatically;
- add charts, snapshot deletion, queues, retries, or schedulers;
- address CDN allowlisting, Provider hardening, Login Plugin maintenance, or multi-process locking.

## Known Limitations

- Write coordination uses a process-local lock and is intended for the current local-first, single-process runtime.
- One Timeline is stored per Creator project and remains bound to its original Execution Record identity.
- Snapshot deletion is intentionally unavailable; corrections use PATCH.
- Manual values are not independently verified.
- `expected_metric` is displayed as source text and is not automatically scored against observed metrics.
