from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .graph import GraphStore

app = FastAPI(title="TraceBrain", version="0.1.0")
store = GraphStore()
handoffs: list[dict] = []

SEED = [
    {"id": "incident-update", "title": "Checkout incident update", "source": "incident-2026-10-14.md", "type": "document", "memory_kind": "semantic", "updated_at": "2026-10-14T09:00:00+00:00", "text": "Incident checkout latency is owned by Maya Chen. The team decided to prioritize database connection pooling and revert the risky cache change."},
    {"id": "support-thread", "title": "Support agent handoff", "source": "conversation-support-2026-10-14.txt", "type": "conversation", "memory_kind": "episodic", "updated_at": "2026-10-14T10:00:00+00:00", "text": "Maya confirms the checkout latency incident owner and the database connection pooling decision."},
]

class IngestRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    text: str
    title: str = "Untitled source"
    source: str = "api"
    type: str = "document"
    id: str | None = None
    updated_at: str | None = None
    memory_kind: str = "semantic"

class AskRequest(BaseModel):
    tenant_id: str
    agent_id: str = "default-agent"
    question: str

class HandoffRequest(BaseModel):
    tenant_id: str
    from_agent: str
    to_agent: str
    task: str
    context: str = ""

@app.on_event("startup")
def seed():
    if not store.memory("acme"):
        for doc in SEED:
            store.upsert_document("acme", doc)

@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(Path(__file__).parent.parent / "frontend" / "index.html")

@app.get("/health")
def health():
    return {"ok": True, "service": "tracebrain", "graph": "falkordb" if store.db else "fallback"}

@app.post("/ingest")
def ingest(req: IngestRequest):
    return {"ok": True, "memory": store.upsert_document(req.tenant_id, req.model_dump())}

@app.post("/ask")
def ask(req: AskRequest):
    return store.answer(req.tenant_id, req.question) | {"agent_id": req.agent_id}

@app.post("/handoff")
def handoff(req: HandoffRequest):
    item = req.model_dump()
    item["status"] = "queued"
    handoffs.append(item)
    store.upsert_document(req.tenant_id, {"id": f"handoff-{len(handoffs)}", "title": f"Handoff {req.from_agent} → {req.to_agent}", "source": "agent-handoff", "type": "conversation", "memory_kind": "procedural", "text": f"{req.from_agent} handed to {req.to_agent}: {req.task}. {req.context}"})
    return item

@app.get("/memory")
def memory(tenant_id: str):
    memories = store.memory(tenant_id)
    durable_handoffs = [
        {"tenant_id": tenant_id, "from_agent": m["text"].split(" handed to ", 1)[0], "to_agent": m["text"].split(" handed to ", 1)[1].split(":", 1)[0], "task": m["text"].split(":", 1)[1].split(".", 1)[0], "status": "queued"}
        for m in memories if m.get("source") == "agent-handoff" and " handed to " in m.get("text", "")
    ]
    return {"tenant_id": tenant_id, "memories": memories, "handoffs": durable_handoffs or [h for h in handoffs if h["tenant_id"] == tenant_id]}

# Keep the demo usable in lightweight test clients that do not run lifespan hooks.
seed()

