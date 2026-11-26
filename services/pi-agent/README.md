# Local Pi Agent Service

This HTTP/SSE service uses the locally installed Pi 0.83 CLI and its existing OAuth configuration.
It registers five setup tools and forwards their calls to the fixed FastAPI Tool Broker.
The local `ask_user_question` tool emits a structured question and ends the turn until
the user replies. It has no Django access. Create tools declare their required fields;
Pi asks for missing values before attempting a write. The Gateway Broker and Django
both validate the business arguments.
It never receives the Django session cookie.

The configured model must be enabled for the local Pi account. If Pi rejects the model, keep
`ASSISTANT_PROVIDER=deterministic` so the full broker/Django demo remains runnable.

```bash
.venv/bin/uvicorn --app-dir services/pi-agent app:app --port 8010
```

Run from repository root after configuring PI_AGENT_SERVICE_TOKEN in the ignored
root `.env`; Gateway and this service must use the same locally chosen secret.
Install extension dependencies with `npm --prefix services/pi-agent ci`.

For local development the repository starts the module by file path because the directory name contains a dash.
The existing `services/pi-docs` container remains a separate read-only documentation sandbox.

The service reads the repository `.env`. With `PI_MODEL` empty it follows `defaultModel`
in `~/.pi/agent/settings.json` at startup. Restart the service after changing that model.
