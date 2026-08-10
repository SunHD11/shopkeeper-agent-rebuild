export type ProgressStatus = "running" | "success" | "error";

export type ErrorCode =
  | "INVALID_REQUEST"
  | "TOO_MANY_REQUESTS"
  | "LLM_AUTH_FAILED"
  | "LLM_BALANCE_INSUFFICIENT"
  | "LLM_RATE_LIMITED"
  | "LLM_UNAVAILABLE"
  | "RETRIEVAL_FAILED"
  | "SQL_REJECTED"
  | "SQL_VALIDATION_FAILED"
  | "QUERY_TIMEOUT"
  | "SERVICE_UNAVAILABLE"
  | "INTERNAL_ERROR";

export type ProgressEvent = {
  type: "progress";
  step: string;
  status: ProgressStatus;
};

export type ResultEvent = {
  type: "result";
  data: unknown;
};

export type ErrorEvent = {
  type: "error";
  code: ErrorCode;
  message: string;
  request_id: string;
  retryable: boolean;
};

export type AgentEvent = ProgressEvent | ResultEvent | ErrorEvent;

export type StepState = {
  step: string;
  status: ProgressStatus;
  updatedAt: number;
};

export type MessageStatus =
  | "connecting"
  | "streaming"
  | "done"
  | "empty"
  | "error"
  | "stopped";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: number;
  query?: string;
  status?: MessageStatus;
  steps?: StepState[];
  result?: unknown;
  error?: ErrorEvent;
  requestId?: string;
};

export function isErrorEvent(value: unknown): value is ErrorEvent {
  if (!value || typeof value !== "object") return false;
  const event = value as Partial<ErrorEvent>;
  return (
    event.type === "error" &&
    typeof event.code === "string" &&
    typeof event.message === "string" &&
    typeof event.request_id === "string" &&
    typeof event.retryable === "boolean"
  );
}

export function isAgentEvent(value: unknown): value is AgentEvent {
  if (!value || typeof value !== "object") return false;
  const event = value as Record<string, unknown>;

  if (event.type === "progress") {
    return (
      typeof event.step === "string" &&
      ["running", "success", "error"].includes(String(event.status))
    );
  }
  if (event.type === "result") return "data" in event;
  return isErrorEvent(value);
}
