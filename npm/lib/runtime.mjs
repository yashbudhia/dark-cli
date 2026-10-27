import { createHash, randomUUID } from "node:crypto";
import { spawn } from "node:child_process";
import { createWriteStream } from "node:fs";
import { access, mkdir, readFile, rename, rm, stat, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { fileURLToPath } from "node:url";
import { setTimeout as delay } from "node:timers/promises";
import { selfUpdate } from "./update.mjs";

const PACKAGE = fileURLToPath(new URL("../", import.meta.url));
const UV_VERSION = "0.13.6";
const UV_TARGETS = {
  "win32-x64": ["x86_64-pc-windows-msvc.zip", "a2a8820d5eea32f08ef467ef3b7f66883a9b076d5737a2fc2fbb5f458d1bb50f"],
  "win32-arm64": ["aarch64-pc-windows-msvc.zip", "c2426c0c8e28b53d8c440e47a18d96ad4db51e159866c0e81435b196d7f0081c"],
  "darwin-x64": ["x86_64-apple-darwin.tar.gz", "63ba17fdda55ad1a230d4b37fc6017ffa10c23688c83818bd3bfdf914c652a02"],
  "darwin-arm64": ["aarch64-apple-darwin.tar.gz", "60fbd5c8a1ed681845eea28d9d622fcde03c51e91a43465b64a1e17db1ed3472"],
  "linux-x64": ["x86_64-unknown-linux-gnu.tar.gz", "f29c3e94ffabd7e6f3ba521dba169a9b7ec12100bf3257087f0f24f6123f3645"],
  "linux-arm64": ["aarch64-unknown-linux-gnu.tar.gz", "229e194255c7958d86d56e8790d969a6f74736592133f0dfd0076f754c642c1d"],
  "linux-x64-musl": ["x86_64-unknown-linux-musl.tar.gz", "5d61f26b6c7213779eda90edc6971ea6b0b796bfb8d49a574c8ad69b59838548"],
  "linux-arm64-musl": ["aarch64-unknown-linux-musl.tar.gz", "819692e404d23e5aae6bc44c0e260f1f5492fd1910ab4693b2c650f926dbe800"],
};

// glibc builds of Node report the C library version they run on; musl builds (Alpine) do not.
export function libc(platform = process.platform, report = () => process.report?.getReport()) {
  return platform === "linux" && !report()?.header?.glibcVersionRuntime ? "musl" : "";
}

export function target(platform = process.platform, arch = process.arch, variant = "") {
  const entry = UV_TARGETS[[platform, arch, variant].filter(Boolean).join("-")];
  if (!entry) throw new Error(`Unsupported platform: ${platform}/${arch}. Use Windows, macOS or Linux on x64/arm64.`);
  const [suffix, sha256] = entry;
  return { asset: `uv-${suffix}`, sha256, folder: `uv-${suffix.replace(/\.(zip|tar\.gz)$/, "")}` };
}

export function cacheDirectory(env = process.env, platform = process.platform) {
  if (env.DARK_RUNTIME_DIR) return resolve(env.DARK_RUNTIME_DIR);
  if (platform === "win32") return join(env.LOCALAPPDATA || join(homedir(), "AppData", "Local"), "Dark", "runtime");
  return join(env.XDG_CACHE_HOME || join(homedir(), ".cache"), "dark-cli");
}

async function exists(path) {
  try { await access(path); return true; } catch { return false; }
}

export function verifyDigest(bytes, expected) {
  if (createHash("sha256").update(bytes).digest("hex") !== expected) {
    throw new Error("Download integrity check failed. Nothing was executed; retry the command.");
  }
}

// Keep first-run setup exclusive across terminals. Dead owners can be retried safely.
export async function withLock(path, operation) {
  await mkdir(dirname(path), { recursive: true });
  const deadline = Date.now() + 10 * 60_000;
  while (true) {
    try { await mkdir(path); break; } catch (error) {
      if (error.code !== "EEXIST") throw error;
      let stale = false;
      try {
        const pid = Number(await readFile(join(path, "owner"), "utf8"));
        if (!Number.isSafeInteger(pid) || pid <= 0) throw new Error("Invalid setup owner");
        try { process.kill(pid, 0); } catch (failure) { stale = failure.code === "ESRCH"; }
      } catch {
        try { stale = Date.now() - (await stat(path)).mtimeMs > 60_000; } catch { /* Owner finished. */ }
      }
      if (stale) { await rm(path, { recursive: true, force: true }); continue; }
      if (Date.now() > deadline) throw new Error("Another Dark setup is still running. Wait for it to finish and retry.");
      await delay(300);
    }
  }
  try {
    await writeFile(join(path, "owner"), String(process.pid));
    return await operation();
  } finally { await rm(path, { recursive: true, force: true }); }
}

function run(command, args, env = process.env) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { env, stdio: "inherit", shell: false, windowsHide: true });
    child.once("error", () => reject(new Error(`Could not start ${command}. Check that it exists and is executable.`)));
    child.once("exit", (code, signal) => {
      if (signal) reject(new Error(`Process stopped by ${signal}.`));
      else resolve(code ?? 1);
    });
  });
}

