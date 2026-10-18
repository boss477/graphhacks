# TraceBrain production research

Research date: 2026-10-17. This document separates hackathon requirements from the work required to safely connect real Slack workspaces.

## Graph Hacks 2026 submission checklist

TraceBrain is submitted to **Track 03 — Company Brain**:

- Track 03: documents, conversations, people, incidents, decisions, ownership, source tracing, freshness, conflict handling, and connected company knowledge.
- Shared episodic, semantic, and procedural memory plus agent handoffs are supporting implementation features for the Company Brain experience.
- FalkorDB must be load-bearing. The README and demo must show the graph model, Cypher, and a graph-backed answer—not only a graph visualization.
- Use synthetic/public data only. Explicitly disclose AI assistance.
- Submit the public repository, setup instructions, architecture, representative Cypher, and a working demo video.

Sources: [Graph Hacks tracks](https://www.wemakedevs.org/hackathons/falkordb), [rules](https://www.wemakedevs.org/hackathons/falkordb/rules), [resources](https://www.wemakedevs.org/hackathons/falkordb/resources).

## Slack integration plan

The safe MVP is a bot-scoped, selected-channel integration:

1. OAuth v2 installation with `state`, HTTPS redirect, server-side code exchange, encrypted installation/token storage, and token rotation.
2. Request only the scopes needed for selected channels:
   - `channels:read`, `channels:history`
   - `groups:read`, `groups:history` only when private-channel support is explicitly enabled
   - `app_mentions:read`, `chat:write` only if TraceBrain answers in Slack
3. Subscribe to `message.channels`, `message.groups`, `app_mention`, edits, deletions, `app_uninstalled`, `tokens_revoked`, and `app_rate_limited` as applicable.
4. Verify `X-Slack-Signature` against the raw request body and reject timestamps outside the replay window.
5. Handle URL verification, enqueue the event, and return HTTP 200 within three seconds.
6. Deduplicate using Slack's globally unique `event_id`; use a second domain key such as `slack:{team_id}:{channel_id}:{message_ts}`.
7. Process asynchronously through a durable queue. Retry with backoff, honor `Retry-After`, and dead-letter poison events.
8. Handle message edits/deletions and uninstall deletion. Never expose indexed content to a TraceBrain user who could not access it in Slack.

Do not make `search.messages`, user tokens, `files:read`, `admin.*`, or unrestricted historical backfill part of the MVP. Slack history/replies rate limits and permissions make those poor defaults.

Sources: [Slack OAuth](https://docs.slack.dev/authentication/installing-with-oauth/), [Events API](https://docs.slack.dev/apis/events-api/), [request verification](https://docs.slack.dev/authentication/verifying-requests-from-slack/), [message events](https://docs.slack.dev/reference/events/message/), [history](https://docs.slack.dev/reference/methods/conversations.history/), [rate limits](https://docs.slack.dev/apis/web-api/rate-limits/), [token rotation](https://docs.slack.dev/authentication/using-token-rotation/), [Marketplace AI/privacy guidance](https://docs.slack.dev/slack-marketplace/slack-marketplace-app-guidelines-and-requirements/).

## Production architecture

```text
Slack OAuth + Events API
        |
        v
FastAPI ingress -- verify/dedupe/enqueue --> Redis Streams or managed queue
                                                   |
                                                   v
                                      ingestion workers + retry/DLQ
                                                   |
                                                   v
                                  tenant-isolated FalkorDB graphs
                                                   |
                                                   v
                                      authenticated query API/UI
```

Required production changes from the hackathon MVP:

- Authenticate API calls; derive the tenant from identity and Slack `team_id`, never from an untrusted request body alone.
- Prefer one FalkorDB graph per tenant, with strict graph-name validation and ACLs.
- Remove the in-memory fallback from the production deployment; readiness must fail when FalkorDB is unavailable.
- Move handoffs and Slack inbox state out of process memory into durable storage.
- Use persistent FalkorDB volumes, authentication, private networking, TLS, backups, and pinned image versions.
- Add `/health/live` and `/health/ready`, structured logs, tracing, queue metrics, DLQ metrics, and FalkorDB latency/error metrics.
- Add claim-level provenance and bi-temporal fields (`valid_from`, `valid_to`, `observed_at`, `ingested_at`).
- Model conflicts as durable records preserving both candidate claims and an explicit resolution state.

## Demo video: two-minute cut

| Time | Show | Proof |
|---|---|---|
| 0:00–0:08 | TraceBrain promise | Company memory that verifies, not guesses |
| 0:08–0:20 | Fragmented incident context | Why ownership and decisions are hard to recover |
| 0:20–0:45 | Ask the checkout latency question | Owner, decision, current status |
| 0:45–1:03 | Reveal sources, graph path, Cypher | FalkorDB is load-bearing and explainable |
| 1:03–1:22 | Add conflicting synthetic evidence | Conflict warning; no invented answer |
| 1:22–1:42 | Research agent hands off to support agent | Shared durable memory across agents |
| 1:42–1:53 | Show measured test metrics | Only numbers actually tested |
| 1:53–2:00 | Close on impact | Every agent starts with verified context |

Do not spend the opening minute on architecture. Show the business question first, then prove why the answer is trustworthy.

## API and integration inventory

### TraceBrain APIs

- `POST /ingest`: source document/conversation normalization and graph write.
- `POST /ask`: authenticated, tenant-scoped Cypher retrieval with answer, sources, freshness, conflicts, and path.
- `POST /handoff`: typed durable handoff with source evidence references and lifecycle status.
- `GET /memory`: authorized memory inspection.
- `GET /health/live`, `GET /health/ready`: liveness/readiness.
- `POST /slack/events`: signed Slack Events API ingress.
- `GET /slack/oauth/start`, `GET /slack/oauth/callback`: OAuth v2 installation flow.

### External APIs worth adding later

Use read-only evidence adapters before broad write integrations:

- Slack: selected channels and threads.
- GitHub: incidents, PRs, ownership, and deployment evidence.
- Sentry: incidents and error timelines.
- Linear/Jira: issues, projects, and owners.
- Notion/Google Drive: documents and decisions.

Company Brain demonstrates a connector-oriented model; TraceBrain should preserve each adapter's source permissions and keep live tool evidence distinct from durable memory. Do not add every connector before the Slack path, conflict workflow, and provenance model are reliable.

## Reference projects

TraceBrain is independently implemented. It borrows ideas—not runtime code—from [Company Brain](https://github.com/supermemoryai/company-brain) and [HippocampAI](https://github.com/rexdivakar/HippocampAI): scoped company memory, provenance lineage, temporal facts, conflict preservation, context assembly, and multi-agent handoff permissions.

