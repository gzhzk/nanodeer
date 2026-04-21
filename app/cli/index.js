#!/usr/bin/env node
/**
 * NanoDeer TS CLI - Thin client for nanodeer agent harness.
 *
 * Usage:
 *   node index.js "your prompt here"
 */

const { spawn } = require("child_process");
const readline = require("readline");
const path = require("path");

// ── ANSI Colors ──────────────────────────────────────────────────────────────
const C = {
  title: "\x1b[34m",
  sep: "\x1b[90m",
  green: "\x1b[32m",
  yellow: "\x1b[33m",
  cyan: "\x1b[36m",
  gray: "\x1b[90m",
  dim: "\x1b[2m",
  bold: "\x1b[1m",
  reset: "\x1b[0m",
};

// ── ASCII Art ─────────────────────────────────────────────────────────────────
const NANODEER_ASCII = [
  "███╗   ██╗ █████╗ ███╗   ██╗ ██████╗ ██████╗ ███████╗███████╗██████╗ ",
  "████╗  ██║██╔══██╗████╗  ██║██╔═══██╗██╔══██╗██╔════╝██╔════╝██╔══██╗",
  "██╔██╗ ██║███████║██╔██╗ ██║██║   ██║██║  ██║█████╗  █████╗  ██████╔╝",
  "██║╚██╗██║██╔══██║██║╚██╗██║██║   ██║██║  ██║██╔══╝  ██╔══╝  ██╔══██╗",
  "██║ ╚████║██║  ██║██║ ╚████║╚██████╔╝██████╔╝███████╗███████╗██║  ██║",
  "╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═╝",
];

const VERSION = "0.1.0";

// ── Helpers ───────────────────────────────────────────────────────────────────
function truncate(s, max = 200) {
  if (!s) return "";
  return s.length > max ? s.slice(0, max) + "\x1b[90m...\x1b[0m" : s;
}

function formatEvent(ev) {
  switch (ev.type) {
    case "memory_context":
      return ev.has_memory
        ? `${C.gray}  [memory] loaded${C.reset}`
        : `${C.gray}  [memory] empty${C.reset}`;

    case "todos":
      return ev.count > 0
        ? `${C.gray}  [todos] ${ev.count} pending${C.reset}`
        : `${C.gray}  [todos] none${C.reset}`;

    case "sandbox_acquired":
      return `${C.cyan}  [sandbox] ${ev.exec_id}${C.reset}`;

    case "tool_call":
      return `${C.yellow}  [tool] ${ev.name}: ${truncate(ev.command, 80)}${C.reset}`;

    case "tool_result":
      return `${C.gray}    -> ${truncate(ev.result, 120)}${C.reset}`;

    case "end":
      return `\n${C.sep}--------------------------------------------------------------------\n${C.gray}  Done in ${ev.duration_ms}ms | ${ev.next_action}${C.reset}\n`;

    default:
      return "";
  }
}

// ── Banner ────────────────────────────────────────────────────────────────────
function printBanner() {
  // Use ASCII box for cross-terminal compatibility
  console.log(`\n${C.title}+${"-".repeat(76)}+${C.reset}`);
  // Title line
  const titleText = `NanoDeer ${VERSION}`;
  const titlePad = Math.floor((76 - titleText.length) / 2);
  console.log(`${C.title}|${" ".repeat(titlePad)}${C.bold}${C.green}${titleText}${C.reset}${C.title}${" ".repeat(76 - titlePad - titleText.length)}|${C.reset}`);
  console.log(`${C.title}+${"-".repeat(76)}+${C.reset}`);
  // ASCII art
  const artWidth = 72;
  for (const line of NANODEER_ASCII) {
    const padding = Math.floor((76 - artWidth) / 2);
    console.log(`${C.title}|${" ".repeat(padding)}${C.green}${line}${C.reset}${" ".repeat(76 - padding - line.length)}|${C.reset}`);
  }
  console.log(`${C.title}+${"-".repeat(76)}+${C.reset}`);
  // Welcome
  console.log(`${C.title}|${C.reset}  ${C.green}Welcome!${C.reset}${" ".repeat(63)}|${C.reset}`);
  console.log(`${C.title}|${C.reset}${C.gray}  ~/workspace  -  Docker Sandbox${" ".repeat(39)}|${C.reset}`);
  console.log(`${C.title}+${"-".repeat(76)}+${C.reset}`);
  console.log(`${C.dim}  Type your prompt or '?' for shortcuts${C.reset}\n`);
  console.log(`${C.sep}${"-".repeat(76)}\n`);
}

// ── Main ──────────────────────────────────────────────────────────────────────
async function main() {
  const args = process.argv.slice(2);
  if (args.length === 0) {
    console.error(`Usage: node index.js "your prompt here"`);
    process.exit(1);
  }

  const userArgs = args.join(" ");
  printBanner();

  // nanodeer installed via pip: just use "nanodeer" command
  // development: set NANODEER_CLI to python executable, NANODEER_PYTHONPATH to project root
  let cmd, pythonArgs, envExtra = {};
  const cliBase = process.env.NANODEER_CLI || "nanodeer";

  if (cliBase === "nanodeer") {
    // Installed via pip - use directly
    cmd = "nanodeer";
    pythonArgs = ["cli", "--json-events", userArgs];
  } else {
    // Development mode - python executable + module
    const pythonExe = cliBase;
    const pythonPath = process.env.NANODEER_PYTHONPATH || path.dirname(path.dirname(__dirname));
    cmd = pythonExe;
    pythonArgs = ["-m", "app.cli.cli", "cli", "--json-events", userArgs];
    envExtra = { PYTHONPATH: pythonPath };
  }

  const child = spawn(cmd, pythonArgs, {
    env: { ...process.env, ...envExtra },
  });

  child.on("error", (err) => {
    if (err.code === "ENOENT") {
      console.error(`${C.yellow}Error: 'nanodeer' command not found.${C.reset}`);
      console.error(`  Please install: pip install nanodeer-ai`);
      console.error(`  Or set NANODEER_CLI environment variable to your CLI path.`);
      process.exit(1);
    }
    throw err;
  });

  const rl = readline.createInterface({ input: child.stdout });

  for await (const line of rl) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const ev = JSON.parse(trimmed);
      const formatted = formatEvent(ev);
      if (formatted) console.log(formatted);
    } catch {
      console.log(trimmed);
    }
  }

  child.stderr.on("data", (d) => process.stderr.write(d));
  child.on("close", (code) => {
    if (code !== 0) process.exit(code);
  });
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