async function checked(command, args, env) {
  const code = await run(command, args, env);
  if (code !== 0) throw new Error(`Runtime setup failed (exit ${code}). Check your network connection, then retry.`);
}

async function archive(url, sha256, destination, executable) {
  if (await exists(join(destination, executable))) return join(destination, executable);
  const temporary = `${destination}.${randomUUID()}`;
  const download = `${temporary}${url.endsWith(".zip") ? ".zip" : ".tar.gz"}`;
  await mkdir(temporary, { recursive: true });
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(180_000) });
    if (!response.ok || !response.body) throw new Error(`Runtime download failed (HTTP ${response.status}). Retry when online.`);
    await pipeline(Readable.fromWeb(response.body), createWriteStream(download));
    verifyDigest(await readFile(download), sha256);
    if (url.endsWith(".zip")) {
      const system = join(process.env.SystemRoot || process.env.WINDIR || "C:\\Windows", "System32");
      // Windows 10 1803+ includes tar, which extracts zips far faster than PowerShell.
      const extracted = await run(join(system, "tar.exe"), ["-xf", download, "-C", temporary]).catch(() => 1);
      if (extracted !== 0) {
        await checked(join(system, "WindowsPowerShell", "v1.0", "powershell.exe"), ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", join(PACKAGE, "scripts", "extract.ps1"), "-Archive", download, "-Destination", temporary]);
      }
    } else {
      await checked("tar", ["-xzf", download, "-C", temporary]);
    }
    if (!(await exists(join(temporary, executable)))) throw new Error("Downloaded runtime is missing its executable.");
    await rename(temporary, destination);
    return join(destination, executable);
  } finally {
    await rm(download, { force: true });
    await rm(temporary, { recursive: true, force: true });
  }
}

