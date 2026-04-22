#!/usr/bin/env node
import * as readline from "readline";
import { BrainClient } from "./brain-client.js";
import { StreamEvent } from "./events.js";

const PROMPT_SYMBOL = "❯ ";
const DONE_SYMBOL = "✓";
const ERROR_SYMBOL = "✗";

async function renderEvent(event: StreamEvent): Promise<void> {
  switch (event.event) {
    case "turn_start":
      // Silent
      break;

    case "llm_token":
      // Stream tokens to stdout without newline
      process.stdout.write(event.text);
      break;

    case "tool_call":
      console.log("\n" + chalk.blue(`[TOOL_CALL: ${event.name}]`));
      if (event.args && Object.keys(event.args).length > 0) {
        const argsStr = JSON.stringify(event.args, null, 2)
          .split("\n")
          .map((l) => "  " + l)
          .join("\n");
        console.log(chalk.gray(argsStr));
      }
      break;

    case "tool_result":
      console.log("\n" + chalk.cyan("[RESULT]"));
      console.log(event.result.slice(0, 500));
      if (event.result.length > 500) {
        console.log(chalk.gray("...(truncated)"));
      }
      break;

    case "end":
      console.log("\n");
      if (event.next_action === "end") {
        console.log(
          chalk.green(`${DONE_SYMBOL} Done`) +
            chalk.gray(` (${event.durationMs}ms)`)
        );
      } else {
        console.log(
          chalk.yellow(`${ERROR_SYMBOL} ${event.next_action}`) +
            chalk.gray(` (${event.durationMs}ms)`)
        );
      }
      break;

    case "error":
      console.error(
        "\n" + chalk.red(`${ERROR_SYMBOL} Error: ${event.message}`)
      );
      break;

    case "wait":
      if (event.question) {
        console.log("\n" + chalk.yellow("Awaiting input: " + event.question));
      }
      break;

    default:
      // Ignore unknown events silently
      break;
  }
}

async function interactive(cli: BrainClient): Promise<void> {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  console.log(chalk.blue("🤖 NanoDeer Agent"));
  console.log(chalk.gray("Type your task... (Ctrl+C to exit)\n"));

  const askQuestion = (): Promise<string> => {
    return new Promise((resolve) => {
      rl.question(chalk.green(PROMPT_SYMBOL), (answer) => {
        resolve(answer);
      });
    });
  };

  while (true) {
    try {
      const prompt = await askQuestion();
      if (!prompt.trim()) continue;

      // Execute and stream events
      const events = await cli.execute(prompt);

      // If end event shows wait, prompt for more
      const endEvent = events.find((e) => e.event === "end");
      if (endEvent && endEvent.event === "end" && endEvent.next_action === "wait") {
        // Get clarification question
        const waitEvent = events.find((e) => e.event === "wait");
        if (waitEvent && waitEvent.event === "wait") {
          console.log(chalk.yellow("\nClarification needed: " + waitEvent.question));
        }
      }
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code === "EOF") {
        break;
      }
      console.error(chalk.red(`Error: ${err}`));
    }
  }

  rl.close();
}

// Simple non-interactive mode
async function main(): Promise<void> {
  const args = process.argv.slice(2);

  if (args.length === 0) {
    // Interactive mode
    const cli = new BrainClient();
    await interactive(cli);
    cli.close();
  } else {
    // Single shot mode
    const prompt = args.join(" ");
    const cli = new BrainClient();

    process.stdout.write(chalk.gray(`Executing: "${prompt}"\n\n`));

    try {
      for await (const event of cli.stream({ type: "execute", prompt })) {
        await renderEvent(event);
      }
    } finally {
      cli.close();
    }
  }
}

// Lazy import chalk only if we have TTY
import chalk from "chalk";

// Detect python path
function detectPython(): string {
  // Try common python commands
  const candidates = ["python3", "python", ".venv/bin/python"];
  for (const cmd of candidates) {
    try {
      const { execSync } = require("child_process");
      execSync(cmd + " --version", { stdio: "ignore" });
      return cmd;
    } catch {
      // Continue
    }
  }
  return "python3"; // Fallback
}

main().catch(console.error);
