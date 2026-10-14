# Coexist Demo

> This repository is an architecture demo, not a production deployment. Its
> built-in credentials, development secret, SQLite databases, and permissive
> local CORS configuration must be replaced before production use.

This standalone demo shows:

- Django templates and Angular SPA routes living in one Django project
- `/legacy/...` routes rendered by Django
- `/new/...` routes served as an Angular shell
- DRF `APIView` with method-scoped serializers and pre-handler validation
- a standardized `{status, result, error}` API contract
- Angular interceptor handling `303` and `338` redirect semantics
- DRF-native feature authorization with explicit read-only/read-write grants
- input rejection, normalization, HTML escaping, and SQL parameter binding
- side-by-side Django ORM and SQLAlchemy declarative models
- a contextual assistant that combines Angular page state with canonical Django data
- a FastAPI orchestration boundary with Server-Sent Events streaming
- an isolated Pi document-agent service under `services/pi-docs/`

## Recommended Demo Walkthrough

The three navigation pages have different jobs:

1. Open `/new/legacy/report` first. Angular owns the shell and side navigation,
   while an iframe displays the server-rendered `/legacy/report/` Django
   template.
2. Open `/new/architecture` for the main interview walkthrough. Call the
   protected API while logged out, log in with the demo credentials, call it
   again, run the security examples, and compare Django ORM with SQLAlchemy.
3. Use `/new/demo/form` only as an API contract playground. Its JSON, query,
   upload, and redirect cards are four independent experiments, not sections of
   one business form.
4. Open `/new/context-assistant` after logging in. Select a VM, change the
   visible page state, and stream a context-aware answer through FastAPI.

On the API contract playground:

- `name`, `age`, and `active` demonstrate string, integer, and boolean values.
- `source` is sent as the nested value `metadata.source`.
- comma-separated `tags` are converted into a validated string array.
- `note` demonstrates an optional JSON property.
- search `term`, `limit`, and `active` demonstrate required and optional query
  parameters.
- the file input demonstrates a DRF `FileField` and validates extension,
  content type, and maximum size without saving the file.
- the redirect buttons have no business input; they demonstrate frontend
  handling of structured `303` and `338` API responses.

## Backend

Install dependencies once:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

```bash
cd backend
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py runserver 127.0.0.1:8001
```

## FastAPI Assistant Gateway

Run the assistant gateway in a second terminal:

```bash
cd coexist_demo
DJANGO_BASE_URL=http://127.0.0.1:8001 \
  ./.venv/bin/uvicorn assistant_gateway.app:app --host 127.0.0.1 --port 8002
```

### API key configuration

Copy the committed template to the ignored local secrets file:

```bash
cp .env.example .env
```

Configure future assistant providers in the root `.env` file:

```dotenv
ASSISTANT_PROVIDER=your-provider
# Paste the real key only in your ignored .env file.
ASSISTANT_API_KEY=
ASSISTANT_BASE_URL=https://api.example.com/v1
ASSISTANT_MODEL=your-model
```

API keys are backend-only and must never be placed in `frontend/`, Angular
environment files, browser storage, or committed source. Provider code reads
the centralized typed configuration like this:

```python
from assistant_gateway.config import get_assistant_settings

settings = get_assistant_settings()
api_key = settings.require_api_key()
model = settings.assistant_model
base_url = settings.assistant_base_url
```

`assistant_api_key` is stored as Pydantic `SecretStr`, so settings logs and
representations mask it. `require_api_key()` reveals it only at the provider
call boundary. The default deterministic provider does not require a key.

The assistant request path is:

```text
Angular transient page state + question
  -> FastAPI /assistant/stream
  -> Django /api/demo/secure/page-context?record_id=...
  -> DRF serializer validation + Django ORM
  -> FastAPI assistant provider
  -> SSE meta / delta / done events
  -> Angular ReadableStream parser
```

Django remains the source of truth. FastAPI forwards the Django session cookie
and never opens `db.sqlite3` directly. The browser is allowed to contribute only
the small Pydantic-validated UI state contract: selected VM, visible filter,
active panel, and expanded association ids.

The default `DeterministicAssistantProvider` requires no model key. Replace that
provider when connecting a real model. An agent SDK is intentionally not used
until the assistant needs autonomous tool selection, a multi-step agent loop,
long-running session state, or sub-agents.

