import type { RemoteThreadListAdapter } from "@assistant-ui/react";

// Local types — not re-exported from @assistant-ui/react
interface RemoteThreadMetadata {
  readonly status: "regular" | "archived";
  readonly remoteId: string;
  readonly externalId?: string;
  readonly title?: string;
}

interface RemoteThreadListResponse {
  threads: RemoteThreadMetadata[];
  nextCursor?: string;
}

interface RemoteThreadInitializeResponse {
  remoteId: string;
  externalId: string | undefined;
}

interface RemoteThreadListPageOptions {
  after?: string;
}

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "";

async function apiFetch(path: string, options?: RequestInit): Promise<Response> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res;
}

function clearStoredThreadId() {
  if (typeof window !== "undefined") {
    localStorage.removeItem("nanodeer_thread_id");
  }
}

function mapThread(row: {
  thread_id: string;
  title: string | null;
  status: string | null;
}): RemoteThreadMetadata {
  return {
    remoteId: row.thread_id,
    title: row.title || undefined,
    status: row.status === "archived" ? "archived" : "regular",
    externalId: undefined,
  };
}

export const nanodeerThreadListAdapter: RemoteThreadListAdapter = {
  async list(_params?: RemoteThreadListPageOptions): Promise<RemoteThreadListResponse> {
    const res = await apiFetch("/api/conversations");
    const data = await res.json();
    const threads: RemoteThreadMetadata[] = (data.conversations || []).map(mapThread);
    return { threads };
  },

  async rename(remoteId: string, newTitle: string): Promise<void> {
    await apiFetch(`/api/conversations/${encodeURIComponent(remoteId)}/rename`, {
      method: "PATCH",
      body: JSON.stringify({ title: newTitle }),
    });
  },

  async archive(remoteId: string): Promise<void> {
    await apiFetch(`/api/conversations/${encodeURIComponent(remoteId)}/archive`, {
      method: "PATCH",
    });
  },

  async unarchive(remoteId: string): Promise<void> {
    await apiFetch(`/api/conversations/${encodeURIComponent(remoteId)}/unarchive`, {
      method: "PATCH",
    });
  },

  async delete(remoteId: string): Promise<void> {
    await apiFetch(`/api/conversations/${encodeURIComponent(remoteId)}`, {
      method: "DELETE",
    });
  },

  async initialize(threadId: string): Promise<RemoteThreadInitializeResponse> {
    return { remoteId: threadId, externalId: undefined };
  },

  async generateTitle(): Promise<ReadableStream> {
    // Backend generates titles server-side automatically
    return new ReadableStream();
  },

  async fetch(threadId: string): Promise<RemoteThreadMetadata> {
    const res = await fetch(
      `${API_BASE}/api/conversations/${encodeURIComponent(threadId)}/meta`,
    );
    if (res.status === 404) {
      // Stale threadId from localStorage — backend doesn't know about it
      clearStoredThreadId();
      return { remoteId: threadId, status: "regular" };
    }
    if (!res.ok) {
      throw new Error(`API error: ${res.status} ${res.statusText}`);
    }
    const data = await res.json();
    return mapThread(data);
  },
};
