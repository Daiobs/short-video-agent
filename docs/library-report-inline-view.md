# Creator report viewing and downloads

Base: `3a0826fa52f85b762a3a79ac9d3ab0d027b97f2d` (main including PR #31 and PR #33).

## Cause and contract

The library already used `target="_blank"` without a `download` attribute. An actual Chrome click downloaded the report because the file response specified a filename and therefore returned `Content-Disposition: attachment`.

- `GET /api/creator-clone/sets/{set_id}/files/creator_clone.html?view=1`: view the saved HTML in a new tab, `text/html; charset=utf-8`, `Content-Disposition: inline`.
- The same path without a query remains an explicit HTML attachment download.
- Only the exact `view=1` query on `creator_clone.html` supports viewing. Other files retain download semantics; a view parameter on them is rejected.
- The library offers separate **打开报告** and **下载 HTML** links. Markdown-only assets show **下载 Markdown**, not a misleading report-view action.
- Creator's **打开网页报告** and Workbench report links share this viewing mode. Creator's **下一步：下载报告** retains attachment semantics. Case links and precise Creator recovery are unchanged.
- URL allowlists accept only this specific query, not arbitrary parameters or external URLs.

## Read-only and safety

HTML access reads existing bytes only. It no longer calls the export helper to generate missing files, rewrite JSON, or create a missing Creator directory. Missing HTML returns a sanitized 404 directing the user to existing Creator results or Markdown. No report renderer or business content changes are included.

Creator IDs are validated, symlinked directories/files and escaping paths are rejected, and HTML is bounded at 8 MiB. Viewing sets `Cache-Control: no-store`, `nosniff`, `Referrer-Policy: no-referrer`, and a sandbox CSP. Saved HTML cannot execute scripts, submit forms, or act as same-origin application code; native details and inline styles remain usable. This is not a new general-purpose HTML viewer.

The default JSON, Markdown, Prompt and other file download paths retain their existing behavior. Report viewing does not regenerate old static exports. In particular, the real saved HTML used for acceptance has no native details controls; it is preserved byte-for-byte, not replaced with a newer export. Missing historical detail content cannot be recovered by fixing response headers.

## Verification

Automated coverage checks headers, byte equality, missing files without writes, two distinct Creators, strict URL parameters, invalid IDs, symlinks, oversized HTML, existing download semantics, library action labels and Creator recovery targets. Existing formula/idea and cover regressions remain in the full suite.

An isolated formal FastAPI application and library page were tested using Chrome at 100% scale, 1280px and 390px. A copy of the current real report was opened from a filtered second library page: a new tab rendered the identical saved bytes, refresh and direct access worked, and no download occurred. The separate download action produced exactly one `creator_clone.html` with matching content. The original library query, page and rows stayed unchanged. Isolated output/database hashes and original source hashes were unchanged during view/download.

Native formula/idea expansion was separately tested using explicitly synthetic complete HTML, because the saved real export contains no such controls. This does not claim to have restored missing details in that historical artifact. A saved-script fixture verifies that CSP blocks execution while native details still work. Existing report layout/content issues are outside this fix.

No model calls, collection, video downloads, enrichment, runtime deployment, favorites or notes are part of this change. Private reports, browser downloads and screenshots are not committed.

Final local checks: `pytest -q`: **707 passed**, one existing Starlette deprecation warning. All 12 tracked application JavaScript files and the new Node behavior runner passed `node --check`; `compileall` and `git diff --check` passed. The saved real report had no horizontal overflow at either tested width. The existing mobile library header clips some navigation items; this change does not alter that layout.
