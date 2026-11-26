# Instructions for AI contributors

## Start here

Read `README.md`, `docs/AI_HANDOFF.md`, `TODO.md`, and
`docs/ASSISTANT_SSE_PROTOCOL.md` before changing the assistant flow. Inspect the
current code and `git status` rather than assuming services are running or the
working tree is clean. Update these documents when behavior or priorities change.

## Project intent

This is a small Django-to-Angular migration and agent demo. Keep the main UI to
chat plus four resource lists: Admin Profiles, Admin Users, Instances, Adapters.
The chatbot uses registered Pi tools to query/create real Django demo data.
The traditional resource pages support create/edit/delete. Adapters only save
configuration; do not add actual telecom integrations unless explicitly asked.

## Boundaries to preserve

- Django Session authentication, CSRF and Group-based FeaturePermission remain
  enforced for business APIs. Do not replace them with JWT or bypass them.
- Only Gateway/Broker handles Django cookies; never send them to Pi or the model.
- Broker authenticates run execution tokens, enforces the tool allowlist and
  Pydantic arguments, and maps to fixed Django URLs/methods. No generic HTTP tool.
- Pi chooses tools and reasons over results. Missing required information should
  use ask_user_question; do not invent values, select the last record by default,
  or use keyword routing as a substitute for the real Pi provider.
- UI success cards use successful tool_result.result.created_record, not model
  prose. Render assistant Markdown with HTML escaping and Angular sanitization.
- AdminUserRecord is demo business data, not a Django login account. AdminProfile
  does not grant auth Groups to the currently logged-in user.
- The business Pi service is `services/pi-agent` (local HTTP service + Pi CLI).
  `services/pi-docs` is a separate read-only document Docker sandbox.

## Next priority

Follow TODO.md: server-side conversation/tool history, multi-step failure tests,
then idempotent creates. These are planned work, not already implemented.
Keep request/run credentials separate from longer-lived conversation state.

## Work and verification

- Preserve existing unrelated changes. Never reset or overwrite the worktree.
- Do not commit `.env`, auth files, cookies, SQLite databases, dependency folders,
  local learning notes, private source-project extracts or personal prep notes.
- Do not access other local/private repositories as a required dependency.
- Do not change the user's Pi login or default model without a task requirement.
- Run relevant checks: `.venv/bin/python -m unittest assistant_gateway.tests`,
  `cd backend && ../.venv/bin/python manage.py test`, and
  `cd frontend && npm run build && npm test -- --watch=false --browsers=ChromeHeadless`.
- SDK/model calls need a live Pi login; report mocked tests separately from real
  model/API verification. Do not describe earlier tests as newly executed.
- Update TODO.md and docs/AI_HANDOFF.md when completing a meaningful step.
