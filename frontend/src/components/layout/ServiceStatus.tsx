import { CheckCircle2, CircleAlert, LoaderCircle, RefreshCw } from "lucide-react";
import { cn } from "../../lib/format";
import type { ServiceHealthState } from "../../types/health";

export function ServiceStatus({
  state,
  onRefresh,
  compact = false,
}: {
  state: ServiceHealthState;
  onRefresh: () => void;
  compact?: boolean;
}) {
  const Icon =
    state.phase === "checking"
      ? LoaderCircle
      : state.phase === "ready"
        ? CheckCircle2
        : CircleAlert;

  return (
    <button
      type="button"
      onClick={onRefresh}
      disabled={state.phase === "checking"}
      className={cn(
        "group flex min-h-11 items-center gap-2 rounded border px-3 text-left transition",
        state.phase === "ready" && "border-moss/20 bg-moss/5 text-moss",
        state.phase === "checking" && "border-brass/20 bg-brass/5 text-brass",
        state.phase === "unavailable" &&
          "border-tomato/25 bg-tomato/5 text-tomato",
        compact && "border-transparent bg-transparent px-2",
      )}
      aria-live="polite"
      title={`${state.message}，点击重新检测`}
    >
      <Icon
        className={cn("h-4 w-4 shrink-0", state.phase === "checking" && "animate-spin")}
        aria-hidden="true"
      />
      {!compact && (
        <span className="min-w-0 flex-1">
          <span className="block text-xs font-semibold">服务状态</span>
          <span className="block truncate text-xs opacity-75">{state.message}</span>
        </span>
      )}
      {!compact && state.phase !== "checking" && (
        <RefreshCw
          className="h-3.5 w-3.5 shrink-0 opacity-45 transition group-hover:rotate-45 group-hover:opacity-100"
          aria-hidden="true"
        />
      )}
      <span className="sr-only">点击重新检测</span>
    </button>
  );
}
