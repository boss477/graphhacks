# TraceBrain

TraceBrain is a small, synthetic company-memory assistant for Graph Hacks 2026. It uses FastAPI and FalkorDB to turn documents and conversations into a tenant-scoped, provenance-aware graph.

## Run

```bash
docker compose up --build
```

Open http://localhost:8000. The API is also documented at http://localhost:8000/docs.

For local development, install `requirements.txt`, start FalkorDB with `docker compose up falkordb`, then run `uvicorn app.main:app --reload`.

## Demo

The API seeds synthetic incident documents on startup. Ask the default question or send:

```bash
curl -X POST http://localhost:8000/ask -H 'content-type: application/json' \
  -d '{"tenant_id":"acme","agent_id":"support-agent","question":"Who owns the checkout latency incident, what decision was made, and is the information current?"}'
```

The response includes a plain-language answer, owner, decision, freshness, conflict status, source documents, the exact Cypher query, and traversed graph path.

## API

- `POST /ingest` — ingest a synthetic document or conversation
- `POST /ask` — answer a company question through Cypher traversal
- `POST /handoff` — create a durable agent-to-agent handoff
- `GET /memory?tenant_id=acme` — inspect shared episodic, semantic, and procedural memory
- `GET /health` — service and graph health

All request models require `tenant_id`; every graph query includes tenant filtering.

