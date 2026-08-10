import { BarChart3, DatabaseZap, MessageSquarePlus, Server } from "lucide-react";
import { cn } from "../../lib/format";
import type { ServiceHealthState } from "../../types/health";
import { ServiceStatus } from "./ServiceStatus";

export function AppSidebar({
  examples,
  disabled,
  completedCount,
  health,
  onRefreshHealth,
  onExample,
  onNew,
  className,
}: {
  examples: string[];
  disabled: boolean;
  completedCount: number;
  health: ServiceHealthState;
  onRefreshHealth: () => void;
  onExample: (example: string) => void;
  onNew: () => void;
  className?: string;
}) {
  return (
    <aside
      className={cn(
        "flex min-h-0 flex-col border-r border-ink/10 bg-surface-strong/85 backdrop-blur",
        className,
      )}
      aria-label="问数导航"
    >
      <div className="border-b border-ink/10 px-5 py-5">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded bg-ink text-canvas">
            <BarChart3 className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <div className="font-display text-lg font-bold tracking-wide">电商问数</div>
            <div className="text-xs text-muted">shopkeeper-agent rebuild</div>
          </div>
        </div>
      </div>

      <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <button
          type="button"
          onClick={onNew}
          disabled={disabled}
          className="flex min-h-11 w-full items-center justify-center gap-2 rounded bg-ink px-4 text-sm font-semibold text-canvas transition hover:bg-ink/90 disabled:cursor-not-allowed disabled:opacity-35"
        >
          <MessageSquarePlus className="h-4 w-4" aria-hidden="true" />
          新会话
        </button>

        <section className="mt-6" aria-labelledby="example-heading">
          <div
            id="example-heading"
            className="mb-2 flex items-center gap-2 px-1 text-xs font-bold tracking-[0.14em] text-muted"
          >
            <DatabaseZap className="h-3.5 w-3.5" aria-hidden="true" />
            常用提问
          </div>
          <div className="space-y-2">
            {examples.map((example, index) => (
              <button
                key={example}
                type="button"
                disabled={disabled}
                onClick={() => onExample(example)}
                className="group flex min-h-16 w-full gap-3 rounded border border-ink/10 bg-surface/55 px-3 py-3 text-left text-sm leading-5 text-ink/75 transition hover:border-moss/35 hover:bg-surface disabled:cursor-not-allowed disabled:opacity-45"
              >
                <span className="font-mono text-xs text-brass">0{index + 1}</span>
                <span>{example}</span>
              </button>
            ))}
          </div>
        </section>
      </div>

      <div className="space-y-3 border-t border-ink/10 p-4">
        <ServiceStatus state={health} onRefresh={onRefreshHealth} />
        <div className="flex items-center justify-between text-xs text-muted">
          <span className="inline-flex items-center gap-2">
            <Server className="h-3.5 w-3.5" aria-hidden="true" />
            已完成查询
          </span>
          <span className="font-mono text-ink">{completedCount}</span>
        </div>
      </div>
    </aside>
  );
}
