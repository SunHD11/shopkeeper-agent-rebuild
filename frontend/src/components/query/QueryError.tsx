import { RefreshCw, ShieldAlert } from "lucide-react";
import type { ErrorEvent } from "../../types/agent";

export function QueryError({ error, onRetry }: { error: ErrorEvent; onRetry: () => void }) {
  return (
    <section
      className="mt-4 rounded-panel border border-tomato/25 bg-tomato/5 p-4"
      aria-label="查询错误"
    >
      <div className="flex items-start gap-3">
        <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-tomato" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-tomato">查询未完成</h3>
          <p className="mt-1 text-sm leading-6 text-ink/80">{error.message}</p>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 font-mono text-xs text-muted">
            <span>{error.code}</span>
            <span className="max-w-full truncate" title={error.request_id}>
              request_id: {error.request_id}
            </span>
          </div>
          {error.retryable && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-4 inline-flex min-h-11 items-center gap-2 rounded bg-ink px-4 text-sm font-semibold text-canvas transition hover:bg-ink/90"
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              重试这次查询
            </button>
          )}
        </div>
      </div>
    </section>
  );
}
