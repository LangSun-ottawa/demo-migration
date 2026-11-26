# Demo flow and code reading guide

Updated 2026-11-26. Read this first, then follow the linked source files. Main UI:
http://127.0.0.1:4200/setup. There are only chat + four resource-list pages.

## 1. Authentication: two entrances, one Django Session

```text
Password form → POST /api/demo/auth/login → Django authenticate()/login()
SSO link → Django SAML login → Keycloak Docker → signed XML POST to Django ACS
                                              → validate → map identity/groups
                                              → Django login()
Both → sessionid cookie → /api/demo/auth/session → Angular access/status display
```

Read `backend/demoapp/saml.py` (start/acs/provision),
`backend/demoapp/api/views.py` (LoginView/SessionView/LogoutView),
`backend/demoapp/api/permissions.py` (FeaturePermission), and
`frontend/src/app/pages/setup-demo/setup-demo.component.ts` (loadSession/login).
[SAML.md](SAML.md) documents IdP configuration, endpoints and local test accounts.

SAML verifies signed assertions before trusting issuer + persistent NameID and
explicitly mapped groups. It never auto-links existing accounts by email.
`setup_access` in session responses is UI metadata, not an authorization token.
Readonly users see read-oriented chat examples and non-editable resource lists;
unknown grants show no-access state. API permission checks remain authoritative,
including requests forged outside Angular or after a permission change.
Logout currently ends the Django session only, not Keycloak Single Logout.

## 2. Chat/tool loop

```text
Angular sends question + conversation_id + page_state (no trusted tool history)
  → Gateway validates, generates request_id/run_id
  → Django checks owner/Group and restores durable messages + actual tool results
  → Gateway keeps user cookies only in temporary run state
  → Pi service receives history + allowed_tools + short-lived Broker token
     → model chooses a registered tool
        • ask_user_question → local structured question → user replies next turn
        • business/log tool → Broker checks token/allowlist/Pydantic arguments
                            → fixed Django endpoint + stored user cookies/CSRF
                            → Session/Group/serializer/ownership checks → SQLite
     ← real JSON result → Pi reasons and selects another tool or answers
  ← SSE meta/tool_start/tool_result/delta/error/done
Angular renders sanitized Markdown, real result cards and evidence timelines
```

Reading order:

1. `frontend/src/app/pages/setup-demo/setup-demo.component.ts`: send/handleEvent.
2. `frontend/src/app/services/setup-assistant.service.ts`: browser request + SSE.
3. `assistant_gateway/app.py`: stream_gateway_events and internal Broker endpoint.
4. `assistant_gateway/providers.py`: provider interface, real Pi adapter, mock.
5. `services/pi-agent/app.py` and `business-tools.ts`: model loop, schemas, execute.
6. `assistant_gateway/tools.py`: fixed API adapters, validation and allowlist.
7. `backend/demoapp/api/views.py`, `serializers.py`, `permissions.py`: final API.
8. `backend/demoapp/api/assistant_history.py`: owner-scoped trusted persistence.

Profile → returned profile_id → User; Instance → returned instance_id → Adapter.
The two chains are independent. A failed second create does not undo the first.
Cookies/tokens are not persisted in history or exposed to Pi. Conversation IDs,
turns, actual tool arguments/results and created business IDs are persisted.
Create operation IDs support scoped retries; see [IDEMPOTENT_CREATES.md](IDEMPOTENT_CREATES.md).
Refresh restores the latest owned chat. New chat does not delete previous history.
Stop cancels work, not previously committed writes. For event payloads read
[ASSISTANT_SSE_PROTOCOL.md](ASSISTANT_SSE_PROTOCOL.md).

## 3. Traditional lists and forms (no Pi involved)

Angular resource page → session metadata → GET protected setup snapshot → table.
Read/write users can submit create/edit/delete → Django directly → returned
snapshot replaces table data. Readonly users only view. Unauthorized/expired
sessions show login/permission guidance; loading/network failures are not shown
as a successful empty list. Refresh/Retry reloads session metadata and records.
Server authorization is repeated for every actual operation.

Read `frontend/src/app/pages/resource-list/resource-list.component.*` and
`frontend/src/app/services/setup-demo.service.ts`.
Business Admin Profiles/Users are **not** Django authentication users or grants.
Adapters save configuration; they do not open real connections.

## 4. Device-free log investigation

Read/write login → select fictional scenario or upload normalized JSONL → owned
LogDataset/LogDevice/LogEvent → switch chat to investigation → Pi queries schema,
bounded events, original records and correlations using six registered read tools.
Broker excludes create tools in investigation mode even for a readwrite user.
The UI uses real tool-result event IDs for UTC timelines and original evidence.
Changing the selected dataset clears the current conversation/draft so a prior
dataset's conclusion is not carried into the new chat. No auto-send or history deletion.

Samples: normal observations, policy block, insufficient evidence. Evidence and
uncertainty matter; absence of logs is not proof of success or failure. These are
fictional normalized fixtures, not Fortinet device integration or malicious replay.
See [LOG_INVESTIGATION.md](LOG_INVESTIGATION.md) and
[LOG_SCENARIO_EVALUATION.md](LOG_SCENARIO_EVALUATION.md).

## Demonstration sequence

1. Password login or SSO writer; ask to create a Profile and User with incomplete
   information; answer Pi's question and inspect returned cards/IDs in the lists.
2. Refresh chat and use the actual earlier Profile ID in a later request.
3. Sign in as SSO reader; verify list mutation controls are absent. Backend
   denial is independently proven by tests, not the absence of a button.
4. Writer loads a fictional incident, asks what happened and inspects original
   evidence. Repeat with insufficient evidence and observe clarification.

## Real versus mock; deferred scope

- Real: Django Session/Group/CSRF/ORM, SAML/Keycloak, Broker, persistence, CRUD,
  JSONL import/query, SSE and UI rendering.
- Real Pi provider: local Pi CLI + selected authenticated model. No new model
  invocation is implied by unit tests or health responses.
- Deterministic provider: explicitly a no-key reasoning mock, still uses real APIs.
- Offline tests may script model tool selection; they do not prove model reasoning.
- PW/vulnerability tools are not imported, registered or executed. Later use a
  typed adapter with approved target scope, execution isolation, timeout, progress
  and controlled results; never expose a generic shell command tool.
- `services/pi-docs` stays a separate read-only document Docker sandbox.
- This is local-demo configuration, not production deployment. Remaining work
  is explicit in [TODO.md](../TODO.md).
