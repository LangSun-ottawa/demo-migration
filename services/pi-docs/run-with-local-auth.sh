#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if ! command -v pi >/dev/null 2>&1; then
  echo "Error: host pi command was not found." >&2
  exit 69
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed or not on PATH." >&2
  exit 69
fi

interactive=0
if [ "${1:-}" = "--interactive" ] || [ "${1:-}" = "-i" ]; then
  interactive=1
  shift
fi

if [ "$interactive" -eq 0 ] && [ "$#" -eq 0 ]; then
  echo "Usage:" >&2
  echo "  ./run-with-local-auth.sh \"your question\"" >&2
  echo "  ./run-with-local-auth.sh --interactive [optional opening question]" >&2
  exit 64
fi

provider="${PI_PROVIDER:-openai-codex}"
model="${PI_MODEL:-gpt-5.5}"

if [ "$provider" != "openai-codex" ]; then
  echo "Error: this wrapper currently supports the local openai-codex OAuth login only." >&2
  exit 64
fi

# The host Pi refreshes its OAuth login if needed and prints only a short-lived
# access token. Command substitution keeps it out of normal terminal output.
token="$(pi auth print-bearer-token \
  --provider "$provider" \
  --model "$model" \
  --min-expiry 2h)"

if [ -z "$token" ]; then
  echo "Error: host Pi returned an empty bearer token." >&2
  exit 77
fi

PI_API_KEY="$token" \
PI_PROVIDER="$provider" \
PI_MODEL="$model" \
PI_INTERACTIVE="$interactive" \
docker compose \
  --project-directory "$script_dir" \
  -f "$script_dir/compose.yaml" \
  run --rm \
  pi-docs "$@"

unset token
