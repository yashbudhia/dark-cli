import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";
import { selfUpdate } from "../lib/update.mjs";

test("updating a local/npx package never changes the global installation", async () => {
  let installed = false;
  await assert.rejects(selfUpdate(join(tmpdir(), "project", "node_modules", "dark-agent-cli"), {
    npm: "test-npm", capture: async () => join(tmpdir(), "global", "node_modules"),
    install: async () => { installed = true; return 0; },
  }), /local or npx/);
  assert.equal(installed, false);
});

test("global update installs the verified release and avoids downgrades", async () => {
  const root = await mkdtemp(join(tmpdir(), "dark-update-"));
  const globalRoot = join(root, "node_modules");
  const pkg = join(globalRoot, "dark-agent-cli");
  await mkdir(pkg, { recursive: true });
  await writeFile(join(pkg, "package.json"), JSON.stringify({ version: "0.2.0" }));
  const installs = [];
  const operations = {
    npm: "test-npm",
    capture: async (args) => args[0] === "root" ? globalRoot : "0.3.0",
    install: async (args) => { installs.push(args); return 0; },
  };
  try {
    await selfUpdate(pkg, operations);
    assert.deepEqual(installs[0], ["install", "--global", "dark-agent-cli@0.3.0", "--registry=https://registry.npmjs.org"]);
    operations.capture = async (args) => args[0] === "root" ? globalRoot : "0.1.0";
    await selfUpdate(pkg, operations);
    assert.equal(installs.length, 1);
  } finally { await rm(root, { recursive: true, force: true }); }
});
