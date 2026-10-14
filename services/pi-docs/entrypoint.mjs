import { chmodSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { spawn } from "node:child_process";

const question = process.argv.slice(2).join(" ").trim();
const interactive = process.env.PI_INTERACTIVE === "1";

if (!interactive && !question) {
  console.error('Usage: docker compose run --rm pi-docs "your question"');
  process.exit(64);
}

const provider = process.env.PI_PROVIDER || "openai";
const model = process.env.PI_MODEL || "gpt-5-mini";
const apiKey = process.env.PI_API_KEY;
const policy = readFileSync("/app/policy.md", "utf8");

function decodeJwtPayload(token) {
  const parts = token.split(".");
  if (parts.length !== 3) throw new Error("The local Pi bearer token is not a JWT");
  return JSON.parse(Buffer.from(parts[1], "base64url").toString("utf8"));
}

function installEphemeralCodexCredential(token) {
  const payload = decodeJwtPayload(token);
  const expires = Number(payload.exp) * 1000;
  const accountId = payload["https://api.openai.com/auth"]?.chatgpt_account_id;

  if (!Number.isFinite(expires) || expires < Date.now() + 5 * 60 * 1000) {
    throw new Error("The local Pi bearer token expires too soon");
  }
  if (typeof accountId !== "string" || !accountId) {
    throw new Error("The local Pi bearer token has no ChatGPT account ID");
  }

  const agentDir = join(process.env.HOME || "/home/pi", ".pi", "agent");
  const authPath = join(agentDir, "auth.json");
  mkdirSync(agentDir, { recursive: true, mode: 0o700 });
  writeFileSync(authPath, JSON.stringify({
    "openai-codex": {
      type: "oauth",
      access: token,
      refresh: "",
      expires,
      accountId,
    },
  }), { mode: 0o600 });
  chmodSync(authPath, 0o600);
}

if (apiKey && provider === "openai-codex") {
  installEphemeralCodexCredential(apiKey);
}

const args = [
  "--no-session",
  "--no-builtin-tools",
  "--extension", "/app/extension/docs-tools.ts",
  "--tools", "docs_read,docs_grep,docs_find,docs_ls",
  "--no-skills",
  "--no-prompt-templates",
  "--no-context-files",
  "--no-approve",
  "--offline",
  "--provider", provider,
  "--model", model,
  "--system-prompt", policy,
];

if (!interactive) {
  args.unshift("--print");
}

if (apiKey && provider !== "openai-codex") {
  args.push("--api-key", apiKey);
}

if (question) {
  args.push(question);
}

// Do not pass the wrapper-only variable to descendants. Pi receives the
// short-lived token through its CLI option.
const childEnv = { ...process.env };
delete childEnv.PI_API_KEY;

const child = spawn("pi", args, {
  stdio: "inherit",
  env: childEnv,
});

child.on("error", (error) => {
  console.error(`Unable to start pi: ${error.message}`);
  process.exit(70);
});

child.on("exit", (code, signal) => {
  if (signal) {
    console.error(`pi terminated by ${signal}`);
    process.exit(70);
  }
  process.exit(code ?? 70);
});
