# EdgeAtlas

**PS 03 — AI-Powered Edge Memory & Intelligence Platform · Team inrow**

Source repository: [thisisdkyadav/edgeatlas](https://github.com/thisisdkyadav/edgeatlas).

EdgeAtlas is a working offline-first memory workspace for field technicians. It captures observations and operating knowledge, embeds text on the device, searches a native Qdrant Edge shard, decides which notes may be shared, and synchronizes approved changes with a separate Qdrant Server. A revision gateway preserves concurrent edits for human resolution.

The product is a React/TypeScript interface backed by a Python/FastAPI device process. It uses **real Qdrant Edge 0.8.0**, **real BGE embeddings through FastEmbed/ONNX**, and **real Qdrant Server 1.19.1** in the supplied local demonstration. There is no hosted AI inference requirement and no substitute vector database labeled as Qdrant Edge.

## Open the running application

On the development machine, open **http://127.0.0.1:4100**. The device process, synchronization gateway on port 4200, and Qdrant Server on port 6333 are running locally. The server represents the centralized side of the workflow; this is not a claim that a remote cloud deployment has been provisioned.

Source directory: `C:\Users\DK YADAV\code\Codex\edgeatlas`.

No login is required in the loopback-only demo. A configured `EDGE_APP_TOKEN` enables the device access screen. No real personal data or equipment history is included: the eight seeded memories are illustrative examples, and a ninth note records the browser's offline workflow validation.

## Setup on Windows

Requires **Python 3.11+**, **Node.js 24+**, and a network connection for initial dependency and model downloads. Python and npm must be on PATH. The prepared development machine already has the dependencies, model, native server, and compiled interface.

```powershell
cd 'C:\Users\DK YADAV\code\Codex\edgeatlas'
.\setup.ps1
.\start.ps1
```

The setup script installs Python packages into the project's `.pydeps/`, installs npm dependencies, downloads the pinned official Qdrant Server Windows release, downloads the BGE model into `data/models/`, and builds the interface. It preserves an existing `.env`. The launcher opens no extra terminal windows and writes process identities and logs to `data/`. Run `stop.ps1` to stop processes started by that launcher; it compares both PID and process start time to avoid stopping an unrelated reused PID.

If PowerShell prevents script execution, run the following commands in separate terminals instead of changing a machine-wide execution policy:

```powershell
python -m pip install --target .pydeps -r requirements.lock.txt
npm.cmd ci
python run.py warm-model
npm.cmd run build
```

Start your Qdrant Server on `127.0.0.1:6333`, or use the official native executable downloaded by the setup script:

```powershell
$env:QDRANT__SERVICE__HOST='127.0.0.1'
$env:QDRANT__STORAGE__STORAGE_PATH='./data/qdrant'
$env:QDRANT__TELEMETRY_DISABLED='true'
.\tools\qdrant-server\qdrant.exe
```

In two additional terminals:

```powershell
python run.py cloud
```

```powershell
$env:HF_HUB_OFFLINE='1'
python run.py edge
```

Then open **http://127.0.0.1:4100**. For frontend development, run `npm run dev` and open port 5174; Vite proxies `/api` to port 4100.

The failed standard-venv creation on this development machine came from missing launchers in its existing Python distribution. The project-local `.pydeps` launcher avoids changing that Python installation. A normal virtual environment also works: `python -m venv .venv`, activate it, and install the same requirements without `--target`.

## Problem-statement coverage

| Goal | Implementation |
|---|---|
| Maintain local semantic memory | Persisted Qdrant Edge shard with 384-dimensional BGE vectors, BM25 sparse vectors, payload metadata, and WAL-backed updates |
| Low-latency vector and hybrid search offline | Local ONNX inference, native semantic and BM25 retrieval, reciprocal rank fusion, site/category filters, measured request duration |
| Decide local versus synchronized knowledge | Explicit sharing scope, sensitive-pattern blocking at both device and gateway, priority ordering, metered-link deferral, per-memory routing explanations |
| Continue through intermittent connectivity | Independent local API and search, a durable SQLite outbox, a cloud-link demonstration switch, bounded retry backoff, replay after restart |
| Synchronize with Qdrant Server | Authenticated gateway writes actual server vectors and payloads; ordered change feed pulls central changes into local Edge memory |
| Handle evolving memory and conflicts | Local optimistic versions, server revisions, idempotent mutation IDs, three conflict-resolution choices, reversible archives, tombstones, revision history |
| Inspect state and activity | Six workspaces, original source fields, search results and excerpts, pending/retry/conflict states, real cloud view, device configuration, event log |
| Meaningful edge-to-cloud behavior | Private memories never enter the initial sharing queue; permitted notes are sent on reconnect, another device can receive them, and concurrent offline edits cannot silently overwrite each other |

## Everyday workflow

1. **Capture a memory.** Add a title, body, category, site, tags, source, and priority. Choose device-only or team sharing. Optional retention archives a note after a number of days; zero means manual retention.
2. **Inspect its routing.** Open the memory to see why it is local or eligible for cloud sharing. Synthetic contact details in a seeded note demonstrate a blocked team-share request.
3. **Recall knowledge.** Search with a symptom such as `pump shaking on startup`. Switch between hybrid, semantic and keyword retrieval. Inspect cited source excerpts and open the original note.
4. **Go offline.** Disable the cloud link in Sync center. Capture another team-shareable note. The note remains searchable, and its outbound change stays queued. This changes the application's cloud-link policy; it does not disconnect the entire computer.
5. **Reconnect.** Enable the link and click Sync now. Inspect the real server copy under At the control room. Automatic synchronization checks every 15 seconds when enabled.
6. **Handle a conflict.** Pause auto sync. Edit a shared note on the device, then edit its server copy through Edit at control room. Sync. The device preserves both bodies. Keep the device, use the cloud, or save a merged note.
7. **Withdraw or archive.** Reclassifying a shared note as local, or adding a detected sensitive pattern, queues a content-free tombstone. Archiving also removes the note from search. Restore archived notes from the library.
8. **Export.** Download JSON with metadata and revision pointers or CSV from the library. CSV cells that could be interpreted as formulas are escaped.

The recall panel presents **retrieved source excerpts**, not an LLM-generated maintenance instruction. It deliberately avoids presenting speculative guidance as a verified procedure. Users must follow their authorized equipment manuals and site procedures.

## Technology

| Layer | Technology |
|---|---|
| Interface | React 19, TypeScript, Vite, custom responsive CSS, Lucide icons |
| Device API | Python 3.11, FastAPI, Uvicorn, Pydantic |
| Local vector engine | `qdrant-edge-py==0.8.0`, native embedded EdgeShard |
| Local AI | FastEmbed 0.8.1, ONNX Runtime CPU, `BAAI/bge-small-en-v1.5`, 384 dimensions |
| Keyword retrieval | Qdrant Edge's built-in BM25, IDF sparse-vector modifier |
| Hybrid ranking | Qdrant Edge reciprocal rank fusion, k=60 |
| Durable coordination | Python SQLite, WAL, serialized device and gateway mutations |
| Central vector storage | Qdrant Server 1.19.1, accessed through its REST API using HTTPX |
| Transport | Authenticated JSON mutation and change-feed gateway |
| Tests | Pytest, FastAPI TestClient, actual Edge engine and actual Qdrant Server |
| Distribution | Windows setup/start/stop scripts, pinned locks, Dockerfile, three-service Compose configuration, CI workflow |

## Configuration

Copy `.env.example` to `.env`. Secrets remain on the device/gateway processes; the browser does not receive the Qdrant API key or sync token.

| Variable | Purpose |
|---|---|
| `EDGE_HOST`, `EDGE_PORT` | Device interface bind address and port; defaults are loopback and 4100 |
| `EDGE_DATA_DIR` | Device SQLite database and Edge shard directory |
| `EDGE_DEVICE_ID`, `EDGE_DEVICE_NAME` | Device identity; use a different ID and directory for each device |
| `EDGE_MODEL_CACHE` | Cached model directory; prepare once using `warm-model` |
| `EDGE_CLOUD_URL` | Revision gateway URL; point this at your deployed gateway for remote use |
| `EDGE_SYNC_TOKEN` | Shared gateway authentication secret; replace the demo token for remote use |
| `EDGE_APP_TOKEN` | Optional device API access token; required for a non-loopback bind |
| `EDGE_APP_ORIGIN` | Additional allowed frontend origin for a remote reverse proxy |
| `EDGE_AUTO_SYNC`, `EDGE_SEED` | Initial automatic-sync and illustrative seed behavior |
| `CLOUD_HOST`, `CLOUD_PORT`, `CLOUD_DATA_DIR` | Gateway bind address, port and coordination database |
| `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION` | Actual Qdrant Server or Qdrant Cloud connection |

Saved device connection/policy settings override the initial `EDGE_AUTO_SYNC` value after the first UI change. Restarting restores them rather than resetting a deliberate offline policy.

## Run a second edge device

Keep the same gateway and server running. Start a new device in another terminal:

```powershell
$env:EDGE_PORT='4101'
$env:EDGE_DEVICE_ID='field-unit-12'
$env:EDGE_DEVICE_NAME='Field unit 12'
$env:EDGE_DATA_DIR='./data/edge-12'
$env:EDGE_SEED='false'
$env:HF_HUB_OFFLINE='1'
python run.py edge
```

Open **http://127.0.0.1:4101** and synchronize. Team memories arrive locally and become searchable offline. Device-only notes do not travel through this gateway. See `docs/DEMO.md` for a concise judge walkthrough.

## Tests and validation

Keep a local Qdrant Server running on port 6333 and cache the model first:

```powershell
npm run build
python run.py test
npm run format:check
npm audit --omit=dev
```

The suite creates UUID-suffixed **test collections** in the local server, and temporary device/gateway databases. It does not reuse or delete the demo collection. It exercises actual semantic and BM25 search, real server writes/pulls, socket-blocked offline retrieval, privacy blocks, durable queues, concurrency, idempotency, retries, withdrawals, retention, API access checks, export safety, and local/cloud projection recovery.

See `docs/VALIDATION.md` for the recorded result and limits. Docker configuration and CI definitions are provided; the validated local runtime uses native Windows processes.

## Deploy the central side later

The **device process belongs near the edge user**. Hosting only the frontend and relying on a remote API would defeat the offline design. Deploy the revision gateway and Qdrant Server centrally, leave EdgeAtlas and its cached model on the device, and set `EDGE_CLOUD_URL` to the gateway's HTTPS URL.

The Compose file is a convenient complete local topology. Before using it, set fresh `EDGE_APP_TOKEN` and `EDGE_SYNC_TOKEN` values in `.env`. The host ports are bound to loopback. The images keep model, device, gateway, and Qdrant data in separate locations/volumes.

```powershell
docker compose up --build -d
```

For remote use, provide HTTPS, strong secrets, network restrictions, backups and per-workspace identity/access controls. Run **one process per device shard and one gateway writer per cloud coordination database**. Multiple independent gateways must not coordinate mutations against one collection using separate SQLite databases. A shared transactional revision database is needed before horizontal scaling.

Back up SQLite consistently, including its WAL state, and use Qdrant snapshots for the central vector store. Stop the relevant local process before filesystem copies, or use supported database backups. The vector projections can be rebuilt from their authoritative SQLite documents, but backup of the coordination databases is still required.

## Practical limits

- Qdrant Edge is beta; the implementation pins its binding version. Its local API is used directly, while synchronization is application-level revision/outbox synchronization rather than server partial-snapshot transfer.
- Model downloads require internet once. A cold device without the prepared model cannot provide semantic search; the app fails visibly rather than replacing semantic search with hash vectors. Cached runtime loads with `local_files_only=True`; offline tests block network sockets.
- Semantic similarity and routing priority are separate concepts. Rank scores are not confidence percentages. BGE is an English text model and long documents may be truncated by its tokenizer; split long manuals into focused notes before ingestion.
- Sensitive-pattern checks are conservative heuristics, not a guarantee that all confidential information is detected. Device-only is the recommended scope for confidential notes. SQLite and the Edge shard are not encrypted by this application; use disk encryption and OS access controls for sensitive deployments.
- Shared-copy withdrawal is a **soft tombstone**, not guaranteed erasure of previously synchronized history, gateway operation receipts or other devices' backups. Device archives retain content and revision history for restoration. Production erasure requires a coordinated history/backup policy.
- The demo is a single trusted workspace. It has no per-user organization tenancy, distributed multi-writer gateway, mobile-native installation, biometric access control or LLM-generated reasoning. These are future extensions, not claimed features.
- Offline refers to the device losing access to the cloud while its local application continues running. The browser is not a standalone PWA and does not queue edits if the local device API itself is stopped. The notes and model persist on the device, not only in browser storage.
- All equipment and contact examples are synthetic/illustrative. The product organizes knowledge; it does not authorize physical maintenance or replace certified safety procedures.

## Repository map

```text
src/                  Interface, typed API client, responsive styles
backend/vectors.py    FastEmbed and native Qdrant Edge dense/BM25/hybrid index
backend/engine.py     Local memories, durable queue, pull/ack/conflict logic
backend/cloud.py      Revision gateway and actual Qdrant Server projection
backend/policy.py     Explicit scope, sensitive-pattern and priority rules
backend/storage.py    SQLite schema, versions, settings, events and projections
backend/app.py        Local API, access checks, cloud editor and SPA serving
backend/seed.py       Clearly illustrative field memories
tests/                Actual engine and server integration suite
docs/                 Architecture, API, demo and validation
run.py                Portable Python launcher
setup/start/stop.ps1   Windows lifecycle helpers
Dockerfile            Interface build and cached-model Python runtime
compose.yaml          Device + gateway + Qdrant Server topology
```

## Official references

- [Qdrant Edge](https://qdrant.tech/documentation/edge/)
- [Edge quickstart](https://qdrant.tech/documentation/edge/edge-quickstart/)
- [Native on-device BM25](https://qdrant.tech/documentation/edge/bm25/)
- [Synchronization patterns](https://qdrant.tech/documentation/edge/edge-data-synchronization-patterns/)
- [Qdrant Edge Python package](https://pypi.org/project/qdrant-edge-py/)
- [Qdrant Server release](https://github.com/qdrant/qdrant/releases/tag/v1.19.1)
- [FastEmbed](https://qdrant.tech/documentation/fastembed/)
