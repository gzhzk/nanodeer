export interface NanoDeerEvent {
  event:
    | "turn_start"
    | "context_loaded"
    | "memory_context"
    | "plan_context"
    | "sandbox_acquired"
    | "sandbox_released"
    | "llm_start"
    | "llm_retry"
    | "llm_end"
    | "llm_token"
    | "reasoning_token"
    | "assistant_response"
    | "tool_call"
    | "tool_blocked"
    | "tool_result"
    | "checkpoint_saved"
    | "context_absorbed"
    | "wait"
    | "end"
    | "error"
    | "cancelled";
  threadId: string;
  schema_version?: string;
  ts_ms?: number;
  type?: string;
  turn?: number;
  text?: string;
  name?: string;
  args?: Record<string, unknown>;
  args_preview?: Record<string, unknown>;
  result?: string;
  success?: boolean;
  question?: string;
  message?: string;
  next_action?: string;
  durationMs?: number;
  duration_ms?: number;
  model?: string;
  usage?: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
}

export interface Conversation {
  thread_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ToolCallData {
  name: string;
  args: Record<string, unknown>;
  id: string | null;
}

export interface BackendMessage {
  content: string;
  role: "human" | "ai" | "tool" | "system";
  id?: string;
  tool_calls?: ToolCallData[];
  tool_call_id?: string;
  name?: string;
}

export interface UploadedFilePayload {
  name: string;
  content: string;
  mime_type: string;
  encoding: "base64";
}

export interface WorkspaceSummary {
  projects: {
    count: number;
    items: WorkspaceWikiEntry[];
  };
  plans: {
    count: number;
    active: number;
    items: WorkspacePlan[];
  };
  memory: {
    count: number;
    has_user: boolean;
    has_memory: boolean;
    episodic_days: number;
  };
  wiki: {
    count: number;
    items: WorkspaceWikiEntry[];
  };
}

export interface WorkspaceWikiEntry {
  path: string;
  title: string;
  summary: string;
  tags: string[];
  updated_at: string;
}

export interface WorkspacePlan {
  plan_id: string;
  goal: string;
  title: string;
  status: string;
  steps: Array<{
    id: string;
    content: string;
    status: string;
  }>;
}
