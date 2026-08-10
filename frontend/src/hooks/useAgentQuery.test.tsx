import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AgentEvent } from "../types/agent";
import { useAgentQuery } from "./useAgentQuery";

const streamQueryMock = vi.hoisted(() => vi.fn());

vi.mock("../lib/agentApi", () => ({
  AgentApiError: class AgentApiError extends Error {
    toEvent() {
      return {
        type: "error" as const,
        code: "SERVICE_UNAVAILABLE" as const,
        message: this.message,
        request_id: "client",
        retryable: true,
      };
    }
  },
  streamQuery: streamQueryMock,
}));

beforeEach(() => {
  streamQueryMock.mockReset();
});

describe("useAgentQuery", () => {
  it("把进度与结果归并到同一条 assistant 消息", async () => {
    streamQueryMock.mockImplementation(
      async (...args: unknown[]) => {
        const options = args.find(
          (argument): argument is { onEvent: (event: AgentEvent) => void } =>
            typeof argument === "object" &&
            argument !== null &&
            "onEvent" in argument,
        );
        if (!options) throw new Error("streamQuery 缺少事件回调参数");
        options.onEvent({
          type: "progress",
          step: "生成SQL",
          status: "running",
        });
        options.onEvent({
          type: "progress",
          step: "生成SQL",
          status: "success",
        });
        options.onEvent({ type: "result", data: [{ amount: 128 }] });
        return {
          requestId: "req-hook-1",
          receivedResult: true,
          receivedError: false,
        };
      },
    );
    const { result } = renderHook(() => useAgentQuery());

    await act(async () => {
      expect(await result.current.submit("  查询成交额 ")).toBe(true);
    });

    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[0]).toMatchObject({
      role: "user",
      content: "查询成交额",
    });
    expect(result.current.messages[1]).toMatchObject({
      role: "assistant",
      status: "done",
      result: [{ amount: 128 }],
      steps: [{ step: "生成SQL", status: "success" }],
      requestId: "req-hook-1",
    });
    expect(result.current.completedCount).toBe(1);
    expect(result.current.isStreaming).toBe(false);
  });

  it("缺少 result 终止事件时生成可重试的协议错误", async () => {
    streamQueryMock.mockResolvedValue({
      requestId: "req-no-result",
      receivedResult: false,
      receivedError: false,
    });
    const { result } = renderHook(() => useAgentQuery());

    await act(async () => {
      await result.current.submit("查询库存");
    });

    expect(result.current.messages[1]).toMatchObject({
      status: "error",
      error: {
        code: "INTERNAL_ERROR",
        request_id: "req-no-result",
        retryable: true,
      },
    });
  });
});
