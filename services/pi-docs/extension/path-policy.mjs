import { constants } from "node:fs";
import { open, readdir, realpath, stat } from "node:fs/promises";
import { isAbsolute, join, relative, resolve } from "node:path";

export const LIMITS = Object.freeze({
  maxReadBytes: 128 * 1024,
  maxFileBytes: 2 * 1024 * 1024,
  maxResults: 200,
  maxEntries: 5000,
  maxLineLength: 500,
});

export async function createDocsAccess(configuredRoot, limits = LIMITS) {
  const root = await realpath(configuredRoot);

  function displayPath(path) {
    return relative(root, path) || ".";
  }

  async function safePath(input = ".") {
    if (typeof input !== "string" || input.includes("\0")) {
      throw new Error("Invalid path");
    }

    const candidate = resolve(root, input);
    const target = await realpath(candidate);
    const rel = relative(root, target);

    if (rel.startsWith("..") || isAbsolute(rel)) {
      throw new Error("Access denied: path is outside documentation root");
    }

    return target;
  }

  async function readTextFile(path) {
    const noFollow = constants.O_NOFOLLOW ?? 0;
    const handle = await open(path, constants.O_RDONLY | noFollow);

    try {
      const info = await handle.stat();
      if (!info.isFile()) throw new Error("Not a regular file");
      if (info.size > limits.maxFileBytes) {
        throw new Error(`File exceeds ${limits.maxFileBytes} byte limit`);
      }

      const buffer = Buffer.alloc(info.size);
      let position = 0;
      while (position < buffer.length) {
        const { bytesRead } = await handle.read(buffer, position, buffer.length - position, position);
        if (bytesRead === 0) break;
        position += bytesRead;
      }

      const data = buffer.subarray(0, position);
      if (data.subarray(0, 8192).includes(0)) {
        throw new Error("Binary files are not allowed");
      }
      return data.toString("utf8");
    } finally {
      await handle.close();
    }
  }

  async function walk(start, callback) {
    const startInfo = await stat(start);
    const stack = [];
    let visited = 0;

    if (startInfo.isFile()) stack.push({ path: start, file: true });
    else if (startInfo.isDirectory()) stack.push({ path: start, file: false });
    else throw new Error("Path is neither a file nor directory");

    while (stack.length > 0) {
      const current = stack.pop();
      if (current.file) {
        if (await callback(current.path)) return;
        continue;
      }

      const entries = await readdir(current.path, { withFileTypes: true });
      entries.sort((a, b) => b.name.localeCompare(a.name));

      for (const entry of entries) {
        if (++visited > limits.maxEntries) {
          throw new Error("Documentation tree entry limit exceeded");
        }
        if (entry.isSymbolicLink()) continue;

        const path = join(current.path, entry.name);
        if (entry.isDirectory()) stack.push({ path, file: false });
        else if (entry.isFile()) stack.push({ path, file: true });
      }
    }
  }

  return { root, safePath, displayPath, readTextFile, walk, limits };
}

export function truncateUtf8(text, maxBytes = LIMITS.maxReadBytes) {
  const data = Buffer.from(text, "utf8");
  if (data.length <= maxBytes) return text;
  return `${data.subarray(0, maxBytes).toString("utf8")}\n\n[Output truncated]`;
}
