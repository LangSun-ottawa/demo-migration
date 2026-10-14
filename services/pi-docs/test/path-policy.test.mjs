import assert from "node:assert/strict";
import { mkdtemp, mkdir, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { createDocsAccess } from "../extension/path-policy.mjs";

async function fixture() {
  const base = await mkdtemp(join(tmpdir(), "pi-docs-test-"));
  const docs = join(base, "docs");
  const outside = join(base, "secret.txt");
  await mkdir(join(docs, "guide"), { recursive: true });
  await writeFile(join(docs, "guide", "sandbox.md"), "sandbox network policy\n", "utf8");
  await writeFile(outside, "secret\n", "utf8");
  await symlink(outside, join(docs, "escape-link"));
  return { base, docs, outside };
}

test("allows a regular document below root", async () => {
  const { docs } = await fixture();
  const access = await createDocsAccess(docs);
  const path = await access.safePath("guide/sandbox.md");
  assert.equal(await access.readTextFile(path), "sandbox network policy\n");
});

test("blocks parent-directory traversal", async () => {
  const { docs } = await fixture();
  const access = await createDocsAccess(docs);
  await assert.rejects(() => access.safePath("../secret.txt"), /outside documentation root/);
});

test("blocks a symlink that escapes root", async () => {
  const { docs } = await fixture();
  const access = await createDocsAccess(docs);
  await assert.rejects(() => access.safePath("escape-link"), /outside documentation root/);
});

test("walker ignores symlinks", async () => {
  const { docs } = await fixture();
  const access = await createDocsAccess(docs);
  const files = [];
  await access.walk(await access.safePath("."), async (path) => files.push(access.displayPath(path)) && false);
  assert.deepEqual(files, ["guide/sandbox.md"]);
});
