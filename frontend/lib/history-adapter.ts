import type { ThreadHistoryAdapter, ThreadMessageLike } from "@assistant-ui/react";
import { ExportedMessageRepository } from "@assistant-ui/react";
import type { BackendMessage } from "@/lib/types";
import { getCurrentThreadId } from "@/components/nanodeer-adapter";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "";

function textPart(text: string) {
  return { type: "text" as const, text };
}

function toolCallPart(tc: NonNullable<BackendMessage["tool_calls"]>[0]) {
  return {
    type: "tool-call" as const,
    toolCallId: tc.id || undefined,
    toolName: tc.name,
    args: tc.args,
    result: undefined,
  };
}

function backendToThreadMessages(msgs: BackendMessage[]): ThreadMessageLike[] {
  const result: ThreadMessageLike[] = [];

  for (const msg of msgs) {
    if (msg.role === "human") {
      result.push({
        role: "user",
        content: [textPart(msg.content || "")],
      } as unknown as ThreadMessageLike);
    } else if (msg.role === "ai") {
      const content: unknown[] = [];
      if (msg.content) content.push(textPart(msg.content));
      if (msg.tool_calls) {
        for (const tc of msg.tool_calls) content.push(toolCallPart(tc));
      }
      result.push({ role: "assistant", content } as unknown as ThreadMessageLike);
    } else if (msg.role === "tool") {
      for (let i = result.length - 1; i >= 0; i--) {
        const last = result[i];
        if (last.role !== "assistant") continue;
        const parts: unknown[] = Array.isArray(last.content)
          ? [...last.content]
          : [textPart(last.content as string)];
        let found = false;
        for (const part of parts) {
          const p = part as { type: string; toolCallId?: string };
          if (p.type === "tool-call" && p.toolCallId === msg.tool_call_id) {
            (part as Record<string, unknown>).result = msg.content || "";
            found = true;
            break;
          }
        }
        if (found) {
          result[i] = { role: "assistant", content: parts } as unknown as ThreadMessageLike;
          break;
        }
      }
    }
  }

  return result;
}

export function createHistoryAdapter(): ThreadHistoryAdapter {
  return {
    async load() {
      const threadId = getCurrentThreadId();
      if (!threadId) return ExportedMessageRepository.fromArray([]);

      const res = await fetch(
        `${API_BASE}/api/conversations/${encodeURIComponent(threadId)}`,
      );
      if (!res.ok) return ExportedMessageRepository.fromArray([]);
      const data = await res.json();
      const messages = backendToThreadMessages(data.messages || []);
      return ExportedMessageRepository.fromArray(messages);
    },

    async append() {
      // Backend auto-saves via checkpoint
    },
  };
}
