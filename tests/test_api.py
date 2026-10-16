from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_demo_answer_has_trust_signals():
    response = client.post('/ask', json={'tenant_id':'acme','agent_id':'agent-a','question':'Who owns checkout latency?'})
    data = response.json()
    assert response.status_code == 200
    assert data['owner'] == 'Maya Chen'
    assert data['freshness']['current'] is True
    assert data['sources']
    assert 'MATCH' in data['cypher']
    assert any('Incident' in part for part in data['graph_path'])

def test_tenants_are_isolated():
    response = client.post('/ingest', json={'tenant_id':'other','title':'Private note','text':'Maya owns checkout latency.'})
    assert response.status_code == 200
    assert client.get('/memory?tenant_id=acme').json()['memories']
    assert all(x['tenant_id'] == 'other' for x in client.get('/memory?tenant_id=other').json()['memories'])

def test_handoff_is_shared_and_persistent():
    response = client.post('/handoff', json={'tenant_id':'acme','from_agent':'research-agent','to_agent':'support-agent','task':'Verify incident owner','context':'Check latest incident update'})
    assert response.json()['status'] == 'queued'
    memory = client.get('/memory?tenant_id=acme').json()
    assert memory['handoffs'][0]['to_agent'] == 'support-agent'
    assert any(x['type'] == 'conversation' for x in memory['memories'])

def test_memory_classification_and_deduplication():
    payload = {'tenant_id':'dedupe', 'title':'Runbook', 'text':'The team decided to always page the checkout owner.'}
    first = client.post('/ingest', json=payload).json()['memory']
    second = client.post('/ingest', json=payload).json()['memory']
    assert first['memory_kind'] == 'procedural'
    assert first['importance'] == 1.0
    assert second['deduplicated'] is True
    assert len(client.get('/memory?tenant_id=dedupe').json()['memories']) == 1

