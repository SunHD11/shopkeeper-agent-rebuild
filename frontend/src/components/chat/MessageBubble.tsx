import { Bot, Check, Copy, UserRound } from "lucide-react";
import { useState } from "react";
import { cn, formatTime, toClipboardText } from "../../lib/format";
import type { ChatMessage } from "../../types/agent";
import { ExecutionProgress } from "../query/ExecutionProgress";
import { QueryError } from "../query/QueryError";
import { ResultTable } from "../query/ResultTable";
import { StatusBadge } from "../ui/StatusBadge";

export function MessageBubble({
  message,
  onRetry,
}: {
  message: ChatMessage;
  onRetry: (query: string) => void;
}) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";

  const copy = async () => {
    await navigator.clipboard.writeText(
      message.result === undefined ? message.content : toClipboardText(message.result),
    );
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  };

  if (isUser) {
    return (
      <article className="flex justify-end gap-3">
        <div className="max-w-[min(760px,88%)] rounded-panel bg-ink px-4 py-3 text-canvas shadow-line sm:px-5 sm:py-4">
          <p className="whitespace-pre-wrap text-base leading-7">{message.content}</p>
          <div className="mt-2 text-right text-xs text-canvas/55">
            {formatTime(message.createdAt)}
          </div>
        </div>
        <div className="mt-1 hidden h-9 w-9 shrink-0 place-items-center rounded-full bg-moss text-white sm:grid">
          <UserRound className="h-4 w-4" aria-hidden="true" />
        </div>
      </article>
    );
  }

  return (
    <article className="group flex gap-3">
      <div className="mt-1 hidden h-9 w-9 shrink-0 place-items-center rounded-full bg-ink text-canvas sm:grid">
        <Bot className="h-4 w-4" aria-hidden="true" />
      </div>
      <div className="min-w-0 flex-1 rounded-panel border border-ink/10 bg-surface/85 p-4 shadow-line backdrop-blur sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-ink/8 pb-3">
          <div>
            <div className="text-xs font-bold tracking-[0.12em] text-muted">AGENT RESPONSE</div>
            <p className="mt-1 text-base font-medium leading-7">{message.content}</p>
          </div>
          <div className="flex items-center gap-1">
            {message.status && <StatusBadge status={message.status} />}
            {message.status !== "connecting" && message.status !== "streaming" && (
              <button
                type="button"
                onClick={copy}
                className="grid h-9 w-9 place-items-center rounded text-muted transition hover:bg-ink/5 hover:text-ink"
                aria-label="复制回复"
                title="复制回复"
              >
                {copied ? (
                  <Check className="h-4 w-4 text-moss" aria-hidden="true" />
                ) : (
                  <Copy className="h-4 w-4" aria-hidden="true" />
                )}
              </button>
            )}
          </div>
        </div>

        <ExecutionProgress steps={message.steps} />
        {message.error && (
          <QueryError error={message.error} onRetry={() => onRetry(message.query ?? "")} />
        )}
        {message.result !== undefined && <ResultTable data={message.result} />}

        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
          <span>{formatTime(message.createdAt)}</span>
          {message.requestId && (
            <span className="max-w-full truncate font-mono" title={message.requestId}>
              request_id: {message.requestId}
            </span>
          )}
        </div>
      </div>
    </article>
  );
}
