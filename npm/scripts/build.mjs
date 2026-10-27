import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const payload = join(root, "npm", "python");
await mkdir(payload, { recursive: true });
for (const name of await readdir(payload)) {
  if (name.endsWith(".whl") || name === "manifest.json") await rm(join(payload, name));
}
const build = spawnSync("uv", ["build", join(root, "cli"), "--wheel", "--out-dir", payload], { stdio: "inherit", shell: false });
if (build.error || build.status !== 0) throw new Error("Install uv to build the Python payload, then retry npm pack.");
// uv ignores build output in Git; that nested file would also hide it from npm.
await rm(join(payload, ".gitignore"), { force: true });
const wheels = (await readdir(payload)).filter((name) => name.endsWith(".whl"));
if (wheels.length !== 1) throw new Error("Expected exactly one CLI wheel.");
const wheel = wheels[0];
const pkg = JSON.parse(await readFile(join(root, "npm", "package.json"), "utf8"));
if (wheel !== `dark_cli-${pkg.version}-py3-none-any.whl`) throw new Error("npm and Python CLI versions must match.");
const digest = async (path) => createHash("sha256").update(await readFile(path)).digest("hex");
await writeFile(join(payload, "manifest.json"), JSON.stringify({
  wheel, wheelSha256: await digest(join(payload, wheel)),
  requirementsSha256: await digest(join(payload, "requirements.txt")),
}, null, 2) + "\n");
