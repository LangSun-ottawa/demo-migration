# Recoverable creates

All four create APIs support `Idempotency-Key: <UUID>`. Django checks Session,
CSRF and current readwrite permission BEFORE looking up or replaying an operation.
`CreateOperation` is unique on (owner, key), binds the resource/request-body hash,
and stores the original successful result in the same transaction as the create.

- Same user/key/body after success: original created_record ID, plus
  `operation_replayed=true`. No second business row.
- Same key with different body/resource: controlled 409, no mutation.
- Validation failure: no operation reserved; correct the fields and retry.
- Lost response after commit: retry the same logical key, even in a new run.
- Concurrent contenders: one committed create, others replay or receive a
  retryable 409 under contention. SQLite uses IMMEDIATE transactions; Broker
  serializes parallel tool calls within each temporary run.
- Replays are historical outcomes, not fresh snapshots or permission bypasses.
  If a record was subsequently edited/deleted, query current state.

Broker adds `operation_id` to validated create arguments before executing and
records it in tool history. If omitted, it derives a stable UUID from conversation
ID + tool + canonical business arguments. This survives new run IDs for retries
inside the same conversation. Pi may reuse a returned operation_id for an exact
retry; corrected arguments must omit the old ID. IDs are never user-required data.

This fallback intentionally treats identical arguments in the same conversation
as the same operation. A genuinely new intent after deletion needs a new operation
ID/new conversation; different conversations are not automatically deduplicated.
Global unique business names still reject duplicates without idempotency.

Traditional CRUD forms generate one key per unchanged pending create, retain it
after a transport error and regenerate after edits/reset/success. Pending form
keys are memory-only, not restored across a full page reload. Direct API callers
must retain/send their own key; calls without it preserve legacy validation.
Operation results persist until the owning login user is removed; production
retention/redaction policy remains deployment work.

Verification:

```bash
.venv/bin/python backend/manage.py test demoapp.test_idempotency demoapp.test_assistant_authorization demoapp.test_setup_demo
```

Tests cover exact replay, conflicting arguments, per-user key isolation, fresh
authorization, failed validation, concurrent retries, partial Profile/User and
Instance/Adapter recovery. The integration test injects an HTTP response loss
AFTER the real Django create has committed, then starts another Gateway run in
the same conversation and gets the original ID without duplication. Only the
agent's tool selection/transport fault are scripted; the database commit, Broker,
Session/CSRF and idempotency implementation are real. This is not an assertion
that arbitrary external APIs have exactly-once semantics.
