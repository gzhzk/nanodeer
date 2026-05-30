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
