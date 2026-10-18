# TraceBrain

TraceBrain is a small, synthetic company-memory assistant for Graph Hacks 2026. It uses FastAPI and FalkorDB to turn documents and conversations into a tenant-scoped, provenance-aware graph.

## Run

```bash
docker compose up --build
```

Open http://localhost:8000. The API is also documented at http://localhost:8000/docs.

FalkorDB data is persisted in the Docker volume `tracebrain_falkordb`. To connect a Slack development workspace, copy `.env.example` to `.env`, create a Slack app with the listed bot scopes, set the three Slack secrets, expose the callback URL if Slack cannot reach localhost, and open `http://localhost:8000/slack/oauth/start`. Slack Events API requests go to `POST /slack/events`; the endpoint verifies the signing secret, rejects replayed requests, handles URL verification, deduplicates `event_id`, and ingests message events.

For local development, install `requirements.txt`, start FalkorDB with `docker compose up falkordb`, then run `uvicorn app.main:app --reload`.

## Demo

The API seeds synthetic incident documents on startup. Ask the default question or send:

```bash
curl -X POST http://localhost:8000/ask -H 'content-type: application/json' \
  -d '{"tenant_id":"acme","agent_id":"support-agent","question":"Who owns the checkout latency incident, what decision was made, and is the information current?"}'
```

The response includes a plain-language answer, owner, decision, freshness, conflict status, source documents, the exact Cypher query, and traversed graph path. The seeded Company Brain story also covers teams, projects, tickets, customers, systems, expertise, dependencies, and downstream impact paths.

## Architecture

The FastAPI service performs deterministic extraction for the synthetic demo, classifies each memory as episodic, semantic, or procedural, fingerprints documents for deduplication, and writes tenant-scoped `Document`, `Memory`, `Person`, `Incident`, and `Decision` nodes to FalkorDB. Relationships include `DESCRIBES`, `OWNS`, and `EVIDENCES`. `/ask` retrieves the newest evidence through a parameterized Cypher traversal and returns provenance plus the visible path. Conflicting owners or decisions are surfaced as a warning instead of being merged into an invented answer. Agent handoffs are stored as procedural conversation memory and shared by both agents in the tenant.

The frontend calls the JSON contract directly, renders trust signals, exposes exact Cypher, shows the graph path, and demonstrates the research-agent to support-agent handoff.

## Two-minute demo script

1. Open the app and point out that the `acme` tenant has two shared agents.
2. Click **Trace answer**. Explain that TraceBrain traverses FalkorDB instead of guessing from a chat response.
3. Call out Maya Chen as owner, the connection-pooling decision, the current status, and the source documents.
4. Show the exact Cypher and visible graph path for explainability.
5. Click **Hand research to support agent**. Explain that the handoff becomes shared procedural memory.
6. Ingest a second synthetic document with a different owner or decision, ask again, and show the conflict warning.

## Attribution and disclosure

TraceBrain is an independent implementation inspired by the publicly documented concepts in [Company Brain](https://github.com/supermemoryai/company-brain) and [HippocampAI](https://github.com/rexdivakar/HippocampAI). Their source code is not included as a dependency or vendored into this repository. The application is released under Apache License 2.0; see `LICENSE`.

AI assistance was used to help draft and test portions of this hackathon MVP. The system uses synthetic data only and does not connect to Slack, production systems, or external company data.

## API

- `POST /ingest` — ingest a synthetic document or conversation
- `POST /ask` — answer a company question through Cypher traversal
- `POST /handoff` — create a durable agent-to-agent handoff
- `GET /memory?tenant_id=acme` — inspect shared episodic, semantic, and procedural memory
- `GET /health` — service and graph health
- `GET /slack/oauth/start` — begin Slack OAuth v2 installation
- `GET /slack/oauth/callback` — exchange the OAuth code server-side
- `POST /slack/events` — verify and ingest Slack Events API deliveries

All request models require `tenant_id`; every graph query includes tenant filtering.

