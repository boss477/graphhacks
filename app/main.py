from pathlib import Path
import hashlib
import hmac
import os
import time
import uuid
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import httpx
from pydantic import BaseModel, Field
from .graph import GraphStore

app = FastAPI(title="TraceBrain", version="0.1.0")
app.mount("/frontend", StaticFiles(directory=Path(__file__).parent.parent / "frontend"), name="frontend")
store = GraphStore()
handoffs: list[dict] = []
oauth_states: set[str] = set()
slack_events: set[str] = set()

SEED = [
    {"id": "incident-update", "title": "Checkout incident update", "source": "incident-2026-10-14.md", "type": "document", "memory_kind": "semantic", "updated_at": "2026-10-14T09:00:00+00:00", "text": "Incident checkout latency is owned by Maya Chen. The team decided to prioritize database connection pooling and revert the risky cache change."},
    {"id": "support-thread", "title": "Support agent handoff", "source": "conversation-support-2026-10-14.txt", "type": "conversation", "memory_kind": "episodic", "updated_at": "2026-10-14T10:00:00+00:00", "text": "Maya confirms the checkout latency incident owner and the database connection pooling decision."},
    {"id": "company-map", "title": "Company service map", "source": "architecture-2026-10-12.md", "type": "document", "memory_kind": "semantic", "updated_at": "2026-10-12T12:00:00+00:00", "text": "Team Checkout Platform owns project Checkout Revamp. Maya Chen worked on service checkout-api. checkout-api depends on payments-api and impacts order-service."},
    {"id": "customer-case", "title": "Customer case 1042", "source": "ticket-1042.md", "type": "ticket", "memory_kind": "episodic", "updated_at": "2026-10-13T14:00:00+00:00", "text": "Customer Acme Retail asked for checkout latency investigation last month. Ticket INC-1042 was resolved by Maya Chen."},
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
    return {"ok": True, "service": "tracebrain", "graph": "falkordb" if store.db else "fallback", "slack_oauth_configured": bool(os.getenv("SLACK_CLIENT_ID") and os.getenv("SLACK_CLIENT_SECRET")), "slack_signing_configured": bool(os.getenv("SLACK_SIGNING_SECRET"))}

@app.get("/slack/oauth/start", include_in_schema=False)
def slack_oauth_start():
    client_id = os.getenv("SLACK_CLIENT_ID")
    redirect_uri = os.getenv("SLACK_REDIRECT_URI", "http://localhost:8000/slack/oauth/callback")
    if not client_id:
        raise HTTPException(503, "Slack OAuth is not configured. Set SLACK_CLIENT_ID.")
    state = uuid.uuid4().hex
    oauth_states.add(state)
    scopes = os.getenv("SLACK_BOT_SCOPES", "channels:read,channels:history,groups:read,groups:history,app_mentions:read,chat:write")
    url = "https://slack.com/oauth/v2/authorize?" + httpx.QueryParams({"client_id": client_id, "scope": scopes, "redirect_uri": redirect_uri, "state": state})
    return RedirectResponse(url)

@app.get("/slack/oauth/callback", include_in_schema=False)
async def slack_oauth_callback(code: str | None = None, state: str | None = None, error: str | None = None):
    if error:
        raise HTTPException(400, f"Slack OAuth denied: {error}")
    if not code or not state or state not in oauth_states:
        raise HTTPException(400, "Invalid or expired Slack OAuth state")
    oauth_states.remove(state)
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post("https://slack.com/api/oauth.v2.access", data={"client_id": os.getenv("SLACK_CLIENT_ID"), "client_secret": os.getenv("SLACK_CLIENT_SECRET"), "code": code, "redirect_uri": os.getenv("SLACK_REDIRECT_URI", "http://localhost:8000/slack/oauth/callback")})
    data = response.json()
    if not data.get("ok"):
        raise HTTPException(502, f"Slack OAuth exchange failed: {data.get('error', 'unknown_error')}")
    team = data.get("team", {}).get("id")
    # Local MVP: record the installation as synthetic graph metadata. Production should encrypt this in a control-plane database.
    store.upsert_document(team or "slack-installation", {"id": f"slack-installation-{team}", "title": "Slack installation", "source": "slack-oauth", "type": "document", "memory_kind": "procedural", "text": f"Slack workspace {team} installed TraceBrain with granted scopes: {data.get('scope', '')}."})
    return JSONResponse({"ok": True, "team_id": team, "scope": data.get("scope"), "message": "Slack connected. Tokens are intentionally not returned to the browser."})

@app.post("/slack/events", include_in_schema=False)
async def slack_events_endpoint(request: Request):
    raw = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    secret = os.getenv("SLACK_SIGNING_SECRET")
    if not secret:
        raise HTTPException(503, "Slack signing secret is not configured")
    try:
        if abs(time.time() - int(timestamp)) > 300:
            raise ValueError("stale")
    except ValueError:
        raise HTTPException(401, "Invalid Slack request timestamp")
    base = f"v0:{timestamp}:{raw.decode('utf-8')}".encode()
    expected = "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "Invalid Slack signature")
    payload = await request.json()
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}
    event_id = payload.get("event_id")
    if event_id and event_id in slack_events:
        return {"ok": True, "duplicate": True}
    if event_id:
        slack_events.add(event_id)
    event = payload.get("event", {})
    if event.get("type") == "message" and event.get("text") and not event.get("subtype"):
        team_id = payload.get("team_id", "unknown-team")
        store.upsert_document(team_id, {"id": f"slack:{team_id}:{event.get('channel')}:{event.get('ts')}", "title": "Slack message", "source": "slack", "type": "conversation", "memory_kind": "episodic", "updated_at": event.get("ts"), "text": event["text"]})
    return {"ok": True, "event_id": event_id}

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

@app.get("/graph/insights")
def graph_insights(tenant_id: str):
    return store.graph_insights(tenant_id)

# Keep the demo usable in lightweight test clients that do not run lifespan hooks.
seed()

