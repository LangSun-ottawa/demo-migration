# Project TODO

Last reviewed: 2026-11-26. See [AI handoff](docs/AI_HANDOFF.md) for current behavior
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

## P0 — durable multi-turn context (implemented)

- [x] Design a server-side conversation ID and storage schema, owned by a Django
  user, with an explicit retention policy. Prevent cross-user access and clear
  the browser's local history on account changes.
- [x] Store user/assistant messages and actual tool calls/results, including
  call_id and execution status. Do not treat an assistant's summary as proof of a write.
- [x] Resume conversations using trusted server history instead of relying only
  on the browser's recent plain-text messages. Bound context size.
- [x] Keep per-request run_id and execution tokens temporary; do not persist
  cookies/provider credentials in conversation records.
- [x] Verify reload/resume, user isolation, context trimming and expired sessions.

Acceptance: create a Profile, return in a later turn, then create a User using
the actual returned profile_id without guessing or duplicate creation.

Verified 2026-11-25 with real local Pi + Django: clarification → Profile ID 7 →
reload via authenticated history API → later User ID 3 linked to Profile 7, with
exactly one new Profile. Automated checks: Django 41, Gateway 12, Angular 21.
See docs/CONVERSATIONS.md for storage, retention and limits.

## P1 — business chains and failure recovery

- [x] Readonly authorization proof: four forced create calls denied by real Django,
  database unchanged; read allowed, readwrite positive control, mid-run downgrade
  denied. Real Pi Profile-create denial also verified. See
  [readonly verification](docs/READONLY_AUTHORIZATION.md).
- [x] API regression coverage: Profile → User and Instance → Adapter partial
  failures; corrected retries retain the successful dependency's actual ID.
- [x] Nonexistent related IDs, invalid email, duplicate-name/key behavior and
  controlled 401/403/business/upstream failure results.
- [x] Pi instructions preserve partial success; cancellation cleanup test and
  visible Stop button warn that already-committed writes are not rolled back.
- [ ] Expand real-model evaluations for ambiguity, user corrections, changing the
  requested resource, and editing a created record versus an unsubmitted draft.
  There is no enforced workflow/draft state machine yet.

## P2 — idempotent writes

- [x] Define operation/idempotency keys for each logical create, separate from
  transient request_id/run_id; enforce uniqueness and persist outcomes in Django.
- [x] Retrying a completed operation returns its original record; reusing a key
  with different arguments returns a controlled conflict.
- [x] Test injected response loss after a real Django commit, repeated calls and
  concurrent retries. See docs/IDEMPOTENT_CREATES.md for scope/limits.

## P3 — device-free log investigation demo

- [x] Fictional device inventory and six-event policy-change incident, including
  unrelated traffic/threat distractors; no real devices or traffic replay.
- [x] Atomic normalized JSONL import; owner-isolated datasets, bounded real queries
  and original evidence lookup. No generic SQL/HTTP execution.
- [x] Schema/field semantics + six Pi log tools, with investigation-mode read-only
  allowlist enforced by Broker even for a readwrite login.
- [x] Existing chat page supports sample loading/upload, mode selection, UTC
  evidence timeline, source viewer and refresh restore. No extra nav pages.
- [x] Real Pi evidence collection/Chinese explanation verified; independent fixture
  oracle and regression tests. See docs/LOG_INVESTIGATION.md.
- [x] Add normal/block/insufficient sample selection, neutral shared question,
  explicit failure-window handling and fresh chat on dataset switch. Add
  independent fixture/checker tests plus opt-in real Pi three-case verification
  (docs/LOG_SCENARIO_EVALUATION.md); semantic correctness still needs human review.
- [ ] Later: real vendor-format adapters, evidence evaluation suite, dataset
  deletion/retention UI, quotas and approved handling for real sensitive logs.

## Later — only when needed

- [x] Demo polish: session/access badges, conditional SSO entry, readonly resource
  controls and chat examples, list loading/error/retry/login states, required-field
  validation, mutation in-flight guards and fresh chat on dataset selection.
- [x] Document full login/CRUD/agent/log flow and reading order in docs/DEMO_FLOW.md.

- [x] Optional real Keycloak Docker SAML login alongside password login; persistent
  issuer/NameID mapping, signed-response validation, replay guard and explicit
  readonly/readwrite Group mapping. See docs/SAML.md for verification and limits.
- [ ] SAML deployment only if needed: HTTPS/cookies, SP signing, certificate
  rotation, IdP revocation propagation/session lifetime and Single Logout.
- [ ] PW/vulnerability tool integrations deferred explicitly: extract former
  internal tools first; do not import or execute them as part of SAML work.

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
