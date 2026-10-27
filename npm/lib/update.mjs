import { execFile, spawn } from "node:child_process";
import { access, readFile, realpath } from "node:fs/promises";
import { delimiter, dirname, join, resolve } from "node:path";
import { promisify } from "node:util";

const execute = promisify(execFile);

export function isGlobalInstall(packageRoot, npmRoot, platform = process.platform) {
  const normalize = (path) => {
    const value = resolve(path).replace(/[\\/]+$/, "");
    return platform === "win32" ? value.toLowerCase() : value;
  };
  return normalize(packageRoot) === normalize(join(npmRoot, "dark-agent-cli"));
}

export async function npmScript() {
  const nodeDirectory = dirname(process.execPath);
  const candidates = [process.env.npm_execpath,
    join(nodeDirectory, "node_modules", "npm", "bin", "npm-cli.js"),
    join(nodeDirectory, "..", "lib", "node_modules", "npm", "bin", "npm-cli.js")];
  for (const directory of (process.env.PATH || "").split(delimiter)) {
    if (!directory) continue;
    candidates.push(join(directory, "node_modules", "npm", "bin", "npm-cli.js"));
    if (process.platform !== "win32") {
      try { candidates.push(await realpath(join(directory, "npm"))); } catch { /* Try next directory. */ }
    }
  }
  for (const candidate of candidates) {
    if (!candidate?.endsWith("npm-cli.js")) continue;
    try { await access(candidate); return candidate; } catch { /* Try next candidate. */ }
  }
  throw new Error("npm was not found. Install Node.js with npm, then run npm install -g dark-agent-cli@latest.");
}

export async function selfUpdate(packageRoot, operations = {}) {
  const npm = operations.npm || await npmScript();
  const capture = operations.capture || (async (args) => {
    const { stdout } = await execute(process.execPath, [npm, ...args], { encoding: "utf8", timeout: 60_000, windowsHide: true });
    return stdout.trim();
  });
  const install = operations.install || ((args) => new Promise((resolveCode, reject) => {
    const child = spawn(process.execPath, [npm, ...args], { stdio: "inherit", shell: false, windowsHide: true });
    child.once("error", reject);
    child.once("exit", (code) => resolveCode(code ?? 1));
  }));
  const root = await capture(["root", "--global"]);
  if (!isGlobalInstall(packageRoot, root)) {
    throw new Error("This is a local or npx install. Use npm install -g dark-agent-cli@latest, or npx --yes --package dark-agent-cli@latest dark.");
  }
  const pkg = JSON.parse(await readFile(join(packageRoot, "package.json"), "utf8"));
  const latest = await capture(["view", "dark-agent-cli", "version", "--prefer-online", "--registry=https://registry.npmjs.org"]);
  if (!/^\d+\.\d+\.\d+$/.test(latest)) throw new Error("npm returned an invalid release version. Retry the update shortly.");
  const currentParts = pkg.version.split(".").map(Number);
  const latestParts = latest.split(".").map(Number);
  const comparison = latestParts.map((part, index) => part - currentParts[index]).find((difference) => difference !== 0) || 0;
  if (comparison <= 0) {
    console.error(`Dark ${pkg.version} is already current.`);
    return;
  }
  console.error(`Updating Dark ${pkg.version} → ${latest}…`);
  const code = await install(["install", "--global", `dark-agent-cli@${latest}`, "--registry=https://registry.npmjs.org", "--prefer-online"]);
  if (code !== 0) throw new Error(`npm update failed (exit ${code}). Retry npm install -g dark-agent-cli@latest.`);
  console.error(`Dark updated to ${latest}.`);
}
