import { Eraser, Menu, PanelLeftClose } from "lucide-react";
import type { ServiceHealthState } from "../../types/health";
import { ServiceStatus } from "./ServiceStatus";

export function AppHeader({
  hasMessages,
  isStreaming,
  health,
  onRefreshHealth,
  onOpenMenu,
  onClear,
}: {
  hasMessages: boolean;
  isStreaming: boolean;
  health: ServiceHealthState;
  onRefreshHealth: () => void;
  onOpenMenu: () => void;
  onClear: () => void;
}) {
  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-ink/10 bg-canvas/90 px-3 backdrop-blur sm:px-5">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={onOpenMenu}
          className="grid h-11 w-11 place-items-center rounded text-ink transition hover:bg-ink/5 md:hidden"
          aria-label="打开导航"
        >
          <Menu className="h-5 w-5" aria-hidden="true" />
        </button>
        <div className="min-w-0">
          <div className="truncate text-sm font-bold">智能数据分析工作台</div>
          <div className="hidden truncate text-xs text-muted sm:block">
            自然语言 → 元数据检索 → 安全 SQL → 真实结果
          </div>
        </div>
      </div>

      <div className="flex items-center gap-1 sm:gap-2">
        <div className="md:hidden">
          <ServiceStatus state={health} onRefresh={onRefreshHealth} compact />
        </div>
        <button
          type="button"
          onClick={onClear}
          disabled={!hasMessages || isStreaming}
          className="grid h-11 w-11 place-items-center rounded text-muted transition hover:bg-ink/5 hover:text-ink disabled:cursor-not-allowed disabled:opacity-30"
          aria-label="清空会话"
          title="清空会话"
        >
          {hasMessages ? (
            <Eraser className="h-[18px] w-[18px]" aria-hidden="true" />
          ) : (
            <PanelLeftClose className="h-[18px] w-[18px]" aria-hidden="true" />
          )}
        </button>
      </div>
    </header>
  );
}
