from fastapi.testclient import TestClient
from app.main import app
import hashlib
import hmac
import json
import time

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

def test_slack_url_verification_and_signature(monkeypatch):
    secret = 'test-signing-secret'
    monkeypatch.setenv('SLACK_SIGNING_SECRET', secret)
    body = json.dumps({'type': 'url_verification', 'challenge': 'challenge-123'}).encode()
    timestamp = str(int(time.time()))
    signature = 'v0=' + hmac.new(secret.encode(), f'v0:{timestamp}:'.encode() + body, hashlib.sha256).hexdigest()
    response = client.post('/slack/events', content=body, headers={'X-Slack-Request-Timestamp': timestamp, 'X-Slack-Signature': signature, 'content-type': 'application/json'})
    assert response.status_code == 200
    assert response.json()['challenge'] == 'challenge-123'

def test_slack_rejects_bad_signature(monkeypatch):
    monkeypatch.setenv('SLACK_SIGNING_SECRET', 'test-signing-secret')
    response = client.post('/slack/events', content=b'{}', headers={'X-Slack-Request-Timestamp': str(int(time.time())), 'X-Slack-Signature': 'v0=bad', 'content-type': 'application/json'})
    assert response.status_code == 401

def test_company_brain_questions_have_graph_paths():
    customer = client.post('/ask', json={'tenant_id':'acme','question':'What did this customer ask for last month, and was it resolved?'}).json()
    dependency = client.post('/ask', json={'tenant_id':'acme','question':'What breaks if checkout-api goes down?'}).json()
    expertise = client.post('/ask', json={'tenant_id':'acme','question':'Who on the team has worked on checkout-api before?'}).json()
    assert 'Customer' in customer['graph_path'][0]
    assert 'System' in dependency['graph_path'][0]
    assert 'Person' in expertise['graph_path'][0]
    assert 'MATCH' in dependency['cypher']

def test_graph_algorithms_are_exposed():
    data = client.get('/graph/insights?tenant_id=acme').json()
    assert set(data['algorithms']) == {'shortest_path', 'pagerank', 'community_detection'}
    assert 'shortestPath' in data['algorithms']['shortest_path']['cypher']
    assert 'pageRank' in data['algorithms']['pagerank']['cypher']

