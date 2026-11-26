# Assistant SSE protocol

The Angular client POSTs `{question, conversation, page_state}` to Gateway
`/assistant/stream` and reads an SSE response. Every `data:` body is JSON.

Source definitions:

- `assistant_gateway/protocol.py`: agent request, Broker ToolResult and public ToolResultEventData.
- `frontend/src/app/services/context-assistant.service.ts`: AssistantStreamEvent union and SSE parser shared by the two chat clients.
- `services/pi-agent/app.py`: Pi events → public SSE payloads.
- `assistant_gateway/app.py`: Gateway owns meta, done and run lifecycle.

## Event types

| Event | Producer | Payload |
| --- | --- | --- |
| meta | Gateway | request_id, run_id, provider |
| tool_start | Agent | call_id, name |
| tool_result | Agent | call_id, name, ok, summary; optional result, error, question, missing_fields |
| delta | Agent | text (natural language, possibly Markdown) |
| error | Agent/Gateway | code, message |
| done | Gateway | request_id, run_id, status |

`call_id` correlates a tool_start with its tool_result. `done` ends a request/run;
an ask_user_question result ends this turn and the user's answer starts a new run
with conversation history. A failed business call is represented by `ok:false`
and an error object; the Agent can reason about it and ask for corrected input.

## Structured business result

```text
event: tool_result
data: {"call_id":"call-1","name":"create_admin_profile","ok":true,"summary":"Django API completed the operation","result":{"profiles":[{"id":6,"name":"test_profile","access_level":"readonly"}],"users":[],"instances":[],"adapters":[],"created_record":{"resource":"profiles","record":{"id":6,"name":"test_profile","access_level":"readonly"}}}}

```

`result` is the real Broker/Django result, not extracted from the model's prose.
Create APIs return the existing full setup snapshot plus `created_record`, which
identifies this exact write. Its resource is profiles/users/instances/adapters;
record contains the Django record's ID, name/username and relevant business fields.
The frontend renders a success card only for an ok tool_result with a matching
tool/resource and a valid created_record. It never selects the last snapshot item.

## Clarification

```text
event: tool_result
data: {"call_id":"call-2","name":"ask_user_question","ok":true,"summary":"Waiting for your reply","question":"What name and access level should the profile use?","missing_fields":["name","access_level"]}

```

The service also emits the question as a delta so existing text-only clients keep
working. A future question-card renderer should avoid showing both copies.

All new fields are optional for backward compatibility. Clients can continue to
show summary while adopting typed result cards. Current setup chat renders created
record cards and sanitized Markdown for assistant text; user text stays plain text.
Never include cookies, credentials, execution tokens or raw request headers in SSE.
