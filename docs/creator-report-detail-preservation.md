# Creator formula and idea detail preservation

Base: `51293c4a6f33588c670fcabb9cfc69eac8f88317` (main and origin/main at task start).
This change does not use PR #29 or #30 code and makes no Prompt/model calls.

## Trace and root cause

| Layer | Formulas | Candidate ideas |
| --- | --- | --- |
| Existing real saved business JSON | Complete objects in `transferable_formulas` | Complete mixed strings/objects in `candidate_ideas` |
| Normalization and persistence | Root objects preserved; strategy may separately contain short `text` templates | Root objects preserved; strategy may separately contain short ideas |
| Re-read through existing set API | Objects still present | Objects still present |
| View model | `_report_text_values` combines templates first and truncates to 180 characters / limited rows | Combines idea bank first and truncates to 160 characters / limited rows |
| Old page | Uses short sections; detail renderer prefers templates and fails to recognize `{text: ...}` | Uses short sections, flattening requirements and Boolean confidence into a sentence |
| Old Markdown/HTML export | Uses the same shortened section, losing tail information | Uses the same shortened section |

The private candidate's raw model business JSON was compared with its saved JSON:
both fields are equal. The original report's raw model response was not available;
only its complete saved fields can be verified. This does not establish that no
other historical content was lost before saving.

## Small repair

The original raw fields and short view model remain intact. No global truncation,
request preparation, normalization, Strategy Plan or Execution Pack contract changes.

The formula and idea sections now use this same-report precedence on page and export:

1. `transferable_formulas` / `candidate_ideas` in the current result.
2. `creator_clone_strategy.templates` / `idea_bank` in that result.
3. Existing root `templates` / `idea_bank` compatibility fields.
4. Saved view-model `sections.formulas` / `next_ideas`, explicitly labeled as
   possibly shortened compatibility suggestions, not recovered model originals.

Empty objects/lists do not suppress the next valid source. No active global strategy
is used to supply another report's details. Sources are not semantically merged,
rewritten or deduplicated by title; order and all selected-source rows are retained.

On the page, a named method/idea is a collapsed native `details` with full labeled
values inside. Lists remain lists; objects remain readable labeled groups; Boolean
values use yes/no labels. Unknown extension fields remain in details. Name-only
records remain name-only, without invented steps. Missing records say the current
saved record does not provide complete content, not that the model never generated it.

Markdown and its existing portable HTML export include the same full fields rather
than the short sections. Exports remain complete expanded documents; no new format
or rebuild endpoint is introduced. Model strings are HTML-escaped as before.

Detail reading is bounded to 2 MiB serialized JSON (the existing asset library result
bound), 8 levels and 10,000 nodes. Oversized/invalid details show an explicit notice
and do not alter saved originals. Other request/log/summary limits remain unchanged.

## Verification

- Formal mocked generation -> normalization -> saved result -> existing set GET ->
  mounted report component -> Markdown and HTML export preserves long step, risk,
  metric, reference and extension tail sentinels.
- Repeated normalization preserves the two fields, with no duplicate addition.
- Name-only, `{text: ...}`, empty/new-field fallback, stale global strategy,
  HTML escaping and size/depth boundaries covered.
- Full main-based suite: **656 passed**, one existing Starlette deprecation warning.
- Changed frontend and test-runner syntax checks, compileall and diff checks pass.
- Two private real saved reports processed through the base/fix normalization,
  persistence and existing set API before mounting their components. No model calls.
- Private previews preserve the same summary, positioning and chapter text at
  1280px and 390px, zoom 100%. New details are expandable and wrap within their cells.

## Deliberately unchanged

The old full-page mobile hero/two-column issues, quality wording, repeated sample
cards, and generic execution fallback behavior are not fixed here. Previously
saved truncated strings cannot be reconstructed when no full same-report source
exists. This patch restores access to existing content, not analysis quality.

No raw reports, model responses, Prompts or personal screenshots are committed.
8765 remains on main. User product review is pending; this PR remains Draft.
