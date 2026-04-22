// StreamEvent types for NanoDeer Brain protocol
// These must match the Python side (nanodeer-kernel/src/nanodeer/brain.py)

export type StreamEvent =
  | { event: "turn_start"; threadId: string; turnMs: number }
  | { event: "llm_token"; text: string; threadId: string }
  | { event: "tool_call"; name: string; args: Record<string, unknown>; threadId: string }
  | { event: "tool_result"; name: string; result: string; success: boolean; threadId: string }
  | { event: "wait"; question: string | null; threadId: string }
  | { event: "end"; next_action: string; durationMs: number; threadId: string; message?: string }
  | { event: "error"; code: string; message: string; threadId?: string }
  | { event: "cancelled"; threadId: string }
  | { event: "pong" };

export interface ExecuteRequest {
  type: "execute";
  prompt: string;
  threadId?: string;
  uploadedFiles?: UploadedFile[];
}

export interface ResumeRequest {
  type: "resume";
  threadId: string;
  prompt: string;
}

export interface CancelRequest {
  type: "cancel";
  threadId: string;
}

export interface PingRequest {
  type: "ping";
}

export interface UploadedFile {
  name: string;
  content: string;
  mimeType: string;
}

export type BrainRequest = ExecuteRequest | ResumeRequest | CancelRequest | PingRequest;
