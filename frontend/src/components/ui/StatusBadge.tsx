import { Check, CircleAlert, LoaderCircle, Square } from "lucide-react";
import { cn } from "../../lib/format";
import type { MessageStatus } from "../../types/agent";

const labels: Record<MessageStatus, string> = {
  connecting: "连接中",
  streaming: "执行中",
  done: "已完成",
  empty: "无数据",
  error: "未完成",
  stopped: "已停止",
};

export function StatusBadge({ status }: { status: MessageStatus }) {
  const Icon =
    status === "connecting" || status === "streaming"
      ? LoaderCircle
      : status === "done"
        ? Check
        : status === "stopped"
          ? Square
          : CircleAlert;

  return (
    <span
      className={cn(
        "inline-flex min-h-7 items-center gap-1.5 rounded px-2 text-xs font-semibold",
        (status === "connecting" || status === "streaming") &&
          "bg-brass/10 text-brass",
        status === "done" && "bg-moss/10 text-moss",
        status === "empty" && "bg-info/10 text-info",
        status === "error" && "bg-tomato/10 text-tomato",
        status === "stopped" && "bg-ink/5 text-muted",
      )}
    >
      <Icon
        className={cn(
          "h-3.5 w-3.5",
          (status === "connecting" || status === "streaming") && "animate-spin",
        )}
        aria-hidden="true"
      />
      {labels[status]}
    </span>
  );
}
