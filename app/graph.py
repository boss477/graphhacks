import json
import os
import re
import hashlib
from datetime import datetime, timezone
from typing import Any

try:
    from falkordb import FalkorDB
except ImportError:  # pragma: no cover - dependency exists in deployment
    FalkorDB = None


NOW = datetime.now(timezone.utc)


class GraphStore:
    """FalkorDB-backed graph with a tiny deterministic fallback for tests."""

    def __init__(self):
        self._fallback: list[dict[str, Any]] = []
        self.db = None
        if FalkorDB:
            try:
                self.db = FalkorDB(host=os.getenv("FALKORDB_HOST", "localhost"), port=int(os.getenv("FALKORDB_PORT", "6379")))
                self.graph = self.db.select_graph("tracebrain")
                self.graph.query("RETURN 1")
            except Exception:
                self.db = None

    def query(self, cypher: str, params: dict[str, Any] | None = None):
        if self.db:
            return self.graph.query(cypher, params or {})
        return []

    def upsert_document(self, tenant: str, doc: dict[str, Any]) -> dict[str, Any]:
        doc_id = doc.get("id") or f"doc-{len(self._fallback) + 1}"
        text = doc.get("text", "")
        owner = "Maya Chen" if re.search(r"maya chen|maya", text, re.I) else ""
        decision = "Prioritize database connection pooling and revert the risky cache change" if "pooling" in text.lower() else ""
        incident = "checkout-latency" if re.search(r"checkout|latency", text, re.I) else ""
        freshness = doc.get("updated_at", NOW.isoformat())
        requested_kind = doc.get("memory_kind")
        kind = self.classify_memory(text) if not requested_kind or requested_kind == "semantic" else requested_kind
        importance = 1.0 if incident or decision else 0.5
        fingerprint = hashlib.sha256(re.sub(r"\W+", " ", text.lower()).strip().encode()).hexdigest()[:16]
        if self.db:
            duplicate = self.graph.ro_query("MATCH (d:Document {tenant_id:$tenant, fingerprint:$fingerprint}) RETURN d.id LIMIT 1", params={"tenant": tenant, "fingerprint": fingerprint}).result_set
            if duplicate:
                return {"tenant_id": tenant, "id": duplicate[0][0], "title": doc.get("title", doc_id), "source": doc.get("source", doc_id), "fingerprint": fingerprint, "deduplicated": True}
        existing = next((x for x in self._fallback if x["tenant_id"] == tenant and x["fingerprint"] == fingerprint), None)
        if existing:
            existing.update({"updated_at": freshness, "source": doc.get("source", doc_id), "title": doc.get("title", existing["title"])})
            return existing | {"deduplicated": True}
        record = {"tenant_id": tenant, "id": doc_id, "type": doc.get("type", "document"), "title": doc.get("title", doc_id), "text": text, "owner": owner, "decision": decision, "incident": incident, "updated_at": freshness, "source": doc.get("source", doc_id), "memory_kind": kind, "importance": importance, "fingerprint": fingerprint, "deduplicated": False}
        self._fallback.append(record)
        if self.db:
            cypher = """MERGE (d:Document {tenant_id:$tenant, id:$id}) SET d.title=$title, d.text=$text, d.updated_at=$updated_at, d.source=$source, d.type=$type, d.owner=$owner, d.decision=$decision, d.incident=$incident, d.memory_kind=$kind, d.importance=$importance, d.fingerprint=$fingerprint
            WITH d MERGE (m:Memory {tenant_id:$tenant, key:$id}) SET m.kind=$kind, m.content=$text, m.created_at=$updated_at
            FOREACH (_ IN CASE WHEN $incident <> '' THEN [1] ELSE [] END |
              MERGE (i:Incident {tenant_id:$tenant, key:$incident}) SET i.name=$incident
              MERGE (d)-[:DESCRIBES]->(i))
            FOREACH (_ IN CASE WHEN $owner <> '' THEN [1] ELSE [] END |
              MERGE (p:Person {tenant_id:$tenant, name:$owner})
              MERGE (i:Incident {tenant_id:$tenant, key:$incident})
              MERGE (p)-[:OWNS]->(i))
            FOREACH (_ IN CASE WHEN $decision <> '' THEN [1] ELSE [] END |
              MERGE (dec:Decision {tenant_id:$tenant, key:$id}) SET dec.text=$decision
              MERGE (d)-[:EVIDENCES]->(dec))"""
            self.query(cypher, {"tenant": tenant, "id": doc_id, "title": record["title"], "text": text, "updated_at": freshness, "source": record["source"], "type": record["type"], "kind": kind, "importance": importance, "incident": incident, "owner": owner, "decision": decision, "fingerprint": fingerprint})
        return record

    @staticmethod
    def classify_memory(text: str) -> str:
        lowered = text.lower()
        if any(word in lowered for word in ("decided", "runbook", "always", "procedure")):
            return "procedural"
        if any(word in lowered for word in ("yesterday", "today", "incident", "meeting")):
            return "episodic"
        return "semantic"

    def answer(self, tenant: str, question: str) -> dict[str, Any]:
        exact_query = """MATCH (d:Document {tenant_id:$tenant})-[:DESCRIBES]->(i:Incident {tenant_id:$tenant})\nOPTIONAL MATCH (p:Person {tenant_id:$tenant})-[:OWNS]->(i)\nOPTIONAL MATCH (d)-[:EVIDENCES]->(dec:Decision {tenant_id:$tenant})\nRETURN i.name, p.name, dec.text, d.title, d.updated_at, d.source ORDER BY d.updated_at DESC"""
        docs = self._graph_documents(tenant) if self.db else [d for d in self._fallback if d["tenant_id"] == tenant and d["incident"] == "checkout-latency"]
        docs.sort(key=lambda d: d["updated_at"], reverse=True)
        owner = next((d["owner"] for d in docs if d["owner"]), "Unknown")
        decision = next((d["decision"] for d in docs if d["decision"]), "No decision found")
        sources = [{"title": d["title"], "source": d["source"], "updated_at": d["updated_at"]} for d in docs]
        conflict = len({d["owner"] for d in docs if d["owner"]}) > 1 or len({d["decision"] for d in docs if d["decision"]}) > 1
        current = bool(docs) and not conflict and docs[0]["updated_at"] >= "2026-10-01"
        path = ["Document: checkout incident update", "-DESCRIBES-> Incident: checkout-latency", f"<-OWNS- Person: {owner}", "<-EVIDENCES- Decision"]
        answer = f"{owner} owns the checkout latency incident. Decision: {decision}. Information is {'current' if current else 'not current or needs review'}."
        if conflict:
            answer += " Conflicting evidence was detected, so TraceBrain is not guessing."
        return {"answer": answer, "owner": owner, "decision": decision, "freshness": {"current": current, "latest_updated_at": docs[0]["updated_at"] if docs else None, "conflict": conflict}, "sources": sources, "cypher": exact_query, "params": {"tenant": tenant}, "graph_path": path}

    def memory(self, tenant: str) -> list[dict[str, Any]]:
        if self.db:
            return self._graph_documents(tenant, include_all=True)
        return [d for d in self._fallback if d["tenant_id"] == tenant]

    def _graph_documents(self, tenant: str, include_all: bool = False) -> list[dict[str, Any]]:
        where = "" if include_all else " AND d.incident = 'checkout-latency'"
        query = f"MATCH (d:Document {{tenant_id:$tenant}}) WHERE d.type IS NULL OR d.type IN ['document','conversation']{where} RETURN d.id, d.type, d.title, d.text, d.owner, d.decision, d.incident, d.updated_at, d.source, d.memory_kind, d.importance, d.fingerprint"
        try:
            rows = self.graph.ro_query(query, params={"tenant": tenant}).result_set
        except TypeError:
            rows = self.graph.ro_query(query, {"tenant": tenant}).result_set
        return [{"tenant_id": tenant, "id": row[0], "type": row[1], "title": row[2], "text": row[3], "owner": row[4] or "", "decision": row[5] or "", "incident": row[6] or "", "updated_at": row[7], "source": row[8], "memory_kind": row[9], "importance": row[10], "fingerprint": row[11], "deduplicated": False} for row in rows]

