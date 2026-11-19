#!/usr/bin/env node
import { crashLine, main } from "../src/cli.js";

const argv = process.argv.slice(2);
try {
  // `check` answers at once; `translate` talks to the API and answers with a promise.
  process.exitCode = await main(argv);
} catch (e) {
  // A crash must not look like a clean run, and must not look like "a translation is broken"
  // (exit 1) either: 2 is "the command itself could not be done".
  process.stderr.write(crashLine(argv, e) + "\n");
  if (process.env.KAERIS_DEBUG && e && e.stack) process.stderr.write(e.stack + "\n");
  process.exitCode = 2;
}
