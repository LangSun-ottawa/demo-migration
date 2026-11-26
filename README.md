# Coexist Demo

Angular + Django migration demo with a Pi tool-calling assistant. Users create
Admin Profiles, Admin Users, Instances and Adapter configurations through chat,
then inspect/edit/delete records in traditional management pages.

For AI/developer continuation, read [AGENTS.md](AGENTS.md),
[TODO.md](TODO.md) and [AI handoff](docs/AI_HANDOFF.md).
Next: server-side conversation/tool history, business-chain failure recovery,
then idempotent writes. These are planned work, not already implemented.

## Flow

```text
Angular chat -> FastAPI Gateway -> Pi Agent Service
                                  -> local ask_user_question
                                  -> FastAPI Tool Broker -> Django API -> SQLite
                 <- SSE text/tool events <- tool results and model reasoning
```

- Django restores users from Session cookies and checks CSRF, Group-based
  FeaturePermission, DRF serializers and business relationships for every write.
- Gateway retains cookies only for the run; Pi gets a short-lived execution token.
- Pi selects tools from TypeBox definitions, asks for missing fields, and reasons
  over actual results. Broker validates token/allowlist/Pydantic args and calls
  fixed Django routes. It does not accept arbitrary URLs, methods or headers.
- AI Markdown is safely rendered; cards use Django's explicit created_record.
- Profile → User and Instance → Adapter are independent business dependencies.
- AdminUserRecord is demo business data, not a Django login account. AdminProfile
  does not grant auth Groups. Adapters save configuration without real connections.

The business Pi HTTP service is implemented in `services/pi-agent` and wraps the
local Pi CLI. The deterministic provider is a no-key reasoning mock using real
Broker/Django calls. `services/pi-docs` is a separate document Docker sandbox.

## Install

From repository root, with Python 3 and Node/npm installed:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix services/pi-agent ci
cp -n .env.example .env
.venv/bin/python backend/manage.py migrate
```

`.env.example` defaults to deterministic. For real model calls, install Pi CLI
and configure a working login/model, then edit the ignored `.env` locally:

```dotenv
ASSISTANT_PROVIDER=pi
PI_AGENT_BASE_URL=http://127.0.0.1:8010
PI_AGENT_SERVICE_TOKEN=<choose-a-local-service-secret>
TOOL_BROKER_BASE_URL=http://127.0.0.1:8002
PI_PROVIDER=openai-codex
PI_MODEL=
```

An empty PI_MODEL follows the model selected in local Pi settings at service
startup. Restart Pi Service after changing the selected model. The service loads
the same root `.env`. Do not copy auth files or keys into this repository.

## Run (four terminals)

```bash
# Terminal 1: Django
.venv/bin/python backend/manage.py runserver 127.0.0.1:8001
```

```bash
# Terminal 2: Gateway + Tool Broker
.venv/bin/uvicorn assistant_gateway.app:app --host 127.0.0.1 --port 8002
```

```bash
# Terminal 3: business Pi HTTP service (omit for deterministic provider)
.venv/bin/uvicorn --app-dir services/pi-agent app:app --host 127.0.0.1 --port 8010
```

```bash
# Terminal 4: Angular
npm --prefix frontend start -- --host 127.0.0.1
```

Open **http://127.0.0.1:4200/setup**. Demo login: `demo` / `DemoPass123!`.
Try creating a Profile and User, or an Instance and Adapter. Pi requests missing
information before submission; created cards link to the corresponding lists.

Health: `http://127.0.0.1:8002/health` and `http://127.0.0.1:8010/health`.
Health alone does not prove model connectivity; test a clarification/query through
the chat when checking Pi access.

## Code map and contracts

| Directory | Responsibility |
| --- | --- |
| frontend/src/app/pages/setup-demo | Chat input, events, Markdown, result cards |
| frontend/src/app/pages/resource-list | Four traditional CRUD pages |
| assistant_gateway | Request/run protocol, provider adapter, session-bound Broker |
| services/pi-agent | Pi HTTP/SSE service, tool schemas and execution handlers |
| backend/demoapp | Django models, auth, permissions, serializers and business APIs |
| services/pi-docs | Independent read-only document CLI/container experiment |

Read [AI_HANDOFF.md](docs/AI_HANDOFF.md) for a file-by-file request walkthrough,
[AGENT_ARCHITECTURE.md](docs/AGENT_ARCHITECTURE.md) for credential boundaries, and
[ASSISTANT_SSE_PROTOCOL.md](docs/ASSISTANT_SSE_PROTOCOL.md) for event payloads.

Tool schemas declare required values; they do not automatically implement
clarification or enforce that values came from the user. Pi coordinates tool
selection; Django enforces business validity. Current history is recent browser
text in sessionStorage, not a durable server-side conversation. See TODO.md.

## Verification

```bash
.venv/bin/python -m unittest assistant_gateway.tests
```

```bash
cd backend
../.venv/bin/python manage.py test
```

```bash
cd frontend
npm run build
npm test -- --watch=false --browsers=ChromeHeadless
```

Pi document path-policy tests: `npm --prefix services/pi-docs test`.
Build frontend assets before using Django's `/new/setup` shell:
`npm --prefix frontend run build`.

## Older migration examples

The main navigation stays small. Secondary routes remain for studying migration:

- `/legacy/report/`: Django template; `/new/legacy/report` embeds it in Angular.
- `/new/demo/form`: JSON/query/upload and legacy 303/338 redirect experiments.
- `/new/architecture`: Session auth, serializer validation and ORM comparisons.
- `/new/context-assistant`: older VM-context deterministic experiment. Its
  query_vm_context tool is not registered in the current business Pi extension.

On the Angular dev port, omit the `/new` prefix. Django APIs retain the
`{status, result, error}` response envelope. DRF ContractAPIView validates inputs
in initial(), after authentication/permissions and before the handler.
The DRF/Pydantic comparison endpoints are educational public echo examples,
not the protected business API authorization pattern.

[MIGRATION_NOTES.md](docs/MIGRATION_NOTES.md) explains routing and validation;
[DRF_PYDANTIC_COMPARISON.md](docs/DRF_PYDANTIC_COMPARISON.md) compares validators.
Export DRF OpenAPI with `manage.py generateschema`; the committed older export
may lag newer setup endpoints (tracked in TODO.md).

For the independent docs sandbox, see [services/pi-docs/README.md](services/pi-docs/README.md).
It is not the business-chat service and has no required runtime dependency on it.

This is a local demo, not a production deployment. Demo credentials, development
settings, SQLite, local Pi identity and single-process run memory require an
explicit deployment design before public use. Secrets, databases, personal notes
and unrelated source-project material must not be committed.
