import { useCallback, useMemo, useRef, useState } from "react";
import { AgentApiError, streamQuery } from "../lib/agentApi";
import { normalizeRows, summarizeResult } from "../lib/format";
import type { AgentEvent, ChatMessage, ErrorEvent, StepState } from "../types/agent";

function makeId() {
  return crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function upsertStep(steps: StepState[] = [], event: Extract<AgentEvent, { type: "progress" }>) {
  const index = steps.findIndex((item) => item.step === event.step);
  const nextStep: StepState = {
    step: event.step,
    status: event.status,
    updatedAt: Date.now(),
  };
  if (index === -1) return [...steps, nextStep];
  return steps.map((item, currentIndex) => (currentIndex === index ? nextStep : item));
}

function connectionError(error: unknown): ErrorEvent {
  if (error instanceof AgentApiError) return error.toEvent();
  return {
    type: "error",
    code: "SERVICE_UNAVAILABLE",
    message: error instanceof Error ? error.message : "无法连接问数接口。",
    request_id: "client",
    retryable: true,
  };
}

export function useAgentQuery() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);

  const updateAssistant = useCallback(
    (assistantId: string, updater: (message: ChatMessage) => ChatMessage) => {
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId ? updater(message) : message,
        ),
      );
    },
    [],
  );

  const submit = useCallback(
    async (rawQuery: string) => {
      const query = rawQuery.trim();
      if (!query || controllerRef.current) return false;

      const userMessage: ChatMessage = {
        id: makeId(),
        role: "user",
        content: query,
        query,
        createdAt: Date.now(),
      };
      const assistantId = makeId();
      const assistantMessage: ChatMessage = {
        id: assistantId,
        role: "assistant",
        query,
        content: "正在连接问数智能体…",
        createdAt: Date.now(),
        status: "connecting",
        steps: [],
      };
      const controller = new AbortController();
      controllerRef.current = controller;
      setIsStreaming(true);
      setMessages((current) => [...current, userMessage, assistantMessage]);

      const onEvent = (event: AgentEvent) => {
        updateAssistant(assistantId, (message) => {
          if (event.type === "progress") {
            return {
              ...message,
              status: event.status === "error" ? "error" : "streaming",
              content:
                event.status === "running" ? `正在执行：${event.step}` : message.content,
              steps: upsertStep(message.steps, event),
            };
          }
          if (event.type === "result") {
            const empty = normalizeRows(event.data).length === 0;
            return {
              ...message,
              status: empty ? "empty" : "done",
              content: summarizeResult(event.data),
              result: event.data,
            };
          }
          return {
            ...message,
            status: "error",
            content: event.message,
            error: event,
            requestId: event.request_id,
          };
        });
      };

      try {
        const summary = await streamQuery(query, {
          signal: controller.signal,
          onEvent,
        });
        updateAssistant(assistantId, (message) => {
          if (message.status !== "connecting" && message.status !== "streaming") {
            return { ...message, requestId: message.requestId ?? summary.requestId ?? undefined };
          }
          const error: ErrorEvent = {
            type: "error",
            code: "INTERNAL_ERROR",
            message: "流程已经结束，但后端没有返回查询结果。",
            request_id: summary.requestId ?? "unknown",
            retryable: true,
          };
          return {
            ...message,
            status: "error",
            content: error.message,
            error,
            requestId: error.request_id,
          };
        });
      } catch (error) {
        const aborted = error instanceof DOMException && error.name === "AbortError";
        updateAssistant(assistantId, (message) => {
          if (aborted) {
            return {
              ...message,
              status: "stopped",
              content: "已停止本次查询，已有执行进度会保留在这里。",
            };
          }
          const apiError = connectionError(error);
          return {
            ...message,
            status: "error",
            content: apiError.message,
            error: apiError,
            requestId: apiError.request_id,
          };
        });
      } finally {
        if (controllerRef.current === controller) {
          controllerRef.current = null;
          setIsStreaming(false);
        }
      }
      return true;
    },
    [updateAssistant],
  );

  const stop = useCallback(() => controllerRef.current?.abort(), []);

  const clear = useCallback(() => {
    if (controllerRef.current) return;
    setMessages([]);
  }, []);

  const completedCount = useMemo(
    () =>
      messages.filter(
        (message) =>
          message.role === "assistant" &&
          (message.status === "done" || message.status === "empty"),
      ).length,
    [messages],
  );

  return {
    messages,
    isStreaming,
    completedCount,
    submit,
    retry: submit,
    stop,
    clear,
  };
}
