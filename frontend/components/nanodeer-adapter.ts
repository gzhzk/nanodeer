import type { ChatModelAdapter } from "@assistant-ui/react";
import { createChatStream, cancelChat } from "@/lib/api";
import { parseSSEStream } from "@/lib/stream-utils";
import type { NanoDeerEvent } from "@/lib/types";

let currentThreadId: string | null = null;

export function setThreadId(id: string | null) {
  currentThreadId = id;
}

export function getThreadId(): string | null {
  return currentThreadId;
}

type ContentPart =
  | { type: "text"; text: string }
  | { type: "reasoning"; text: string; details?: Array<{ type: "text"; text: string }> };

function buildContent(
  accumulatedReasoning: string,
  accumulatedContent: string,
  hasReasoning: boolean,
): ContentPart[] {
  const parts: ContentPart[] = [];
  if (hasReasoning && accumulatedReasoning) {
    parts.push({ type: "reasoning", text: accumulatedReasoning });
  }
  if (accumulatedContent) {
    parts.push({ type: "text", text: accumulatedContent });
  }
  if (parts.length === 0) {
    parts.push({ type: "text", text: "" });
  }
  return parts;
}

export const nanodeerAdapter: ChatModelAdapter = {
  async *run({ messages, abortSignal }) {
    const lastMessage = messages[messages.length - 1];
    if (!lastMessage) return;

    const prompt =
      typeof lastMessage.content === "string"
        ? lastMessage.content
        : lastMessage.content.map((c: any) => c.text ?? "").join("");

    const threadId = currentThreadId || crypto.randomUUID();
    if (!currentThreadId) currentThreadId = threadId;

    const response = await createChatStream(prompt, threadId, abortSignal);
    const reader = response.body!.getReader();

    let accumulatedContent = "";
    let accumulatedReasoning = "";
    let hasReasoning = false;

    try {
      for await (const sse of parseSSEStream(reader, abortSignal)) {
        const ev = sse.data as unknown as NanoDeerEvent;

        switch (ev.event) {
          case "turn_start":
            break;
          case "reasoning_token": {
            hasReasoning = true;
            accumulatedReasoning += ev.text || "";
            yield {
              content: buildContent(accumulatedReasoning, accumulatedContent, hasReasoning),
            };
            break;
          }
          case "llm_token": {
            accumulatedContent += ev.text || "";
            yield {
              content: buildContent(accumulatedReasoning, accumulatedContent, hasReasoning),
            };
            break;
          }
          case "tool_call": {
            const block = `\n\n**🔧 ${ev.name}**\n\`\`\`json\n${JSON.stringify(ev.args, null, 2)}\n\`\`\`\n`;
            accumulatedContent += block;
            yield {
              content: buildContent(accumulatedReasoning, accumulatedContent, hasReasoning),
            };
            break;
          }
          case "tool_result": {
            const icon = ev.success !== false ? "✅" : "❌";
            const truncated = (ev.result || "").slice(0, 1500);
            const block = `${icon} **${ev.name}** — result:\n\`\`\`\n${truncated}\n\`\`\`\n`;
            accumulatedContent += block;
            yield {
              content: buildContent(accumulatedReasoning, accumulatedContent, hasReasoning),
            };
            break;
          }
          case "wait": {
            accumulatedContent += `\n\n⏸️ ${ev.question || ""}\n`;
            yield {
              content: buildContent(accumulatedReasoning, accumulatedContent, hasReasoning),
              status: { type: "incomplete" as const, reason: "other" as const },
            };
            return;
          }
          case "error": {
            accumulatedContent += `\n\n❌ **Error:** ${ev.message || "Unknown error"}\n`;
            yield {
              content: buildContent(accumulatedReasoning, accumulatedContent, hasReasoning),
              status: { type: "incomplete" as const, reason: "error" as const },
            };
            return;
          }
          case "cancelled": {
            accumulatedContent += "\n\n_Cancelled._\n";
            yield {
              content: buildContent(accumulatedReasoning, accumulatedContent, hasReasoning),
              status: { type: "incomplete" as const, reason: "cancelled" as const },
            };
            return;
          }
          case "end":
            return;
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") {
        if (threadId) cancelChat(threadId).catch(() => {});
        yield {
          content: buildContent(accumulatedReasoning, accumulatedContent, hasReasoning),
          status: { type: "incomplete" as const, reason: "cancelled" as const },
        };
        return;
      }
      throw err;
    }
  },
};
