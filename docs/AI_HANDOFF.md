# AI handoff: current implementation

Reviewed 2026-11-26. This is the entry document for an AI or developer continuing
the repository. Read AGENTS.md and TODO.md; inspect actual configuration locally.
Do not infer that a configured service is currently running.

## Product and scope

For a compact full flow and file-by-file reading order, start with
[DEMO_FLOW.md](DEMO_FLOW.md): password/SAML login, direct CRUD, Pi/Broker loop,
history/idempotency and device-free evidence investigation.

A migration demo with Angular presentation, Django Session-authenticated APIs,
and a Pi chatbot that creates four kinds of demo business records. Users verify
results via traditional resource lists. Keep this small and understandable.

AdminProfile → AdminUserRecord.profile; ManagedInstance → AdapterConfig.instance.
These are two independent chains. AdminUserRecord is not django.contrib.auth.User;
AdminProfile.access_level is business metadata, not the login user's auth grant.
Adapters save configuration and never establish a real connection.

## Request flow and reading order

```text
Angular send(question, conversation_id, page_state)
  -> Gateway POST /assistant/stream
     -> validate request; create request_id/run_id
     -> Django: authorize owner; start durable conversation turn; load tool history
     -> store Django session/CSRF cookie temporarily; create execution token
     -> PiAgentServiceAdapter POST /v1/agent/stream
        -> local Pi CLI + extension + allowlist + conversation prompt
        -> model chooses registered tools
           -> ask_user_question: local structured question, end this turn
           -> business tool: Broker POST /internal/agent-runs/{run_id}/tools/{name}
              -> token/TTL/allowlist/argument checks
              -> fixed Django API with stored cookie and CSRF token
              -> durable tool start/result (same call_id as Pi/SSE)
              -> SessionAuthentication + FeaturePermission + DRF serializer
              -> ORM write/query -> JSON ToolResult -> Pi continues reasoning
        -> Pi JSONL events adapted to SSE
     -> persist assistant text/status; Gateway meta/done, timeout, run cleanup
  -> Angular text/progress/error + Markdown + created-record cards
```

| File | Responsibility |
| --- | --- |
| frontend/src/app/pages/setup-demo/setup-demo.component.ts | send, server history restore, events, cards |
| frontend/src/app/services/setup-assistant.service.ts | browser fetch/SSE |
| frontend/src/app/services/context-assistant.service.ts | shared event union/parser, older VM feature |
| assistant_gateway/app.py | Gateway, Pi selection, internal Broker route, lifecycle |
| assistant_gateway/protocol.py | request, tool and SSE payload models |
| assistant_gateway/providers.py | async provider interface, Pi adapter, deterministic mock |
| assistant_gateway/run_store.py | process-local run TTL, hashed execution token, cookie lifecycle |
| assistant_gateway/conversations.py | authenticated Gateway-only Django history client |
| backend/demoapp/api/assistant_history.py | owner-scoped durable history, lease, append/restore |
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
the turn; the next reply starts a new run with bounded server-owned user/assistant
messages and actual tool calls/results. Django owns Conversation/Turn/ToolCall;
browser submits only the ID and new question. Refresh restores latest owned
conversation/cards, New chat starts independently. Old sessionStorage cache is
removed. History expires after 30 days; use the purge command for physical cleanup.
See [CONVERSATIONS.md](CONVERSATIONS.md). Idempotent creates are now implemented
within the scope described in [IDEMPOTENT_CREATES.md](IDEMPOTENT_CREATES.md).

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

P0 follow-up verification (2026-11-25): Django 41, Gateway 12, Angular 21 and
production build passed. Real Pi (local selected gpt-5.6-sol) clarification →
Profile creation → authenticated history reload → later User creation using the
returned Profile ID passed; one Profile, no duplicate. Test records were left in
local DB: P0 Resume 929fb05a (Profile 7), p0_resume_929fb05a (User 3).

Readonly follow-up (2026-11-25): Django 45 tests and Gateway 12 passed. New
`demoapp.test_assistant_authorization` has four integration tests using real
Gateway/Broker/Django with a scripted model choice (not a fake permission
response): all four creates denied for readonly with zero new rows, read allowed,
readwrite create succeeds, and mid-run downgrade blocks writing. The opt-in
`manage.py verify_readonly_agent` also passed with real Pi: Profile create tool
attempt → Django 403 → failed SSE/history → accurate model refusal, no new rows.
Temporary account/session/history cleaned up; existing users/grants preserved.
See [READONLY_AUTHORIZATION.md](READONLY_AUTHORIZATION.md) for commands and evidence.
No frontend permission/route behavior was changed in this verification task.

Subsequent stability/log slice (2026-11-25): migration 0006 adds CreateOperation,
LogDataset, LogDevice and LogEvent. All creates support user-scoped operation
keys; Broker derives stable same-conversation keys and persists them in actual
tool arguments. Commit/result are atomic in Django; replays still reauthorize.
Tests inject a lost HTTP response after a real commit and recover the same ID in
a new run. Concurrent retries cannot add duplicate rows. Partial-failure API
tests retain the successful Profile/Instance when User/Adapter validation fails.
Stop cancels the run with a no-rollback warning; there is no workflow/draft engine.

Six new read tools: get_log_schema, list_log_datasets, find_device,
query_log_events, get_event_details, get_related_events. SetupPageState includes
mode=setup|investigation and optional log_dataset_id. Investigation grants only
those six tools plus ask_user_question; Broker rejects attempted creates before
Django. Logs are owner-isolated under the existing setup feature permission.
Uploads are normalized UTF-8 JSONL only; sample telemetry is explicitly fictional.
The existing /setup page adds a collapsed log source panel, mode switch and
structured evidence timelines/source viewer. No extra navigation pages.

