# Five-minute judge walkthrough

## Pitch

“Field technicians need useful knowledge even when the network disappears. EdgeAtlas stores and searches semantic memory on the device using Qdrant Edge. It only shares safe, selected knowledge, synchronizes to Qdrant Server when connectivity returns, and preserves conflicting edits rather than guessing which technician is right.”

## Demonstration

1. **Overview (30 seconds).** Show device memory, private/shared counts and the edge/cloud topology. State that the seed notes are illustrative. Both Qdrant Edge and the central Qdrant Server are real local processes in this demo.
2. **Recall (45 seconds).** Search `pump shaking on startup`. Open the highest-ranked pump observation. Switch to keyword mode with `vibration`, then return to hybrid. Show source excerpts and local duration. Explain that the BGE model runs on-device and the excerpts are not generated safety instructions.
3. **Privacy (30 seconds).** Open Restricted contact in a service note. It requests team sharing, but the synthetic email makes the routing engine keep it local. Inspect the corresponding absence in the control-room view.
4. **Offline capture (60 seconds).** Disable auto sync in Device & policy, then disable the cloud link in Sync center. Capture a new team note. Recall it immediately. Show Awaiting sync and the pending count. A real network outage produces the same durable-queue behavior; this switch affects application sync only.
5. **Reconnect (30 seconds).** Enable the link and Sync now. Show the note in At the control room with cloud revision 1. It is now stored in Qdrant Server. A second device can pull it and search it locally.
6. **Conflict (60 seconds).** Keep automatic sync paused. Edit the new local note. Then find its original central copy in Sync center and use Edit at control room to make a different change. Sync. Open the conflicting note; show both versions and merge them. Sync again to acknowledge the new revision.
7. **Withdrawal (30 seconds).** Change the shared note to Device only. Sync. Its local body remains, but the current server copy disappears from the active shared view. Explain the content-free tombstone and the distinction between withdrawal and permanent erasure.
8. **Finish (15 seconds).** Show the revision trail, activity and exports. Restore automatic sync if desired.

## Explain the architecture

- Native embedded EdgeShard handles dense/BM25/hybrid local retrieval.
- FastEmbed/ONNX produces real 384-dimensional BGE embeddings without remote inference.
- SQLite atomically saves memory, versions, a retryable outbound snapshot and index repair markers.
- The gateway coordinates cloud revisions/idempotency and projects records to real Qdrant Server.
- An ordered change feed hydrates another edge shard; conflict resolution uses expected revisions.

## Likely questions

**Is this just a local vector database?** No. Show private versus shared routing, offline queue, reconnection, central editing, conflict preservation and withdrawals. Those workflows require coordination beyond vector retrieval.

**Does it need internet for AI?** Once to download its fixed model and dependencies. Normal capture/embedding/search run locally against the cached model. The offline integration test blocks network sockets while searching.

**Is the central server actually a cloud deployment?** In the validated demo it is a separate local Qdrant Server process. The same gateway can connect to Qdrant Cloud or another server by setting URL/key. No external deployment is claimed.

**How is privacy decided?** Explicit scope, conservative sensitive-pattern checks at both boundaries, and priority/bandwidth rules. Explain the limits of heuristics and the absence of application-level encryption rather than claiming guaranteed confidentiality.

**Does the AI reason over failures?** It recalls relevant memories and provides their source excerpts. No generative LLM or unsupported equipment diagnosis is presented. A later optional on-device LLM could reason over those citations.

**What happens if the server is down?** Search remains local, outbound work survives in the outbox, errors are visible and retries back off. If the gateway commits but its vector server fails, a durable projection marker makes the same operation recoverable without creating another revision.

**Can two devices edit at once?** Yes. The expected server revision catches the second disconnected writer. Both bodies are preserved until local/cloud/merge resolution. Further concurrent changes can require another explicit resolution.

**What remains for production?** Per-workspace identity, stronger authorization, encrypted local storage, scale-aware central revision coordination, coordinated erasure/backup policies, large-document chunking and deployment hardening. The current product is a functional single-workspace prototype with end-to-end tests.
