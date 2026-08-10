import type { AgentEvent, ErrorEvent } from "../types/agent";
import { isAgentEvent } from "../types/agent";

function clientParseError(detail: string): ErrorEvent {
  return {
    type: "error",
    code: "INTERNAL_ERROR",
    message: detail,
    request_id: "client",
    retryable: false,
  };
}

export function parseSseEvent(chunk: string): AgentEvent | null {
  const payload = chunk
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.replace(/^data:\s?/, ""))
    .join("\n")
    .trim();

  if (!payload) return null;

  try {
    const parsed: unknown = JSON.parse(payload);
    if (!isAgentEvent(parsed)) {
      return clientParseError("后端返回了无法识别的事件结构。");
    }
    return parsed;
  } catch {
    return clientParseError("后端返回了无法解析的流式事件。");
  }
}

/**
 * 增量 SSE 解码器。
 *
 * fetch() 返回的数据块与 SSE 事件边界没有必然关系：半条 JSON 可能被拆成两块，
 * 也可能一块里塞进三条事件。解码器保留未完成尾部，只输出完整事件。
 */
export class SseDecoder {
  private buffer = "";

  push(text: string): AgentEvent[] {
    this.buffer += text;
    const events: AgentEvent[] = [];

    while (true) {
      const boundary = this.buffer.match(/\r?\n\r?\n/);
      if (!boundary || boundary.index === undefined) break;

      const chunk = this.buffer.slice(0, boundary.index);
      this.buffer = this.buffer.slice(boundary.index + boundary[0].length);
      const event = parseSseEvent(chunk);
      if (event) events.push(event);
    }

    return events;
  }

  flush(): AgentEvent[] {
    const tail = this.buffer.trim();
    this.buffer = "";
    if (!tail) return [];
    const event = parseSseEvent(tail);
    return event ? [event] : [];
  }
}