export async function ensureRuntime(root = cacheDirectory()) {
  target();
  const payload = join(PACKAGE, "python");
  const manifest = JSON.parse(await readFile(join(payload, "manifest.json"), "utf8"));
  if (!/^dark_cli-[0-9][A-Za-z0-9_.-]*\.whl$/.test(manifest.wheel)) throw new Error("Invalid packaged CLI wheel.");
  const wheel = join(payload, manifest.wheel);
  const requirements = join(payload, "requirements.txt");
  verifyDigest(await readFile(wheel), manifest.wheelSha256);
  verifyDigest(await readFile(requirements), manifest.requirementsSha256);
  const fingerprint = createHash("sha256").update(JSON.stringify(manifest)).digest("hex").slice(0, 20);
  const environment = join(root, `cli-${fingerprint}-${process.platform}-${process.arch}`);
  const python = join(environment, process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  const marker = join(environment, ".ready");
  if (await exists(marker) && await exists(python)) return python;
  return withLock(join(root, "setup.lock"), async () => {
    if (await exists(marker) && await exists(python)) return python;
    console.error("Dark: preparing the CLI runtime (first run only)…");
    const variant = libc();
    const build = target(process.platform, process.arch, variant);
    const uv = await archive(
      `https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${build.asset}`,
      build.sha256, join(root, ["uv", UV_VERSION, process.platform, process.arch, variant].filter(Boolean).join("-")),
      process.platform === "win32" ? "uv.exe" : `${build.folder}/uv`,
    );
    const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => !/^(UV_|PYTHONPATH$|PYTHONHOME$|VIRTUAL_ENV$)/i.test(key)));
    Object.assign(env, {
      UV_PYTHON_INSTALL_DIR: join(root, "python"),
      UV_CACHE_DIR: join(root, "cache"),
      UV_PYTHON_PREFERENCE: "only-managed",
      UV_PYTHON_DOWNLOADS: "automatic",
      UV_NO_CONFIG: "1",
      UV_DEFAULT_INDEX: "https://pypi.org/simple",
    });
    await checked(uv, ["--quiet", "venv", "--clear", "--python", "3.12", environment], env);
    // Compiling bytecode now keeps the first launch as fast as later ones.
    await checked(uv, ["--quiet", "pip", "sync", "--python", python, "--require-hashes", "--only-binary", ":all:", "--compile-bytecode", requirements], env);
    await checked(uv, ["--quiet", "pip", "install", "--python", python, "--no-deps", "--compile-bytecode", wheel], env);
    await writeFile(marker, manifest.wheelSha256);
    return python;
  });
}

async function ensureDesktop(root) {
  if (process.platform !== "win32" || process.arch !== "x64") {
    throw new Error("Automatic desktop setup supports Windows x64. Other Windows architectures need DARK_WINDOWS_MCP_PATH.");
  }
  const server = join(root, "windows-mcp-1.3.28", "Sbroenne.WindowsMcp.exe");
  if (await exists(server)) return server;
  return withLock(join(root, "desktop.lock"), () => archive(
    "https://github.com/sbroenne/mcp-windows/releases/download/v1.3.28/windows-mcp-server-1.3.28-win-x64.zip",
    "9ca69685222d3c4934680218b4a2b3b7ae5bd0c8d2ce8bc2220925f4bd924fe4",
    join(root, "windows-mcp-1.3.28"), "Sbroenne.WindowsMcp.exe",
  ));
}

export async function main(args) {
  if (args[0] === "update" && !args.includes("--help")) {
    await selfUpdate(PACKAGE);
    return;
  }
  const root = cacheDirectory();
  const python = await ensureRuntime(root);
  const env = { ...process.env };
  delete env.PYTHONPATH;
  delete env.PYTHONHOME;
  env.PYTHONUTF8 = "1";
  env.PYTHONIOENCODING = "utf-8";
  env.DARK_NPM_LAUNCHER = join(PACKAGE, "bin", "dark.mjs");
  // Python still loads the caller's .env and preserves explicit shell settings.
  const desktopCommand = args[0] === "desktop" && args.length > 1;
  const agentCommand = args.length === 0 || ["chat", "run"].includes(args[0]);
  if ((desktopCommand || (agentCommand && process.platform === "win32" && process.arch === "x64")) && !args.includes("--help") && !env.DARK_WINDOWS_MCP_PATH) {
    // Python loads .env once; a custom MCP path takes precedence over this fallback.
    env.DARK_BUNDLED_WINDOWS_MCP_PATH = await ensureDesktop(root);
  }
  const code = await run(python, ["-m", "dark_cli", ...args], env);
  if (code === 85) {
    await selfUpdate(PACKAGE);
    process.exitCode = await run(process.execPath, [join(PACKAGE, "bin", "dark.mjs")]);
  } else process.exitCode = code;
}
