import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, readFile, writeFile, mkdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { cacheDirectory, target, verifyDigest, withLock } from "../lib/runtime.mjs";

test("platform selection rejects unsupported architectures before downloads", () => {
  assert.match(target("win32", "x64").asset, /windows-msvc.zip$/);
  assert.match(target("darwin", "arm64").asset, /apple-darwin.tar.gz$/);
  assert.throws(() => target("linux", "ia32"), /Unsupported platform/);
});

test("corrupt downloads cannot execute", () => {
  const bytes = Buffer.from("runtime");
  const digest = createHash("sha256").update(bytes).digest("hex");
  verifyDigest(bytes, digest);
  assert.throws(() => verifyDigest(Buffer.from("changed"), digest), /integrity/);
});

test("runtime cache is outside the global npm package and can be overridden", () => {
  assert.equal(cacheDirectory({ DARK_RUNTIME_DIR: join(tmpdir(), "dark-custom") }), join(tmpdir(), "dark-custom"));
  assert.equal(cacheDirectory({ LOCALAPPDATA: "C:\\User Data" }, "win32"), join("C:\\User Data", "Dark", "runtime"));
});

test("concurrent setup runs serialize, release on failure, and recover dead owners", async () => {
  const root = await mkdtemp(join(tmpdir(), "dark-lock-"));
  const lock = join(root, "setup.lock");
  const state = join(root, "state");
  await writeFile(state, "0");
  try {
    await Promise.all([1, 2, 3].map(() => withLock(lock, async () => {
      const value = Number(await readFile(state, "utf8"));
      await new Promise((resolve) => setTimeout(resolve, 25));
      await writeFile(state, String(value + 1));
    })));
    assert.equal(await readFile(state, "utf8"), "3");
    await assert.rejects(withLock(lock, () => { throw new Error("interrupted"); }), /interrupted/);
    await mkdir(lock);
    await writeFile(join(lock, "owner"), "2147483647");
    assert.equal(await withLock(lock, () => 42), 42);
  } finally { await rm(root, { recursive: true, force: true }); }
});
