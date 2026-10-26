import { mkdir, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = fileURLToPath(new URL("../", import.meta.url));
const manifest = JSON.parse(
  await readFile(path.join(root, "assets-manifest.json"), "utf8"),
);
await Promise.all(
  manifest.assets.map(async ({ file, source }) => {
    const target = path.join(root, "public", "framer", file);
    await mkdir(path.dirname(target), { recursive: true });
    const response = await fetch(source, {
      signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok) throw new Error(`${file}: HTTP ${response.status}`);
    await writeFile(target, Buffer.from(await response.arrayBuffer()));
    console.info(`Downloaded ${file}`);
  }),
);
