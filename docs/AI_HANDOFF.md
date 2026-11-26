# AI handoff: current implementation

Reviewed 2026-11-25. This is the entry document for an AI or developer continuing
the repository. Read AGENTS.md and TODO.md; inspect actual configuration locally.
Do not infer that a configured service is currently running.

## Product and scope

A migration demo with Angular presentation, Django Session-authenticated APIs,
and a Pi chatbot that creates four kinds of demo business records. Users verify
results via traditional resource lists. Keep this small and understandable.

AdminProfile → AdminUserRecord.profile; ManagedInstance → AdapterConfig.instance.
These are two independent chains. AdminUserRecord is not django.contrib.auth.User;
AdminProfile.access_level is business metadata, not the login user's auth grant.
Adapters save configuration and never establish a real connection.

## Request flow and reading order

```text
Angular send(question, recent text history, page_state)
  -> Gateway POST /assistant/stream
     -> validate request; create request_id/run_id
     -> store Django session/CSRF cookie temporarily; create execution token
     -> PiAgentServiceAdapter POST /v1/agent/stream
        -> local Pi CLI + extension + allowlist + conversation prompt
        -> model chooses registered tools
           -> ask_user_question: local structured question, end this turn
           -> business tool: Broker POST /internal/agent-runs/{run_id}/tools/{name}
              -> token/TTL/allowlist/argument checks
              -> fixed Django API with stored cookie and CSRF token
              -> SessionAuthentication + FeaturePermission + DRF serializer
              -> ORM write/query -> JSON ToolResult -> Pi continues reasoning
        -> Pi JSONL events adapted to SSE
     -> Gateway meta/done, timeout, run cleanup
  -> Angular text/progress/error + Markdown + created-record cards
```

| File | Responsibility |
| --- | --- |
| frontend/src/app/pages/setup-demo/setup-demo.component.ts | send, history, event handling, card persistence |
| frontend/src/app/services/setup-assistant.service.ts | browser fetch/SSE |
| frontend/src/app/services/context-assistant.service.ts | shared event union/parser, older VM feature |
| assistant_gateway/app.py | Gateway, Pi selection, internal Broker route, lifecycle |
| assistant_gateway/protocol.py | request, tool and SSE payload models |
| assistant_gateway/providers.py | async provider interface, Pi adapter, deterministic mock |
| assistant_gateway/run_store.py | process-local run TTL, hashed execution token, cookie lifecycle |
| assistant_gateway/tools.py | fixed API routes, Pydantic arguments, Broker authorization |
| services/pi-agent/app.py | authenticated Pi HTTP service, prompt, subprocess and event mapping |
| services/pi-agent/business-tools.ts | TypeBox tool schemas and handlers |
| backend/demoapp/api/permissions.py | actual user Group-based feature authorization |
| backend/demoapp/api/serializers.py | Django parameter validation |
| backend/demoapp/api/views.py | setup snapshot/CRUD and explicit created_record response |
| backend/demoapp/models.py | four demo models and relations |
| frontend/src/app/pages/setup-demo/assistant-markdown.pipe.ts | escaped HTML + Markdown rendering |
| frontend/src/app/pages/setup-demo/created-record.ts | cards from authoritative tool results |

## Tools and messages

Pi registers ask_user_question, query_setup_state, create_admin_profile,
create_admin_user, create_instance and create_adapter. The first is local and
never calls Django; the others use the Broker. Tool definitions, not keyword
branches, guide the real Pi provider. The deterministic provider is explicitly
a no-key mock and has narrower language understanding.

Each browser message starts a new run/temporary Pi process. Clarification ends
the turn; the next user reply starts a new run with recent user/assistant text.
The UI stores messages/cards in sessionStorage. Full cross-turn tool history,
server-owned conversations and idempotency are NOT implemented; see TODO.md.

Gateway owns meta/done. Pi owns tool_start/tool_result/delta/error. Call IDs
correlate tool events. Business results contain the full snapshot plus
created_record: {resource, record}. Cards use this object only on success;
they do not scrape the assistant text or select the last array entry.
See [SSE protocol](ASSISTANT_SSE_PROTOCOL.md).

## Running and verification

Use root README commands. Main UI is http://127.0.0.1:4200/setup. Ports: Django
8001, Gateway 8002, Pi Service 8010. `.env.example` defaults to deterministic;
set ASSISTANT_PROVIDER=pi and configure a private service token for real Pi.
For host services use TOOL_BROKER_BASE_URL=http://127.0.0.1:8002. The container
hostname host.docker.internal is only appropriate for a container caller.

The Pi service loads `.env`, uses the locally installed Pi CLI/login, and reads
the local default model at startup when PI_MODEL is empty. Restart it after
changing model selection. A previously tested model is not an entitlement guarantee.

Previous verification (2026-10-16): 35 Django tests, 8 Gateway tests, 19 Angular
tests and production build passed. Real Pi clarification → Profile create and
real Instance create → Markdown/card/list-link were verified. These are historical
results; run current checks before claiming present behavior.

Rechecked 2026-11-25 before publishing: Django 35, Gateway 8, Angular 19 and Pi
document path-policy 4 tests all passed, along with Angular production build.
No live model request was made during this publication task.

## Constraints and remaining gaps

- Django authorizes every business API; browser route/tool metadata is not identity.
- Cookie stays in Gateway/Broker. Pi gets only run-scoped execution capability.
- The in-memory run store is single-process, not a production shared session store.
- Pi HTTP service is a host process wrapping CLI; it is not the document container.
- services/pi-docs remains a separate read-only document CLI sandbox, not integrated
  into the business chat. Keep its existing isolation controls.
- Traditional UI supports edit/delete; chat does not register these tools.
- There is no enforced multi-step workflow engine or exactly-once write guarantee.
- Current server-side parameter validation does not prove model arguments came
  from the user or a prior tool; stronger state/history is the next task.
- Do not import private source-project code or require access to unrelated repos.
- Legacy experiments remain reachable, but do not expand them into main navigation.

Personal local notes/preparation files are intentionally ignored. Shared status,
priorities and implementation guidance belong in this handoff, TODO.md and README.
