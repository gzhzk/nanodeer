export interface NanoDeerEvent {
  event:
    | "turn_start"
    | "llm_token"
    | "reasoning_token"
    | "assistant_response"
    | "tool_call"
    | "tool_result"
    | "wait"
    | "end"
    | "error"
    | "cancelled";
  threadId: string;
  text?: string;
  name?: string;
  args?: Record<string, unknown>;
  result?: string;
  success?: boolean;
  question?: string;
  message?: string;
  next_action?: string;
  durationMs?: number;
  model?: string;
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
