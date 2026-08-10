import { SseDecoder } from "./sse";
import type { AgentEvent, ErrorCode, ErrorEvent } from "../types/agent";
import { isErrorEvent } from "../types/agent";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "";

export type QueryOptions = {
  signal?: AbortSignal;
  onEvent: (event: AgentEvent) => void;
};

export type QueryStreamSummary = {
  requestId: string | null;
  receivedResult: boolean;
  receivedError: boolean;
};

export class AgentApiError extends Error {
  readonly code: ErrorCode;
  readonly requestId: string;
  readonly retryable: boolean;
  readonly status: number;

  constructor(event: ErrorEvent, status: number) {
    super(event.message);
    this.name = "AgentApiError";
    this.code = event.code;
    this.requestId = event.request_id;
    this.retryable = event.retryable;
    this.status = status;
  }

  toEvent(): ErrorEvent {
    return {
      type: "error",
      code: this.code,
      message: this.message,
      request_id: this.requestId,
      retryable: this.retryable,
    };
  }
}

function fallbackCode(status: number): ErrorCode {
  if (status === 429) return "TOO_MANY_REQUESTS";
  if (status === 422 || status === 400) return "INVALID_REQUEST";
  if (status === 503) return "SERVICE_UNAVAILABLE";
  if (status === 504) return "QUERY_TIMEOUT";
  return "INTERNAL_ERROR";
}

async function toApiError(response: Response): Promise<AgentApiError> {
  const requestId = response.headers.get("X-Request-ID") ?? "unknown";
  try {
    const payload: unknown = await response.json();
    if (isErrorEvent(payload)) return new AgentApiError(payload, response.status);
  } catch {
    // 非 JSON 错误页（例如代理返回 HTML）会落到统一安全文案。
  }

  return new AgentApiError(
    {
      type: "error",
      code: fallbackCode(response.status),
      message:
        response.status === 429
          ? "当前问数请求较多，请稍后重试"
          : `问数接口暂时不可用（HTTP ${response.status}）`,
      request_id: requestId,
      retryable: response.status === 429 || response.status >= 500,
    },
    response.status,
  );
}

export async function streamQuery(
  query: string,
  options: QueryOptions,
): Promise<QueryStreamSummary> {
  const response = await fetch(`${API_BASE_URL}/api/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ query: query.trim() }),
    signal: options.signal,
  });

  if (!response.ok) throw await toApiError(response);
  if (!response.body) {
    throw new AgentApiError(
      {
        type: "error",
        code: "SERVICE_UNAVAILABLE",
        message: "浏览器未收到可读取的流式响应。",
        request_id: response.headers.get("X-Request-ID") ?? "unknown",
        retryable: true,
      },
      response.status,
    );
  }

  const reader = response.body.getReader();
  const textDecoder = new TextDecoder("utf-8");
  const sseDecoder = new SseDecoder();
  let receivedResult = false;
  let receivedError = false;

  const dispatch = (events: AgentEvent[]) => {
    for (const event of events) {
      if (event.type === "result") receivedResult = true;
      if (event.type === "error") receivedError = true;
      options.onEvent(event);
    }
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      dispatch(sseDecoder.push(textDecoder.decode(value, { stream: true })));
    }
    dispatch(sseDecoder.push(textDecoder.decode()));
    dispatch(sseDecoder.flush());
  } finally {
    reader.releaseLock();
  }

  return {
    requestId: response.headers.get("X-Request-ID"),
    receivedResult,
    receivedError,
  };
}
