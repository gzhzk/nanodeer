import type { Conversation, BackendMessage } from "@/lib/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "";

export interface ModelInfo {
  provider: string;
  model: string;
}

export async function fetchModelInfo(): Promise<ModelInfo | null> {
  try {
    const res = await fetch(`${API_BASE}/api/info`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function fetchConversations(): Promise<Conversation[]> {
  const res = await fetch(`${API_BASE}/api/conversations`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.conversations || [];
}

export async function fetchConversation(
  threadId: string,
): Promise<{ title: string; messages: BackendMessage[] } | null> {
  const res = await fetch(
    `${API_BASE}/api/conversations/${encodeURIComponent(threadId)}`,
  );
  if (!res.ok) return null;
  return res.json();
}

export function cancelChat(threadId: string): Promise<Response> {
  return fetch(`${API_BASE}/api/chat/cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId }),
  });
}

export function createChatStream(
  prompt: string,
  threadId: string,
  signal?: AbortSignal,
): Promise<Response> {
  return fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, thread_id: threadId }),
    signal,
  });
}
