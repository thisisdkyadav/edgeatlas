# Recorded validation

Validated on Windows on **30 September 2026**, using Python 3.11.14 and Node.js 24.19.0. The running topology uses native Windows processes, the cached BGE model, native Qdrant Edge 0.8.0, and Qdrant Server 1.19.1. The backend accesses the real central vector server rather than a simulated in-memory store.

## Automated results

| Check | Recorded result |
|---|---|
| `python run.py test` | **30 passed**, one test-adapter deprecation warning, 32.36 seconds |
| `npm run build` | TypeScript compilation and Vite production build passed |
| `npm run format:check` | Source formatting passed |
| `npm audit --omit=dev` | Zero reported production dependency vulnerabilities |
| Python source compilation | Backend and tests compiled successfully |
| PowerShell parser | Setup, start and stop scripts parsed without errors |
| Windows launcher | Started all three services, checked device/gateway/server health, stopped them through their recorded identities, and restarted the demo |
| GitHub CI | [Verification run 36754463206](https://github.com/thisisdkyadav/edgeatlas/actions/runs/36754463206) passed on Ubuntu: build, formatting, and 30 integration tests with a real Qdrant Server service |

The warning comes from Starlette's TestClient using its current HTTPX adapter. It does not indicate an application test failure. The fixture creates isolated UUID-suffixed test collections and temporary coordination databases. Production/demo data is not used by these tests.

The 30 cases include parametrized privacy patterns and conflict choices. They cover actual dense/BM25/hybrid ranking, payload filters, retrieval with network sockets blocked, explicit local scope, optimistic local edits, real server writes and a second device pull, offline capture/reconnection, persistent queues and shard reopening, retry backoff, metered routing and prioritized withdrawals, content-free privacy reclassification, local/cloud/merge conflict resolution, unresolved-conflict protection, reversible archive/restore/expiry, idempotent operations, changed-operation rejection, gateway content/vector validation, cloud projection recovery, local index repair before search, request validation/origin checks, safe CSV export, device/gateway tokens, and central editing followed by a device pull.

## Browser workflow

The production interface was exercised in Chrome:

1. Disabled automatic synchronization and the application's cloud link.
2. Captured a new team-shareable pump observation.
3. Retrieved that new note locally while the cloud link was disabled. Its measured local retrieval duration was about **19 ms** in that individual request.
4. Re-enabled the cloud link and synchronized the durable queue. The note appeared in the actual central shared view at revision 1.
5. Edited the central copy and the device copy separately with auto sync paused.
6. Synchronized, verified the two preserved versions, and saved a combined note.
7. Synchronized the merged version successfully, leaving no pending work or conflicts, and restored automatic synchronization.
8. Checked the overview and recall interface at desktop and 390-pixel mobile viewport widths.

Screenshots accompany the delivery: the final overview, mobile layout, offline recall, and conflict review. Recorded durations are individual illustrative measurements, **not** a latency benchmark, service-level promise, or cold-start measurement.

## What has not been run or claimed

- The Dockerfile and Compose topology are supplied but have not been executed as a deployment. The native Windows runtime was validated locally, and the GitHub integration workflow subsequently passed on Ubuntu.
- The setup script has passed static parsing. Its dependency installation, official server download, model preparation, and frontend build steps were performed directly. The start/stop launcher was exercised end to end.
- The source is published at [thisisdkyadav/edgeatlas](https://github.com/thisisdkyadav/edgeatlas). No external hosting has been provisioned; the separate central participant runs on the development machine.
- The cloud-link switch simulates an outage at the synchronization boundary. The independent offline integration test blocks actual network sockets during retrieval.
- No large-corpus throughput, multilingual ranking, distributed gateway scaling, multi-tenant authorization, permanent erasure, or application-level encryption guarantee is claimed.

See the README's practical limits and deployment section before adapting this prototype beyond the supplied single trusted workspace.
