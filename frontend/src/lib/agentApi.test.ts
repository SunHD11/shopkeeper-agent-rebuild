import { afterEach, describe, expect, it, vi } from "vitest";
import { streamQuery } from "./agentApi";

function streamResponse(chunks: string[]) {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  });
  return new Response(body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "X-Request-ID": "req-stream-1",
    },
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("streamQuery", () => {
  it("发送规范请求并按顺序派发流式事件", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      streamResponse([
        'data: {"type":"progress","step":"生成SQL","status":"running"}\n\n',
        'data: {"type":"result","data":[{"gmv":990}]}\n\n',
      ]),
    );
    vi.stubGlobal("fetch", fetchMock);
    const events: unknown[] = [];

    const summary = await streamQuery("  查询 GMV  ", {
      onEvent: (event) => events.push(event),
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/query",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ query: "查询 GMV" }),
      }),
    );
    expect(events).toHaveLength(2);
    expect(summary).toEqual({
      requestId: "req-stream-1",
      receivedResult: true,
      receivedError: false,
    });
  });

  it("把流开始前的结构化 HTTP 错误转换成 AgentApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        Response.json(
          {
            type: "error",
            code: "TOO_MANY_REQUESTS",
            message: "请求太多",
            request_id: "req-limit-1",
            retryable: true,
          },
          { status: 429 },
        ),
      ),
    );

    await expect(streamQuery("查询订单", { onEvent: vi.fn() })).rejects.toMatchObject({
      name: "AgentApiError",
      code: "TOO_MANY_REQUESTS",
      requestId: "req-limit-1",
      retryable: true,
      status: 429,
    });
  });
});
