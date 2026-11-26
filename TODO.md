# Project TODO

Last reviewed: 2026-11-25. See [AI handoff](docs/AI_HANDOFF.md) for current behavior
and [SSE contract](docs/ASSISTANT_SSE_PROTOCOL.md) for transport definitions.

## Completed baseline

- [x] Django Session login, CSRF, Group-based read/readwrite authorization.
- [x] Four Django resource models and traditional list/create/edit/delete pages.
- [x] Gateway request_id/run_id, TTL run store, execution token, timeout and cleanup.
- [x] Broker tool allowlist, Pydantic arguments and fixed Django API adapters.
- [x] Independent local Pi HTTP/SSE service with a Pi CLI agent loop.
- [x] Six Pi setup tools: ask_user_question, query_setup_state, four create tools.
- [x] No-model-key deterministic provider retained for development/tests.
- [x] SSE progress/text/errors, Markdown rendering, authoritative created-record cards.
- [x] Enter sends; Shift+Enter adds a line; IME confirmation does not send; input clears.
- [x] Keep the separate pi-docs container and its read-only document tools intact.

## P0 — durable multi-turn context (next task)

- [ ] Design a server-side conversation ID and storage schema, owned by a Django
  user, with an explicit retention policy. Prevent cross-user access and clear
  the browser's local history on account changes.
- [ ] Store user/assistant messages and actual tool calls/results, including
  call_id and execution status. Do not treat an assistant's summary as proof of a write.
- [ ] Resume conversations using trusted server history instead of relying only
  on the browser's recent plain-text messages. Bound context size.
- [ ] Keep per-request run_id and execution tokens temporary; do not persist
  cookies/provider credentials in conversation records.
- [ ] Verify reload/resume, user isolation, context trimming and expired sessions.

Acceptance: create a Profile, return in a later turn, then create a User using
the actual returned profile_id without guessing or duplicate creation.

## P1 — business chains and failure recovery

- [ ] Exercise Profile → User and Instance → Adapter with missing fields and
  user corrections. Query and disambiguate existing related records.
- [ ] Test duplicate names, nonexistent related IDs, invalid email, 401/403 and
  failed upstream calls. A failed dependency must not be assumed successful.
- [ ] Explain partial success: a created Profile must remain visible if User
  creation fails, and retries should resume the failed step.
- [ ] Test cancellation, changing the requested resource, and modifying an
  already-created record versus a still-unsubmitted draft.

## P2 — idempotent writes

- [ ] Define operation/idempotency keys for each logical create, separate from
  transient request_id/run_id; enforce uniqueness and persist outcomes in Django.
- [ ] Retrying a completed operation returns its original record; reusing a key
  with different arguments returns a controlled conflict.
- [ ] Test network disconnect after commit, repeated sends and concurrent retries.

## Later — only when needed

- [ ] Register chat edit/delete tools if requested; currently available only in UI.
- [ ] Add request_confirmation / update_draft when there is actual confirmation
  or draft state, with execution-side checks rather than prompt-only enforcement.
- [ ] Split shared frontend SSE types/parser out of the VM-context service.
- [ ] Refresh generated OpenAPI to include setup CRUD endpoints and response shapes.
- [ ] Reconcile the older VM assistant with Pi (query_vm_context is not registered
  in the current business Pi extension; its deterministic path remains available).
- [ ] For deployment: shared bounded TTL storage, limits/quotas, durable audit,
  service supervision, independent model identity, private Broker networking and
  robust disconnect/process cancellation. Current setup is a local demo.

## Non-goals

No PW520/ZAP integration, real adapter communication, Kubernetes, complex queues,
or extra business pages until the main conversation workflow is stable.
