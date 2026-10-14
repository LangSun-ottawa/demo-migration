import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { readdir } from "node:fs/promises";
import { createDocsAccess, truncateUtf8 } from "./path-policy.mjs";

const rootPath = process.env.DOCS_ROOT || "/docs";
const accessPromise = createDocsAccess(rootPath);

function ok(text: string, details: Record<string, unknown> = {}) {
  return { content: [{ type: "text" as const, text }], details };
}

function failed(error: unknown) {
  const message = error instanceof Error ? error.message : "Unknown error";
  return ok(`Error: ${message}`, { error: true });
}

export default function docsTools(pi: ExtensionAPI) {
  // Pi's TUI has a user-entered `!` shell path independent of the model's
  // active tools. Intercept it so interactive users cannot inspect the
  // container or the ephemeral OAuth credential.
  pi.on("user_bash", () => ({
    result: {
      output: "Shell commands are disabled in documentation mode.",
      exitCode: 126,
      cancelled: false,
      truncated: false,
    },
  }));

  pi.registerTool({
    name: "docs_read",
    label: "Read documentation",
    description: "Read a UTF-8 text file below the read-only documentation root.",
    parameters: Type.Object({
      path: Type.String({ description: "Path relative to the documentation root" }),
      offset: Type.Optional(Type.Number({ minimum: 1, description: "First line, starting at 1" })),
      limit: Type.Optional(Type.Number({ minimum: 1, maximum: 1000, description: "Maximum lines" })),
    }),
    async execute(_id, params) {
      try {
        const docs = await accessPromise;
        const path = await docs.safePath(params.path);
        const content = await docs.readTextFile(path);
        const lines = content.split("\n");
        const start = Math.max(0, (params.offset ?? 1) - 1);
        const selected = lines.slice(start, start + (params.limit ?? 300));
        const text = selected.map((line, i) => `${start + i + 1}: ${line}`).join("\n");
        return ok(truncateUtf8(text), { path: docs.displayPath(path), totalLines: lines.length });
      } catch (error) {
        return failed(error);
      }
    },
  });

  pi.registerTool({
    name: "docs_ls",
    label: "List documentation",
    description: "List a directory below the documentation root without following symlinks.",
    parameters: Type.Object({
      path: Type.Optional(Type.String({ description: "Directory relative to documentation root" })),
    }),
    async execute(_id, params) {
      try {
        const docs = await accessPromise;
        const path = await docs.safePath(params.path ?? ".");
        const entries = await readdir(path, { withFileTypes: true });
        const names = entries
          .filter((entry) => !entry.isSymbolicLink())
          .slice(0, docs.limits.maxResults)
          .map((entry) => `${entry.name}${entry.isDirectory() ? "/" : ""}`);
        return ok(names.join("\n") || "Directory is empty", { count: names.length });
      } catch (error) {
        return failed(error);
      }
    },
  });

  pi.registerTool({
    name: "docs_find",
    label: "Find documentation",
    description: "Find files by a case-insensitive literal filename substring below the documentation root.",
    parameters: Type.Object({
      query: Type.String({ minLength: 1, maxLength: 200, description: "Literal filename substring" }),
      path: Type.Optional(Type.String({ description: "Starting path below the documentation root" })),
    }),
    async execute(_id, params) {
      try {
        const docs = await accessPromise;
        const start = await docs.safePath(params.path ?? ".");
        const query = params.query.toLowerCase();
        const matches: string[] = [];
        await docs.walk(start, async (path) => {
          const name = docs.displayPath(path);
          if (name.toLowerCase().includes(query)) matches.push(name);
          return matches.length >= docs.limits.maxResults;
        });
        return ok(matches.join("\n") || "No files found", { count: matches.length });
      } catch (error) {
        return failed(error);
      }
    },
  });

  pi.registerTool({
    name: "docs_grep",
    label: "Search documentation",
    description: "Search UTF-8 documents using a case-insensitive literal string; regular expressions are not accepted.",
    parameters: Type.Object({
      query: Type.String({ minLength: 1, maxLength: 500, description: "Literal text to search for" }),
      path: Type.Optional(Type.String({ description: "Starting path below the documentation root" })),
    }),
    async execute(_id, params) {
      try {
        const docs = await accessPromise;
        const start = await docs.safePath(params.path ?? ".");
        const query = params.query.toLowerCase();
        const matches: string[] = [];
        await docs.walk(start, async (path) => {
          let content: string;
          try {
            content = await docs.readTextFile(path);
          } catch {
            return false;
          }
          for (const [index, line] of content.split("\n").entries()) {
            if (line.toLowerCase().includes(query)) {
              matches.push(`${docs.displayPath(path)}:${index + 1}: ${line.slice(0, docs.limits.maxLineLength)}`);
              if (matches.length >= docs.limits.maxResults) return true;
            }
          }
          return false;
        });
        return ok(truncateUtf8(matches.join("\n") || "No matches found"), { count: matches.length });
      } catch (error) {
        return failed(error);
      }
    },
  });
}
