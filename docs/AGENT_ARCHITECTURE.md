# Agent Gateway / Tool Broker Architecture

## Status

The setup demo implements this boundary with real Pi and a no-key deterministic
provider. See ../TODO.md and AI_HANDOFF.md for current priorities and code maps.

```text
Angular Chatbot
  -> FastAPI Gateway /assistant/stream
  -> AssistantProvider
       -> deterministic provider (implemented, local)
       -> PiAgentServiceAdapter (implemented HTTP/SSE client)
  -> FastAPI Tool Broker /internal/agent-runs/{run_id}/tools/{tool_name}
  -> authenticated Django API
```

`services/pi-agent` implements the separate Pi HTTP service using a temporary
local Pi CLI process per request. `services/pi-docs` remains a separate read-only
document CLI/container experiment, not the business-agent HTTP service.

## Trust and credential boundaries

- Browser business requests send cookies to Django; assistant requests send them
  to Gateway. Cookies are never forwarded to Pi.
- Gateway extracts the configured Django session and CSRF cookies and stores them
  in a process-local, TTL-bound run context.
- The request sent through `PiAgentServiceAdapter` contains a run-scoped
  execution token, never the Django cookie.
- The Tool Broker validates the execution token, run ID, tool allowlist and a
  tool-specific Pydantic argument model before it reads the stored cookie.
- Django restores `request.user` through Session/Authentication middleware and
  runs `FeaturePermission` for every real business API request.
- The Broker accepts no caller-provided URL, HTTP method or headers.
- Logs contain request/run IDs and lifecycle status, not Cookie or token values.

The current `InMemoryAgentRunStore` is intentionally a single-process skeleton.
Production multi-worker deployment requires a shared encrypted TTL store with
atomic consume/delete behavior and explicit capacity limits.

## Browser request

Angular calls:

```http
POST /assistant/stream
Content-Type: application/json
Cookie: sessionid=...
```

For setup the browser controls only `question`, `conversation_id`, and validated
`page_state`. Gateway loads owner-checked conversation/tool history from Django,
ignoring browser prose as history. The older VM demo retains its conversation
array. The browser cannot choose tools or the Tool Broker address.

## Gateway to Pi protocol

When `ASSISTANT_PROVIDER=pi`, the adapter calls the server-configured endpoint:

```http
POST {PI_AGENT_BASE_URL}/v1/agent/stream
Authorization: Bearer {PI_AGENT_SERVICE_TOKEN}
Accept: text/event-stream
```

The payload contains `request_id`, `run_id`, `conversation_id`, trusted `history`,
the validated question/page state,
`allowed_tools`, and a server-created `tool_broker` descriptor. The descriptor's
`base_url` comes only from `TOOL_BROKER_BASE_URL` configuration.

The Pi service may emit `tool_start`, `tool_result`, `delta`, and `error`.
The Gateway creates `meta` and `done`, enforces the overall timeout, observes
browser disconnects, records lifecycle audit logs, and deletes run state in a
`finally` block.

## Tool Broker protocol

Setup Broker tools: query_setup_state, create_admin_profile, create_admin_user,
create_instance and create_adapter. Local Pi ask_user_question never enters the
Broker. tools.py owns the exact argument models and fixed Django mappings.
The older deterministic VM feature uses:

```http
POST /internal/agent-runs/{run_id}/tools/query_vm_context
Authorization: Bearer {execution_token}
Content-Type: application/json

{"args":{"record_id":1}}
```

`QueryVmContextArguments` rejects extra fields and requires a positive integer.
The Broker maps this tool to the fixed Django endpoint:

```text
GET /api/demo/secure/page-context?record_id={record_id}
```

It forwards the stored Django Cookie and converts Django authentication,
permission, business and transport failures into a controlled `ToolResult`.
Cookie values never appear in that result.

## Implemented demo flow

For the main setup flow Pi selects tools, uses ask_user_question for missing
fields, queries existing relationships, then submits creates through Broker.
Django checks Session, CSRF, Group permissions, serializers and foreign keys.
Creates return the snapshot plus an explicit created_record for result cards.
Pi can use a new Profile ID in a subsequent User create in the same run.

Pi tool_result carries structured data; delta carries model prose/Markdown.
Angular renders sanitized Markdown and cards from successful created_record
results. Each user message starts a new run; Django stores owner-scoped turns
and actual Broker calls/results for cross-turn continuity and refresh restore.
History append requires the user's Session/CSRF and a separate Gateway credential;
Pi never receives that credential. See CONVERSATIONS.md for retention/limits.
Scoped Django-create idempotency is implemented (IDEMPOTENT_CREATES.md); broader
failure-recovery evaluations remain TODO. Investigation mode grants only the six
log-read tools plus clarification; no create tools. Log datasets are owner-scoped
and the synthetic fixture is fictional (LOG_INVESTIGATION.md).

### Older deterministic VM flow

The deterministic provider is a mock for model reasoning, but the surrounding
security and transport path is real:

1. Gateway creates request/run IDs and stores the session Cookie.
2. Provider emits `tool_start` for `query_vm_context`.
3. Provider invokes the same `ToolBrokerService` policy boundary with the
   short-lived execution token.
4. Broker calls Django with the stored Cookie.
5. Django restores the user and checks the `vm_association` readonly grant.
6. Provider emits `tool_result`, then deterministic `delta` events.
7. Gateway emits `done` and deletes the run context.

The deterministic provider calls the Broker service in-process. A real Pi
service calls the private HTTP Broker route; both paths use the same token,
allowlist, argument validation and Django client implementation.

## Configuration

```dotenv
ASSISTANT_PROVIDER=deterministic  # or pi
DJANGO_BASE_URL=http://127.0.0.1:8001
DJANGO_SESSION_COOKIE_NAME=sessionid
DJANGO_CSRF_COOKIE_NAME=csrftoken
PI_AGENT_BASE_URL=http://127.0.0.1:8010
PI_AGENT_SERVICE_TOKEN=
TOOL_BROKER_BASE_URL=http://127.0.0.1:8002
AGENT_RUN_TTL_SECONDS=120
AGENT_RUN_TIMEOUT_SECONDS=60
```

`TOOL_BROKER_BASE_URL` must resolve from the Pi service/container. It is never
accepted in a browser payload.

## Deferred production work

- Productionize the implemented Pi service and manage process/credential lifecycle.
- Replace process memory with an encrypted shared TTL run store.
- Put the Broker on a private network and add service identity/mTLS as needed.
- Add rate limits, quotas, metrics, durable audit export and overload control.
- Add distributed cancellation and a production task/worker lifecycle.
- Add PW520/ZAP only after the narrow agent/tool contract is stable.