Real Pi investigation passed with seven successful tools (schema/list/events +
four raw lookups), Chinese evidence-linked chronology and no business mutation.
Run 65478093-0658-4538-88d5-d22ed99e2a16. Browser restore/timeline/source #3 were
verified. A first trial exposed parallel SQLite audit-write contention; Broker
now serializes tools within each run and SQLite uses IMMEDIATE transactions;
the clean rerun had no failed tool calls. Real readonly refusal was reverified
after the new tools were added. See LOG_INVESTIGATION.md and IDEMPOTENT_CREATES.md.
Final checks for this slice: Django 61, Gateway 18, Angular 23 and independent
pi-docs path tests 4 passed; production build and migration drift check passed.
These counts are newly executed, separate from the historical results above.

Three-scenario evaluation follow-up (2026-11-25): sample loader now accepts
scenario=normal|policy_block|insufficient (default policy_block, compatible with
empty-body callers). New raw fixtures are observation-only; independent expected
interpretations live in log_evaluation.py and are never sent to Pi. UI has a
small sample selector and starts a fresh chat when loading a different dataset.
All cases use the same neutral question/explicit 14:00–14:10 UTC target window.
Pi guidance honors explicit windows, prevents carrying evidence across datasets,
avoids false block/infection conclusions and uses ask_user_question for missing
evidence. No new tools or navigation pages were added.

Opt-in command: manage.py verify_log_scenarios. Fresh temporary datasets, readonly
model identity, separate conversations; checks actual durable Broker outcomes,
grounded citations, raw evidence, selected window, structured clarification and
unchanged business data. All three final real Pi cases passed and their answers
were reviewed against the independent oracle (LOG_SCENARIO_EVALUATION.md). It is
not a semantic auto-grader or accuracy guarantee. Temporary records cleaned up.
Latest checks: Django 70, Gateway 18, Angular 24 and production build passed.

## Constraints and remaining gaps

SAML follow-up (2026-11-26): optional Keycloak 26.8.2 Docker on loopback 8080,
real signed SP-initiated login in backend/demoapp/saml.py. Migration 0007 adds
SamlIdentity (issuer/persistent NameID → separate Django login user, never email
auto-link) and database SamlReplay assertion guard. Trusted IdP groups map only
to existing demo_setup readonly/readwrite; unknown groups grant nothing. Group
sync occurs at SAML login, not continuous IdP push. Existing Django Session,
password login, CSRF/business permissions and Gateway/Broker/Pi are unchanged.
Setup adds SSO link and local logout. Logout is NOT SAML Single Logout. See
SAML.md for fixed endpoints, ignored certificate metadata, test accounts, startup,
real verification command and production gaps. PW/vulnerability extraction is
explicitly deferred. Do not reset Docker volumes or change Pi auth/model.

New verification: Django 77, Gateway 18, Angular 25 tests and production build
passed; migration drift and whitespace checks passed. Real local Keycloak signed
login → Django read API passed for both SSO accounts; reader create denied 403,
writer create succeeded and verification record deleted; replay and signed-group
tampering rejected. Existing password login passed. Chrome SSO returned to
Angular /setup authenticated with no previous local user's conversation. No new
Pi/model invocation was needed or performed for this auth integration.

Demo polish/publication follow-up (2026-11-26): session API adds setup_access and
saml_enabled UI hints without changing authorization. Chat displays actual access,
hides disabled SSO, uses read-oriented examples for readonly and clears chat/draft
when selecting another dataset. Resource lists use session-aware readonly/no-access
states, loading/retry/refresh/login guidance, required-field checks and in-flight
mutation guards; lost-response create keys remain stable. New tests cover rendered
readonly/loading/error states and guards, operation retry, account expiry, dataset
selection and session grant changes. Browser writer session/list checked; new real
Keycloak reader/writer/replay/tamper HTTP verification passed. Newly rerun Django
78, Gateway 18, Angular 34 and pi-docs 4 tests passed, with production build,
migration drift and whitespace checks. No new live Pi reasoning run in this task.
All previously implemented uncommitted demo history/idempotency/log/SAML source
is included in the publication; ignored secrets/SQLite/personal notes are not.

- Django authorizes every business API; browser route/tool metadata is not identity.
- Cookie stays in Gateway/Broker. Pi gets only run-scoped execution capability.
- The in-memory run store is single-process, not a production shared session store.
- Pi HTTP service is a host process wrapping CLI; it is not the document container.
- services/pi-docs remains a separate read-only document CLI sandbox, not integrated
  into the business chat. Keep its existing isolation controls.
- Traditional UI supports edit/delete; chat does not register these tools.
- There is no enforced workflow engine or general exactly-once external API guarantee.
  Django creates have scoped idempotency; different conversations are not
  automatically the same operation, and legacy clients without keys are unchanged.
- Trusted stored tool results now ground cross-turn references, but parameter
  validation still does not prove every model argument came from the user.
- History append needs ASSISTANT_HISTORY_TOKEN (Django/Gateway only), in addition
  to user Session/CSRF. Its default is local-demo-only; rotate for deployment.
- Next tasks: broader real-model failure/recovery evaluations, log retention and
  real-format parser adapters only when needed (TODO.md).
- Do not import private source-project code or require access to unrelated repos.
- Legacy experiments remain reachable, but do not expand them into main navigation.

Personal local notes/preparation files are intentionally ignored. Shared status,
priorities and implementation guidance belong in this handoff, TODO.md and README.
