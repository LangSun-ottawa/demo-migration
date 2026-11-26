# Server-owned assistant conversations

Implemented for `/new/setup`; the older VM demo is unchanged.

```text
Browser: question + conversation_id (or null)
  → Gateway: authenticated history start → Django user-owned conversation/turn
  → Pi: bounded prior turns + actual tool arguments/results, no Cookie
  → Broker: record started(call_id,args) → real Django business API
                                      → record finished(actual ToolResult)
  → Pi continues reasoning → SSE → Angular
  → Gateway: save assistant text/status, release lease, delete temporary run Cookie
Refresh → authenticated Django latest history → messages + created-record cards
```

## Reading order

1. `backend/demoapp/models.py`, migration `0005_assistant_conversations.py`:
   Conversation (UUID/owner/expiry), Turn (request/run ID, messages/status),
   ToolCall (call_id, name, arguments, actual result/status).
2. `backend/demoapp/api/assistant_history.py`: ownership, service credential,
   concurrency lease, append and restore; Django Session/CSRF/FeaturePermission
   still apply. Even a superuser cannot read another owner's conversation here.
3. `assistant_gateway/conversations.py`, `app.py`: load trusted history before Pi,
   save local clarification calls and final text/status. Browser conversation
   prose cannot replace these records. A 401/403/404 fails before launching Pi.
4. `assistant_gateway/tools.py`: persist a call before business execution, then
   persist the actual Django ToolResult before returning to Pi. A history-start
   failure prevents the business call. Invalid/unallowlisted arguments are
   rejected before execution and are not recorded as executed tools.
5. `services/pi-agent/business-tools.ts`: forward Pi call ID; `app.py`: structured
   history in prompt. A new temporary Pi process still starts per turn: this is
   durable application context, not resuming a native Pi session file.
6. `frontend/src/app/services/setup-assistant.service.ts` and
   `pages/setup-demo/setup-demo.component.ts`: send only ID/new message, restore
   latest server history/cards, New chat, clear old sessionStorage cache and
   recheck account on window focus. Server ownership always enforces isolation.

## HTTP endpoints

All routes start with `/api/demo/secure/assistant/` and return the FDC JSON envelope.

| Method/path | Caller / purpose |
| --- | --- |
| GET conversations/latest | browser: newest nonexpired conversation for current user |
| GET conversations/{conversation_id} | browser: owner-only bounded detail |
| POST internal/turns | Gateway: claim lease, create turn, return conversation_id/history |
| POST internal/turns/{run_id}/tools | Broker/Gateway: started or finished call |
| POST internal/turns/{run_id}/finish | Gateway: save text/status and release lease |

Internal writes require `X-Assistant-History-Token` in addition to the user's
Session cookie, CSRF token and readonly setup permission. Only business APIs
enforce readwrite for actual creates, independently on every request. Configure
`ASSISTANT_HISTORY_TOKEN` identically in Django/Gateway; the checked-in default is
local-demo-only and Django refuses it with DEBUG=false. Pi subprocesses do not
inherit it. No Cookie, execution token, model key or raw headers enter history
fields through these application paths. Do not put secrets in chat messages.

## Bounds, expiry and concurrency

- Retention: 30 days from conversation creation; not sliding. Expired history is
  immediately unreadable. `manage.py purge_assistant_history` physically deletes
  expired conversations and cascading turns/tools; schedule this for deployment.
- Prompt and restored UI: latest 10 whole turns, at most 64,000 JSON characters;
  text at most 8,000 per turn. Successful creates retain exact `created_record`
  rather than the full snapshot; query responses above 8,000 characters use an
  explicit truncation marker. Older records remain in storage until expiry.
  Query current business state when context is missing or outdated.
- At most 32 tool calls per turn; tool append body at most 200,000 serialized
  characters. Gateway stores at most 12,000 final response characters.
- A 3-minute lease rejects concurrent turns with 409. Default run timeout is
  60 seconds. Keep timeout below lease duration. After crash/lease expiry, next
  start marks abandoned turns interrupted; unfinished calls are not successes.
- Duplicate `(turn, call_id)` starts/results are rejected. Logical creates now
  also have separate operation IDs; see IDEMPOTENT_CREATES.md for cross-run scope.
- History failure after a Django write can leave a running/unknown call even if
  the business record committed. Query state before retry. Scoped idempotency now
  addresses this ambiguity: retrying the same operation ID/arguments can
  recover the committed result without a second create. No automatic rollback or
  general external-system exactly-once guarantee is claimed.
- Cancellation saves final text/status on a best-effort basis. Lease expiry is
  the fallback after process death, not a distributed cancellation mechanism.

## Verification

Automated Django tests cover owner isolation, service credential, CSRF, expired
sessions/history, call/result immutability, leases, context compaction and purge.
Gateway tests cover trusted history replacing forged browser prose, credential
separation, Broker persistence and cleanup after provider failure. Angular tests
cover server restore/cards, New chat and existing composer behavior.

Real local Pi verification on 2026-11-25: missing fields → ask_user_question →
create Profile → reload history API → next turn create User with returned
profile_id, no duplicate Profile. This was real model reasoning and real Django
data, not deterministic routing. Full business failure-recovery scenarios and
broader recovery evaluations remain TODO. Scoped logical-write idempotency is now
implemented; see IDEMPOTENT_CREATES.md. Logs use the same durable tool-history path.
