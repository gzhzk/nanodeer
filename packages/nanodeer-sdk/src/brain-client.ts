import { spawn, ChildProcess } from "child_process";
import { Readable } from "stream";
import { BrainRequest, StreamEvent } from "./events.js";
import * as fs from "fs";
import * as path from "path";

export class BrainClient {
  private proc: ChildProcess | null = null;
  private reader: Readable | null = null;
  private buffer: string = "";
  private resolveLine: ((line: string) => void) | null = null;
  private lineQueue: string[] = [];
  private lineResolvers: ((line: string) => void)[] = [];

  private pythonPath: string;

  constructor(pythonPath?: string) {
    // Default: find project root, use .venv/bin/python
    if (!pythonPath) {
      let projectRoot = process.cwd();
      while (projectRoot && !fs.existsSync(projectRoot + "/.venv")) {
        const parent = path.dirname(projectRoot);
        if (parent === projectRoot) break;
        projectRoot = parent;
      }
      pythonPath = projectRoot + "/.venv/bin/python";
      if (!fs.existsSync(pythonPath)) {
        pythonPath = "python3";
      }
    }
    this.pythonPath = pythonPath;
  }

  private ensureRunning(): void {
    if (this.proc) return;

    // Detect project root: go up from nanodeer-sdk to find .venv
    let projectRoot = process.cwd();
    while (projectRoot && !fs.existsSync(projectRoot + "/.venv")) {
      const parent = path.dirname(projectRoot);
      if (parent === projectRoot) break; // Reached root
      projectRoot = parent;
    }

    this.proc = spawn(this.pythonPath, ["-u", "-m", "nanodeer.brain", "--stdio"], {
      stdio: ["pipe", "pipe", "pipe"],
      env: {
        ...process.env,
        PYTHONPATH: projectRoot + "/packages/nanodeer-kernel/src",
      },
    });

    this.reader = this.proc.stdout!;

    this.reader.on("data", (chunk: Buffer) => {
      this.buffer += chunk.toString();
      const lines = this.buffer.split("\n");
      this.buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.trim()) {
          const resolve = this.lineResolvers.shift();
          if (resolve) {
            resolve(line);
          } else {
            this.lineQueue.push(line);
          }
        }
      }
    });

    this.proc.stderr!.on("data", (chunk: Buffer) => {
      // Log brain stderr (logs, not JSON)
      const lines = chunk.toString().trim().split("\n");
      for (const line of lines) {
        if (line.trim()) {
          console.error(line);
        }
      }
    });

    this.proc.on("error", (err) => {
      console.error(`Brain process error: ${err.message}`);
    });

    this.proc.on("exit", (code) => {
      if (code !== 0 && code !== null) {
        console.error(`Brain process exited with code ${code}`);
      }
      this.proc = null;
      this.reader = null;
    });
  }

  private async readLine(): Promise<string> {
    this.ensureRunning();

    if (this.lineQueue.length > 0) {
      return this.lineQueue.shift()!;
    }

    return new Promise<string>((resolve) => {
      this.lineResolvers.push(resolve);
    });
  }

  private async readEvent(): Promise<StreamEvent | null> {
    const line = await this.readLine();
    if (!line) return null;
    try {
      return JSON.parse(line) as StreamEvent;
    } catch {
      console.error(`Failed to parse JSON: ${line}`);
      return null;
    }
  }

  async *stream(request: BrainRequest): AsyncGenerator<StreamEvent> {
    this.ensureRunning();

    // Send request
    const reqLine = JSON.stringify(request) + "\n";
    this.proc!.stdin!.write(reqLine);

    // Read events until end
    while (true) {
      const event = await this.readEvent();
      if (!event) break;

      yield event;

      if (event.event === "end" || event.event === "error" || event.event === "cancelled") {
        break;
      }
    }
  }

  async execute(prompt: string, threadId?: string): Promise<StreamEvent[]> {
    const events: StreamEvent[] = [];
    for await (const event of this.stream({ type: "execute", prompt, threadId })) {
      events.push(event);
    }
    return events;
  }

  async ping(): Promise<boolean> {
    try {
      for await (const event of this.stream({ type: "ping" })) {
        if (event.event === "pong") return true;
      }
      return false;
    } catch {
      return false;
    }
  }

  close(): void {
    if (this.proc) {
      this.proc.kill();
      this.proc = null;
      this.reader = null;
    }
  }
}