## Pi Docs Sandbox

The repository now includes the isolated Pi document-agent runtime under
[`services/pi-docs`](services/pi-docs). It is deliberately kept outside both
the Django app and the FastAPI gateway so the three responsibilities remain
separate:

```text
frontend/             browser UI
backend/              Django data, session, and authorization boundary
assistant_gateway/    HTTP/SSE orchestration boundary
services/pi-docs/     containerized Pi execution boundary
```

Build it from the repository root:

```bash
docker compose \
  --project-directory services/pi-docs \
  -f services/pi-docs/compose.yaml \
  build
```

Run a one-shot documentation question using the host Pi login:

```bash
export DOCS_HOST_PATH="/absolute/path/to/approved/docs"
services/pi-docs/run-with-local-auth.sh \
  "Which document describes the sandbox network policy?"
```

Run an interactive terminal session:

```bash
services/pi-docs/run-with-local-auth.sh --interactive
```

This is currently an independently runnable CLI worker, not an HTTP service and
not yet the provider behind `/assistant/stream`. A safe production integration
should preserve the following boundary:

```text
Angular
  -> assistant_gateway (authenticated request, validation, SSE)
  -> private runner API or job queue
  -> one ephemeral pi-docs container with an approved read-only docs mount
  -> streamed result back through assistant_gateway
```

The browser must never receive Docker access or model credentials, and neither
the gateway nor the Pi container should mount the Docker socket. The current
Compose bridge network still permits general outbound traffic; before treating
this as a production sandbox, restrict egress to the required model endpoint
using infrastructure-level network policy. See
[`services/pi-docs/README.md`](services/pi-docs/README.md) for its exact security
boundary and limitations.

## Frontend

```bash
cd frontend
npm ci
npm start
```

To build Angular assets for Django:

```bash
cd frontend
npm run build
```

Then open:

- `http://127.0.0.1:8001/legacy/report/`
- `http://127.0.0.1:8001/new/demo/form`
- `http://127.0.0.1:8001/new/architecture`
- `http://127.0.0.1:8001/new/context-assistant`

The public-safe design decisions and interview framing are documented in
[`docs/MIGRATION_NOTES.md`](docs/MIGRATION_NOTES.md).

## Export the API schema

DRF can export the serializer-backed OpenAPI contract with its management
command:

```bash
cd backend
../.venv/bin/python manage.py generateschema \
  --title "Coexist Demo API" \
  --file ../docs/openapi.yaml
```

The older FDC project used a custom `manage.py exporturls` command that walked
`param_schemas`. This demo now uses DRF's standard `generateschema` path.

## Security & ORM Lab

Demo credentials:

```text
username: demo
password: DemoPass123!
```

The architecture lab demonstrates this request path:

```text
Django session middleware
  -> DRF APIView.dispatch
  -> ContractAPIView.initial
  -> DRF authentication + FeaturePermission
  -> method-scoped DRF Serializer
  -> request.validated_data
  -> Django ORM / SQLAlchemy
  -> FdcJsonResponse
```

Recommended walkthrough:

1. Log out and call the protected model endpoint. `APIView.dispatch` starts,
   but `FeaturePermission` returns `401` before serializer validation or the
   handler.
2. Log in and call it again. The response trace reaches DRF `APIView.dispatch`
   and shows the `model_comparison` read-only grant before
   `ModelComparisonQuerySerializer`.
3. Run the default security payload. HTML is escaped, surrounding whitespace is
   removed, and the SQL-shaped lookup term remains data.
4. Trigger the semicolon example. `SecurityInspectionSerializer` rejects the
   identifier with HTTP `444`.
5. Compare model queries. Both ORM results expose a SQL template and separate
   bound parameters.

The demo deliberately distinguishes:

- validation: reject values outside an allowed contract
- normalization: trim or coerce valid values
- output handling: HTML-escape text intended for display
- SQL injection defense: use ORM-generated parameterized queries

Deleting quotes from search input is not used as a SQL injection defense.

The two ORMs use separate local SQLite files so the demo remains standalone.
The architectural difference is the model/session API, not the database server.

Useful checks:

```bash
cd backend
../.venv/bin/python manage.py test

cd ../frontend
npm test -- --watch=false --browsers=ChromeHeadless
```
