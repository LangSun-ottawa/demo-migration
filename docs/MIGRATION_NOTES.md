# Migration Notes

## Objective

This demo isolates a modernization pattern without depending on the source
application:

- Keep server-rendered Django routes available.
- Serve a separately built Angular application from Django static assets.
- Standardize request validation with DRF serializers while preserving the
  existing response envelope.
- Add a FastAPI orchestration boundary for a contextual streaming assistant.

## Routing Ownership

Django owns the top-level URL boundary:

- `/legacy/...` renders Django templates directly.
- `/new/...` returns one Angular shell, after which Angular Router owns the
  client-side route.
- `/api/demo/...` remains a Django API surface.
- FastAPI runs separately and exposes `/assistant/stream`.

The legacy report can also appear inside the Angular shell through a
same-origin iframe. This allows navigation and presentation to migrate before
the underlying server-rendered page is rewritten.

## Request Contract

Each Django class-based API view declares method-scoped DRF serializer classes.
`ContractAPIView` deliberately inherits DRF's `APIView.dispatch`; it performs
input validation in `initial()`, after DRF constructs `Request` and before the
HTTP method handler is called. Validated values are stored on
`request.validated_data`; invalid input is adapted to the existing
`{status, result, error}` envelope.

This keeps validation outside feature handlers and makes each view's accepted
input explicit. The demo includes string, integer, boolean, nested object,
list, query-string, and file examples.

## Authentication, Feature Authorization, And Data Access

Django session middleware resolves the logged-in user. Protected API views use
the custom DRF `FeaturePermission`: each view declares a `feature_key`, while
`method_permissions` declares whether each HTTP method needs `readonly` or
`readwrite`. Grants are represented by Django groups such as
`feature:model_comparison:readonly`. Anonymous requests receive `401`; logged-in
users without a sufficient feature grant receive `403`. DRF runs this check in
`APIView.initial()`, before serializer validation and the handler.

The ORM comparison intentionally shows two data-access styles:

- `DeviceRecord` uses Django ORM and the main Django SQLite database.
- `AuditRecord` uses SQLAlchemy declarative models and a separate demo SQLite
  database.

Both examples treat user input as bound data rather than executable SQL.

## Contextual Assistant Flow

```text
Angular question + narrow transient page state
  -> FastAPI /assistant/stream
  -> authenticated Django page-context API
  -> DRF serializer validation + Django ORM
  -> replaceable AssistantProvider
  -> SSE meta / delta / done events
  -> Angular ReadableStream parser
```

Angular owns presentation state such as the selected record, visible filter,
active panel, and expanded rows. Django owns canonical business context.
FastAPI forwards the Django session cookie and fetches that canonical context
instead of reading Django's database directly.

The default `DeterministicAssistantProvider` keeps the repository runnable
without an API key. A real model provider can replace it without changing the
Django API, FastAPI endpoint contract, SSE framing, or Angular parser.

## Why No Agent SDK Yet

The current interaction performs one bounded context fetch and one streamed
answer. It does not need autonomous tool selection, repeated tool calls,
durable agent memory, sub-agents, or a long-running task loop. The provider
interface preserves an upgrade path without introducing those concerns before
they are required.

## Interview Framing

- Modernization was separated by routing and ownership boundaries rather than
  attempted as a single rewrite.
- The browser contributes narrow UI state, while authenticated Django remains
  the source of truth for business data.
- FastAPI acts as an anti-corruption and orchestration layer, not a second data
  access layer.
- Streaming is a transport decision independent of the model provider.
- An agent SDK should be introduced when agent behavior is required, not only
  because the UI contains a chat box.
- The migration keeps the legacy response contract, but uses DRF serializers
  rather than extending a private schema DSL. DRF's `generateschema` command
  can export the resulting OpenAPI contract.
