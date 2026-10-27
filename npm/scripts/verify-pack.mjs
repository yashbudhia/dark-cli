import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

// Invoke npm through node, preserving argument boundaries on Windows too.
const npm = process.env.npm_execpath;
assert.ok(npm, "Run through npm run test:pack");
const root = fileURLToPath(new URL("../", import.meta.url));
const result = spawnSync(process.execPath, [npm, "pack", "--dry-run", "--ignore-scripts", "--json"], {
  cwd: root, encoding: "utf8",
});
assert.equal(result.status, 0, result.stderr);
const [packed] = JSON.parse(result.stdout);
const paths = packed.files.map((file) => file.path);
for (const required of ["README.md", "package.json", "bin/dark.mjs", "lib/runtime.mjs", "lib/update.mjs", "scripts/extract.ps1", "python/manifest.json", "python/requirements.txt"]) {
  assert.ok(paths.includes(required), `Missing release file: ${required}`);
}
assert.equal(paths.filter((path) => /^python\/dark_cli-.*\.whl$/.test(path)).length, 1);
for (const path of paths) {
  assert.ok(/^(README\.md|package\.json|bin\/dark\.mjs|lib\/(runtime|update)\.mjs|scripts\/extract\.ps1|python\/(manifest\.json|requirements\.txt|dark_cli-[\w.-]+\.whl))$/.test(path), `Unexpected published file: ${path}`);
}
console.log(`Verified npm payload: ${paths.length} allowlisted files; no environment files or repository access required.`);
