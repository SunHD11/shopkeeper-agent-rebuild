import { describe, expect, it } from "vitest";
import { SseDecoder, parseSseEvent } from "./sse";

describe("SseDecoder", () => {
  it("把跨网络分块的事件重新拼成完整事件", () => {
    const decoder = new SseDecoder();

    expect(decoder.push('data: {"type":"progress","step":"生成')).toEqual([]);
    expect(decoder.push('SQL","status":"running"}\n\n')).toEqual([
      { type: "progress", step: "生成SQL", status: "running" },
    ]);
  });

  it("一次网络分块可以解析多条 CRLF 事件", () => {
    const decoder = new SseDecoder();
    const events = decoder.push(
      'data: {"type":"progress","step":"执行SQL","status":"success"}\r\n\r\n' +
        'data: {"type":"result","data":[{"amount":120}]}\r\n\r\n',
    );

    expect(events).toHaveLength(2);
    expect(events[1]).toEqual({ type: "result", data: [{ amount: 120 }] });
  });

  it("畸形 JSON 不会炸掉页面，而是转成可展示错误", () => {
    expect(parseSseEvent("data: {broken-json")).toMatchObject({
      type: "error",
      code: "INTERNAL_ERROR",
      request_id: "client",
    });
  });

  it("连接关闭时 flush 会处理没有空行结尾的最后一条事件", () => {
    const decoder = new SseDecoder();
    decoder.push('data: {"type":"result","data":[]}');

    expect(decoder.flush()).toEqual([{ type: "result", data: [] }]);
  });
});
