# Creator existing material inputs v1

Base: `78359d59dd9b7606e5825f2cf6a010aca1134798` (main including PR #31).

## What changed

| Stage | Before | Now |
| --- | --- | --- |
| Case archive | ASR/OCR/comment files and prior single analysis existed | Same files, read only; no new enrichment |
| Local Map | Brief analysis and some evidence excerpts | Fresh selected local Map plus versioned material excerpts; no old cache reused |
| Reduce / micro | Reduce replaced evidence with flags; micro dropped it | Shared bounded material section by sample ID |
| Normal / compact | Raw report plus Markdown duplication, or omitted on retry | Same labelled text section, not an entire report dump |
| Provider images | Always `[]` for Creator | Verified contact sheet, else existing keyframe; explicit 1-based sample mapping |
| Final Reduce | Batch sample IDs truncated to eight | Up to the actual 20 per batch, explicitly secondhand summaries, no direct images |

The main analysis instructions, classification guidance, output schema,
normalization, renderer and PR #31 formula/idea details are unchanged. The small
input note distinguishes transcription, OCR, comments, prior analysis, static
images and inventory status. It does not prescribe new report sections.

## Input contract and bounds

Only selected samples' assigned Case directories are eligible. The local input
collector validates IDs, containment and symlinks, bounds JSON to 2 MiB / depth
24 and JSONL to 100 inspected lines (16 KiB per line), and reuses the existing
execution-record text sanitizer. It never loads a Creator report as sample
evidence. Original enrichment files take precedence; explicitly saved
`analysis_input.analysis_enrichment` is a same-Case fallback.

The formal paths all use compact per-sample content budgets: ASR 400 characters,
OCR 500, comments 400, prior analysis 800. Structural keys/status are additional.
Each sample receives its own allowance, so the twentieth is not starved by the
first. Per-request limits follow the existing 20-sample batch cap. Long content
is sliced as text fields, not serialized JSON. Truncation/omission is recorded.
ASR timestamps are retained when recorded, OCR stays separate, comments need
semantic text rather than counts/status/notes, and prior analysis is labelled
secondhand. Local fallback observations are excluded. Missing metric flags are
preserved separately from measured zero, without changing ranking or storage.

Images are validated JPEG/PNG/WebP, <=3 MiB and <=12M pixels, at most six per
request (or a smaller configured/provider limit). Provider-encoded Base64 is
checked against 4 MiB per image and 8 MiB per request. Invalid/missing images are skipped with
a safe status, without adding downloads, frame extraction or model calls.
The existing Provider serializes images as image data, not localhost URLs.
Explicit `supports_images=False` keeps a text-only request. Transport support
does not prove an arbitrary gateway model understands images.

## Persistence, retries and scope

`result.request_materials` records only sample IDs, source kinds/status,
submitted text character counts, omissions, image order and successful attempt.
It contains no prompt, private paths, image Base64 or credentials. It describes
the successful logical attempt, not the union of previous failed attempts.
Historical reports are not backfilled. Batch results carry their own material
scope; the final result records batch-summary provenance and zero direct images.

Quick timeout does not retry. Existing bounded compact retry/error/deadline
contracts are unchanged. No new per-sample LLM calls, provider protocol, model,
waiting policy, configuration schema or production service changes.

## Verification and product comparison

Synthetic tests capture the actual serialized Provider request through mock
HTTPX transport, including data images, sample binding, micro/normal/Deep,
compact retry, batch/final separation, terminal errors, old Map cache,
missing/zero semantics, long inputs, and save/reload/PR #31 exports.
Existing backfill coverage now checks the labelled structured analysis instead
of requiring duplicate Markdown. The short metadata-only micro bound includes
the new provenance section (6,000 rather than 5,000 characters).

Private real-input comparison and any one authorized generation are recorded
outside Git. The comparison freezes five selected samples and archives the
historical memory; the report being compared is not fed back as input. Since
the original report's historical context cannot be reproduced exactly, this is
a same-material comparison, not a controlled proof of general model quality.
Isolated acceptance may use main-supported 300/360-second request/Quick budgets;
daily settings and 8765 remain unchanged.

Mock/full regression: 677 passed, one existing Starlette warning. JavaScript
syntax (unchanged app/renderer), compileall and diff checks pass. The real-input
dry construction has 8,800 prompt characters, two images (the user's smaller
configured limit) and a 372,383-byte serialized body, versus 4,418 characters
and zero images in reconstructed main. Provider receives 300 seconds, with
360 seconds of task budget, only in the isolated acceptance process.

Real-generation outcome: one authorized task, one logical request, one HTTP
attempt; 81.75 seconds, HTTP 200, Responses status `completed`, no incomplete
details, successful normal JSON/business validation and persistence. Returned
usage: 5,608 input / 2,820 output / 8,428 total tokens. The request retained
`max_output_tokens=1800`; the gateway's larger reported output usage is an
unresolved gateway accounting/enforcement limitation, not adjusted in this PR.

Actual coverage: two ASR texts (one is a likely recognition artifact), five OCR
texts of uneven quality, two ordered contact sheets under the existing image
limit, no semantic comments and no saved single-analysis result in these five
Cases. Synthetic request tests cover the missing source types; this real call
does not claim to verify their real-world analysis quality.

The raw model summary, positioning, formulas, ideas, gaps and next actions
equal the normalized/saved values. Both saved reports mount the unchanged main
renderer at 1280 and 390 pixels / 100% zoom; native details open without new
detail overflow. The existing main mobile layout is not redesigned. Original
report/config/source-file hashes and the 8765 main process remain unchanged.

The candidate uses concrete costume variation and an audience-surrounded venue
visible in the two contact sheets. A proposed scale-reveal idea also has a
counterpart in OCR's setup/question/device-orientation wording. Those are more
grounded details, not proof of audience motivation or performance causality.
Music strength and exact beat/movement claims remain unsupported by static
input; the candidate's stronger confidence wording is not justified by this
call. Overall product gain is **not yet established**; human comparison is
pending. No Prompt/UI follow-up or second generation was performed.

The old renderer still displays inventory flags and structural quality labels
that can look like actual input coverage/factual confidence. The private preview
header states actual input counts to prevent that confusion; production UI is
unchanged and this pre-existing display issue is outside the PR scope.

Files, screenshots, request bodies and responses remain private outside Git. Encoded-size-rejected
contact sheets skip that sample rather than attempting another encoding or a
second image; this is an explicit bounded omission, not a processing failure.
