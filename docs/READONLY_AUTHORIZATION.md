# Proving readonly tool calls cannot write

Verified 2026-11-25. Authorization is enforced by Django, not by the model's
decision to refuse a request. This does not add frontend page guards or change
the current policy that readonly users may chat and query setup data.

## Repeatable offline integration tests

```bash
.venv/bin/python backend/manage.py test demoapp.test_assistant_authorization
```

`backend/demoapp/test_assistant_authorization.py` uses the real Gateway HTTP
handler, Broker HTTP endpoint, run execution token, history client, Django API,
Session authentication, CSRF, Group authorization and temporary test database.
ASGI transports replace TCP only. The model's choice is scripted to force a
registered tool call regardless of the user's privilege; no 403 is mocked.

| Case | Required observations |
| --- | --- |
| readonly attempts each of four create tools | Each actual Django endpoint returns 403; all four business table counts unchanged |
| readonly queries setup | Real Django GET returns 200; successful tool result |
| readwrite attempts the same Profile create | Django returns 200; returned ID identifies the newly created row |
| readwrite downgraded to readonly after run starts | Same session/run cannot write; Django rechecks and returns 403 |

Denied cases also assert Django's permission metadata is `actual=readonly`,
`required=readwrite`, `feature_key=demo_setup`. This distinguishes permission
denial from an accidental CSRF 403. The readwrite positive control uses the
same login/CSRF/Broker path.

The agent receives `ok:false`, `error.code=django_forbidden`,
`error.status_code=403`. SSE carries the failed result with no success payload;
durable history records the same arguments/result and `status=failed`. Run
context is deleted after completion. These tests do not require a model key.

## Opt-in real Pi verification

Start Django on 8001, Gateway/Broker on 8002 and Pi Service on 8010 with
`ASSISTANT_PROVIDER=pi`, then run:

```bash
.venv/bin/python backend/manage.py verify_readonly_agent
```

The command creates a temporary non-superuser with only
`feature:demo_setup:readonly`, logs in through Django, checks readable setup,
then asks the real Pi to create a uniquely named Profile. It requires an actual
`create_admin_profile` tool start/result pair; a prose-only refusal does not pass.
It verifies the denied SSE result, failed durable Broker history and unchanged
counts in all four business tables. It never switches the configured model or
modifies an existing user's grants. URLs are fixed to loopback.

The temporary login identity/session/conversation is removed on exit; no
credentials or Cookie values are printed. No denied Profile should exist. If
verification fails because business data unexpectedly changed, inspect the DB;
the command does not delete arbitrary business records to hide the failure.
Run on a quiet local demo database: unrelated concurrent writes change the count
assertion. This command makes a real model request and is not part of CI tests.

Observed real Pi result (local selected model gpt-5.6-sol):

```text
PASS: readonly session GET setup -> 200
PASS: real Pi -> create_admin_profile -> Broker -> Django 403
PASS: SSE tool_result ok=false, django_forbidden, status_code=403
PASS: durable tool history status=failed; all four business table counts unchanged
Pi answer: Creation failed: Django denied the operation (403 Forbidden). No Admin Profile was created.
```

Verification request_id: `6fa8e4a0-ca6a-4998-b464-0a76aacae546`;
run_id: `063ea731-168a-4659-8713-ff0e796cfbf1`. Temporary history was cleaned up.
The real-model test exercised Profile creation; offline integration tests cover
all four creates and the mid-run permission downgrade. Do not describe this as a
live-model test of every possible tool or failure path.
