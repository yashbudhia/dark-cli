#!/usr/bin/env node
import { main } from "../lib/runtime.mjs";

main(process.argv.slice(2)).catch((error) => {
  console.error(`Dark: ${error.message}`);
  process.exitCode = 1;
});
