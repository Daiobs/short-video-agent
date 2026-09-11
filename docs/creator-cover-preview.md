# Creator cover URLs and local frame previews

Base: `78359d59dd9b7606e5825f2cf6a010aca1134798` (main with PR #31).

## Scope and data flow

Cover fields now use `validated_cover_url` during profile, browser handoff,
structured import, persistence, reload and Creator DTO conversion. Accepted
URLs retain their original path and query bytes; HTML attribute escaping does
not change the browser's request URL. Invalid URLs become an empty cover field,
not a truncated or partially repaired URL. One rejected cover does not reject
an ordinary sample import. Handoff credential detection remains stricter.

This is a cover-only exception, not a change to general metadata redaction.
Allowed domains are `douyinpic.com`, `byteimg.com`, `hdslb.com`, `xhscdn.com`
and their boundary-matched subdomains, with an image-extension resource path.
Maximum URL length is 4096 characters. Userinfo, nonstandard ports, fragments,
control characters, path traversal, non-HTTP protocols and recognized account
credential parameters are rejected. Opaque image signatures such as
`x-signature`, image `token` and expiry parameters are not stripped.
Unrecognized platform hosts or opaque extensionless resource paths currently
fall back rather than expanding access automatically.

General source URLs and text retain their previous sanitization. Creator
Prompt construction strips cover query parameters and excludes local preview
fields. No full signed URL is added to logs, analysis or readable reports.
Handoff's signed-media exclusion continues to exclude video download/login
material; this narrow image-access field is validated independently.

## Existing local assets

Read-only `preview_url` and `preview_source=video_frame` are derived from the
sample's associated Case, not imported from client-provided preview fields and
not persisted back into `samples.json`. `cover_url` remains the platform cover.
Case records are fetched in batches (500 IDs). Aweme identities must match when
present. The configured frame directory must resolve to this Case's keyframes
directory; symlinks, missing directories and invalid IDs degrade to no preview.

The lexicographically first nonempty `frame_*.jpg` is selected deterministically
from at most 256 directory entries. Directory overflow yields no preview.
This reads file metadata only, not all image bodies. Existing safe
`/api/cases/{case_id}/keyframes/{filename}` serves the selected file.
No contact sheet, extraction, AI frame selection, remote proxy or image cache
is added. A file can disappear or be undecodable after lookup; the client then
ends fallback normally.

## List behavior

Each rendered image tries the platform cover first, then at most one local
frame. Platform success does not request the local frame. Missing remote cover
uses the local frame immediately. Local success is marked `视频帧预览`; exhausted
or unavailable previews show `暂无可用预览`. An `img` error no longer claims a
specific HTTP status or platform restriction. Cached failures, independent
local failure, disconnected old nodes and repeated binding are covered.
Sorting or filtering naturally creates a new render; no retry loop is added.

## Validation

- Full regression: **686 passed**, one existing Starlette/httpx warning.
- JS syntax (`app.js`, Node cover runner), compileall and diff checks passed.
- Synthetic signed URL traversed import/save/reload/API and actual browser GET
  without changing percent escapes, plus signs or query order. HTML escaping
  and generic metadata/credential redaction tested separately.
- Formal app/API and normal list component loaded two private real-sample
  copies in an isolated SQLite/output directory. Mocked remote 403 responses
  fell back to each Case's actual JPEG (`naturalWidth > 0`). Sorting, media
  filtering and refresh retained the correct association and selected rows.
- Chrome/Playwright at 100% scale, widths 1280 and 390: both local frames and
  source captions readable; document width equals viewport width. The existing
  horizontally scrollable mobile table and other old mobile layout issues are
  unchanged. Screenshots and real sample records are private, not committed.
- Updated only the old cover assertions that accepted arbitrary hosts or
  stripped userinfo, and the old misleading placeholder assertion; the rest
  of those security tests remain intact.

## Limits and acceptance

Historical queryless covers are not repaired, migrated, or given another
sample's signature. The earlier real 403 responses do not uniquely establish
that query removal caused those failures. No fresh signed platform cover was
available for real-network validation in this change. Synthetic preservation
proves the transport fix, not current platform availability.

The real examples use local **video frames**, not restored original covers.
Metadata-only samples without an accessible Case frame keep a neutral fallback
if the remote cover fails. Original data/configuration, ports 8765/8766, report
logic and model input semantics remain unchanged. All real model, scan, video
download, enrichment and additional remote image GET counts are zero.

An isolated interactive list is provided separately for human acceptance;
remote images are blocked there to avoid accidental network requests, while
browser automation uses explicit 403 mocks. Only local sample recommendation
and read operations are enabled; generation/settings writes are blocked.
Human product acceptance remains pending. This branch must remain a Draft PR.
