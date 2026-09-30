# EdgeAtlas API

Device base: `http://127.0.0.1:4100/api`. Supply `X-Edge-Token` when configured. Gateway base: `http://127.0.0.1:4200`; supply `X-Sync-Token`. Qdrant's API key stays in gateway environment variables.

## Device routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Local process/engine health |
| GET | `/status` | Identity, model, connection, queue/conflict counts, storage and sync cursor |
| GET | `/memories?include_deleted=true` | Memories with routing explanation and synchronization state |
| POST | `/memories` | Capture and locally embed/index a memory |
| GET | `/memories/{uuid}` | Inspect one memory |
| PUT | `/memories/{uuid}` | Edit with an `expected_version` |
| POST | `/memories/{uuid}/archive` | Reversible archive with expected version |
| POST | `/memories/{uuid}/restore` | Restore archived memory with expected version |
| GET | `/memories/{uuid}/history` | Most recent 100 local revisions, without raw vectors |
| POST | `/memories/{uuid}/resolve` | Resolve a conflict: `local`, `cloud` or `merge` |
| POST | `/search` | Local semantic, BM25 or hybrid retrieval and source excerpts |
| GET | `/search-history` | Most recent 30 local recall queries |
| POST | `/sync` | One bounded push/pull synchronization pass |
| PUT | `/connection` | Set cloud-link and metered policy |
| PUT | `/policy` | Automatic sync and metered priority threshold |
| GET | `/activity` | Most recent 150 device events |
| GET | `/cloud` | Actual shared overview through the gateway |
| PUT | `/cloud/memories/{uuid}` | Edit the central copy with an expected cloud revision |
| POST | `/optimize` | Explicit native index optimization |
| GET | `/export?format=json` | Local data export, including archived memories |
| GET | `/export?format=csv` | Formula-escaped local CSV export |

## Capture/edit schema

```json
{
  "title": "Pump P-204 cold-start observation",
  "body": "Illustrative note: inspect the coupling and mounting bolts under the approved procedure.",
  "category": "Observation",
  "site": "North station",
  "tags": ["pump", "vibration"],
  "visibility": "team",
  "priority": "high",
  "source": "Illustrative field note",
  "ttl_days": 0
}
```

Titles must be 3–150 characters; body 10–12000; category one of Observation/Procedure/Incident/Reference; visibility local/team; priority low/normal/high/critical; at most 12 tags of 40 characters each; retention 0–3650 days. Updates require the current local `expected_version`. For the central editor, `expected_version` is the current cloud revision instead.

Returned documents include UUID, local version, cloud revision, origin device, timestamps, routing reason/flags/priority, sync state and any conflict snapshot. Raw dense vectors are not returned to the browser.

## Search

```json
{"query":"pump shaking on startup","mode":"hybrid","category":"","site":"","visibility":"","limit":8}
```

Query length is 2–1000 characters; limit 1–30. The response contains ranked results, measured retrieval duration, engine/model and up to three source excerpts. Similarity/fusion scores are rank values, not calibrated confidence. No search query is transmitted to the gateway.

## Synchronization controls

```json
{"online":false,"metered":false}
```

The cloud-link flag simulates a disconnected device at the sync boundary. The local API remains accessible. Real HTTP disconnections also retain outbox entries and schedule retries.

```json
{"auto_sync":true,"metered_min_priority":70}
```

Priority scores are low=10, normal=40, high=70, critical=100. A metered cutoff defers ordinary outbound updates below that score. Privacy withdrawals always bypass the cutoff.

## Gateway routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Validate actual Qdrant Server availability |
| POST | `/sync/push` | Revision-checked, idempotent mutation |
| GET | `/sync/changes?after=0&limit=100` | Ordered page of central changes |
| GET | `/sync/overview` | Active shared records and withdrawal count |
| POST | `/sync/search` | Actual Qdrant Server dense query with tombstones excluded |

A push carries operation UUID, device ID, base revision, allowed document, 384-dimensional finite vector and embedding-model identity. A tombstone carries just the ID/deleted marker; the gateway writes a sanitized tombstone and zero vector. Mismatched revisions return 409 with the current remote document. Exact repeated operation IDs return their stored receipt after repairing any pending server projection. Reuse with changed content is rejected.

Change-feed cursor values are monotonically increasing sequence numbers. Payloads are returned only after pending vector projection work succeeds, preserving the relationship between an acknowledged central state and the actual server store.

## Failure behavior

- 401: invalid/missing configured device or gateway token.
- 403: disallowed origin.
- 404: missing memory or conflict.
- 409: outdated local version, unresolved conflict, cloud revision mismatch or changed operation reuse.
- 422: invalid input or blocked shared content.
- 503: unreachable gateway/Qdrant Server; pending work remains durable.

The device `/sync` response uses status `connected`, `offline` or `unavailable` and counts pushed/pulled/deferred work. `unavailable` is not a successful acknowledgement. The UI keeps edits on the device and explains the remaining queue.
