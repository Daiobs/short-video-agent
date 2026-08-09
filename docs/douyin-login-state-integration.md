# Douyin Login State Integration

## Scope

This integration connects four separate responsibilities:

1. **Standalone Plugin**: reads Douyin login state only after an explicit user action.
2. **Integration API**: accepts pairing, signed sync, status, and clear requests on loopback.
3. **Credential Store**: keeps raw Cookie material outside the repository with restrictive permissions.
4. **Profile Provider**: consumes the effective login state for the existing Douyin profile scan.

The standalone plugin source is not owned by this PR. The historical implementation at `cf805e7` was used only as a protocol reference; its old LLM, Creator, UI, and CSS changes were not restored.

## Local API v1

All endpoints are loopback-only and return `Cache-Control: no-store`:

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/local-login-state/pair/start` | Create one short-lived pairing code from the local settings page. |
| `POST` | `/api/local-login-state/pair/complete` | Complete pairing from the explicitly allowed extension and return the new shared key once. |
| `GET` | `/api/local-login-state/status` | Return non-sensitive pairing and sync metadata. |
| `POST` | `/api/local-login-state/douyin/sync` | Store a validated, authenticated Douyin login state. |
| `DELETE` | `/api/local-login-state/douyin` | Remove only the extension-synced Douyin state. |

The current protocol uses `schema_version=1`. Pairing codes expire after ten minutes, are attempt-limited, and become invalid immediately after successful use. Re-pairing rotates the shared credential and invalidates the prior extension state.

## Extension identity

Receiver access is default-deny. Configure the exact unpacked or published extension ID:

```env
DOUYIN_LOGIN_EXTENSION_IDS=abcdefghijklmnopabcdefghijklmnop
```

Multiple explicitly trusted IDs may be comma-separated. Each value must be a complete Chrome extension ID (`[a-p]{32}`). If no valid ID is configured, pairing fails with `EXTENSION_ID_CONFIGURATION_REQUIRED`. A syntactically valid but unlisted `chrome-extension://` Origin is still rejected.

The paired extension ID is also stored with the shared credential. A different allowed extension cannot reuse another extension's pairing.

## Signed writes and replay protection

Sync and delete requests include:

```text
X-SVA-Timestamp
X-SVA-Nonce
X-SVA-Signature
X-SVA-Schema-Version
X-SVA-Extension-Version
```

The HMAC-SHA256 signature covers the exact raw body:

```text
timestamp + "\n" + nonce + "\n" + raw_body
```

Signatures use constant-time comparison. Timestamp tolerance, nonce syntax, extension version, schema version, and request size are bounded before the payload is accepted.

Replay claims are stored transactionally in:

```text
~/.short-video-agent/nonce-ledger.sqlite3
```

The ledger stores only scoped nonce digests. It survives a process restart, removes expired entries, and is capped at 4096 rows and 4 MiB. If all bounded entries are still live, the Receiver fails closed instead of evicting an unexpired nonce. It is designed for the local single-instance deployment, not distributed servers.

## Credential store

Secrets are stored in:

```text
~/.short-video-agent/credentials.json
```

Security properties:

- parent directory mode `0700`;
- file mode `0600`;
- regular-file and size validation;
- symlink refusal for the file and immediate parent;
- exclusive temporary file creation;
- file and directory `fsync`;
- atomic `os.replace`.

Raw Cookie values and the shared key never enter `.local_settings.json`, SQLite application tables, Jobs, Cases, Creator artifacts, prompts, reports, logs, browser storage, or status responses. The status mask is always exactly `********`.

## Legacy plaintext migration

If `.local_settings.json` still contains a legacy plaintext Douyin Cookie, the runtime first attempts to move it into the secure credential store.

- On success, the plaintext field is removed and only non-secret metadata remains.
- On failure, the original copy is retained but is not consumed. Calls fail with `LEGACY_CREDENTIAL_MIGRATION_REQUIRED` until the storage problem is corrected.

There is no `manual_legacy` credential source.

## Credential priority

The Profile Provider receives one internal effective settings object in this order:

1. `chrome_extension`
2. `manual_secure`
3. `environment`

Only internal Provider code receives the raw Cookie. Public status payloads expose source, fixed mask, counts, timestamps, schema, extension version, and a bounded health status.

When `source=chrome_extension`, a Profile Provider error remains visible and does not silently switch to the public provider. This preserves actionable login-state diagnostics. Other existing import paths remain available.

## Cookie and Referer validation

The Receiver rejects:

- duplicate Cookie names, including case-only duplicates;
- invalid names and control characters;
- excessive header bytes or pair counts;
- payload count mismatches;
- login state without at least one populated login field.

Referer values must be HTTPS Douyin URLs. Only their safe origin and path are retained; query and fragment components are removed before storage.

## Standalone plugin follow-up

The Receiver accepts normalized state originating from a valid host-only `www.douyin.com` Cookie. It does not read browser Cookies and must not fabricate missing values.

The historical standalone plugin can incorrectly omit host-only `www.douyin.com` Cookies. That is an independent plugin task:

```text
PLUGIN_HOST_ONLY_COOKIE_FIX_REQUIRED
```

Until the plugin-side fix is released, a sync payload may be valid at the Receiver but incomplete at the collection source.

## Testing boundary

Automated tests inject temporary credential and nonce-ledger paths. They use synthetic Cookie values and mocked Douyin responses only. The tests do not pair the real extension, read or rewrite the real credential file, or make a real Douyin request.
