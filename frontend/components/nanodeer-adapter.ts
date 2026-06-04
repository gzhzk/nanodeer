import type { ChatModelAdapter } from "@assistant-ui/react";
import { createChatStream, cancelChat } from "@/lib/api";
import { parseSSEStream } from "@/lib/stream-utils";
import type { NanoDeerEvent, UploadedFilePayload } from "@/lib/types";

const STORAGE_KEY = "nanodeer_thread_id";

// Module-level current threadId for in-session use (not persisted)
// Set during React render phase so history adapter's load() gets the correct thread
let _currentThreadId: string | null = null;

export function getCurrentThreadId(): string | null {
  return _currentThreadId;
}

export function setCurrentThreadId(id: string | null) {
  _currentThreadId = id;
}

export function getSavedThreadId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(STORAGE_KEY);
}

export function saveThreadId(id: string | null) {
  if (typeof window === "undefined") return;
  if (id) {
    localStorage.setItem(STORAGE_KEY, id);
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
}

type ContentPart =
  | { type: "text"; text: string }
  | { type: "reasoning"; text: string; details?: Array<{ type: "text"; text: string }> };

type TextLikeContentPart = {
  text?: string;
};

type ImageContentPart = {
  type: "image";
  image: string;
  filename?: string;
};

function hasText(part: unknown): part is TextLikeContentPart {
  return typeof part === "object" && part !== null && "text" in part;
}

function isImageContentPart(part: unknown): part is ImageContentPart {
  return (
    typeof part === "object" &&
    part !== null &&
    "type" in part &&
    (part as { type?: unknown }).type === "image" &&
    "image" in part &&
    typeof (part as { image?: unknown }).image === "string"
  );
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  const chunkSize = 0x8000;
  let binary = "";
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(i, i + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return btoa(binary);
}

async function fileToUpload(file: File, fallbackName?: string): Promise<UploadedFilePayload> {
  return {
    name: fallbackName || file.name || "upload",
    content: arrayBufferToBase64(await file.arrayBuffer()),
    mime_type: file.type || "application/octet-stream",
    encoding: "base64",
  };
}

function dataUrlToUpload(
  dataUrl: string,
  fallbackName: string,
  fallbackMimeType?: string,
): UploadedFilePayload | null {
  const match = dataUrl.match(/^data:([^;,]+)?;base64,(.*)$/);
  if (!match) return null;
  return {
    name: fallbackName,
    content: match[2] ?? "",
    mime_type: match[1] || fallbackMimeType || "application/octet-stream",
    encoding: "base64",
  };
}

async function extractUploadedFiles(
  attachments: readonly NonNullable<Parameters<ChatModelAdapter["run"]>[0]["messages"][number]["attachments"]>[number][],
): Promise<UploadedFilePayload[]> {
  const uploads: UploadedFilePayload[] = [];

  for (const attachment of attachments) {
    if (attachment.file) {
      uploads.push(await fileToUpload(attachment.file, attachment.name));
      continue;
    }

    const imagePart = attachment.content?.find(isImageContentPart);
    if (!imagePart) continue;

    const upload = dataUrlToUpload(
      imagePart.image,
      imagePart.filename || attachment.name || "image",
      attachment.contentType,
    );
    if (upload) uploads.push(upload);
  }

  return uploads;
}

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
        : lastMessage.content
            .map((part) => (hasText(part) ? part.text ?? "" : ""))
            .join("");

    const threadId = getSavedThreadId() || crypto.randomUUID();
    if (!getSavedThreadId()) saveThreadId(threadId);

    let accumulatedContent = "";
    let accumulatedReasoning = "";
    let hasReasoning = false;

    try {
      const uploadedFiles = await extractUploadedFiles(lastMessage.attachments ?? []);
      const response = await createChatStream(prompt, threadId, uploadedFiles, abortSignal);
      if (!response.ok) {
        throw new Error(`Chat request failed: HTTP ${response.status}`);
      }
      if (!response.body) {
        throw new Error("Chat request failed: empty response body");
      }

      const reader = response.body.getReader();
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
      accumulatedContent += `\n\n❌ **Error:** ${
        err instanceof Error ? err.message : "Connection failed"
      }\n`;
      yield {
        content: buildContent(accumulatedReasoning, accumulatedContent, hasReasoning),
        status: { type: "incomplete" as const, reason: "error" as const },
      };
      return;
    }
  },
};
