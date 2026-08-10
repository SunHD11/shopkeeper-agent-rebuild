import { Check, ChevronDown, Circle, LoaderCircle, X } from "lucide-react";
import { cn } from "../../lib/format";
import type { ProgressStatus, StepState } from "../../types/agent";

type StageStatus = ProgressStatus | "pending";

interface StageGroup {
  label: string;
  required: string[];
  optional?: string[];
}

const groups: StageGroup[] = [
  { label: "理解问题", required: ["抽取关键词"] },
  {
    label: "并行召回",
    required: ["召回字段信息", "召回指标信息", "召回字段取值"],
  },
  {
    label: "组织上下文",
    required: ["合并召回信息", "过滤指标信息", "过滤表信息", "添加额外上下文"],
  },
  { label: "生成与校验", required: ["生成SQL", "校验SQL"], optional: ["校正SQL"] },
  { label: "执行查询", required: ["执行SQL"] },
];

function stageStatus(
  group: StageGroup,
  statusMap: Map<string, ProgressStatus>,
): StageStatus {
  const names = [...group.required, ...(group.optional ?? [])];
  const statuses = names.map((name) => statusMap.get(name)).filter(Boolean);
  if (statuses.includes("error")) return "error";
  if (statuses.includes("running")) return "running";
  if (group.required.every((name) => statusMap.get(name) === "success")) return "success";
  if (statuses.includes("success")) return "running";
  return "pending";
}

function StepIcon({ status }: { status: StageStatus }) {
  if (status === "running") {
    return <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />;
  }
  if (status === "success") return <Check className="h-4 w-4" aria-hidden="true" />;
  if (status === "error") return <X className="h-4 w-4" aria-hidden="true" />;
  return <Circle className="h-3.5 w-3.5" aria-hidden="true" />;
}

export function ExecutionProgress({ steps = [] }: { steps?: StepState[] }) {
  if (steps.length === 0) return null;
  const statusMap = new Map(steps.map((step) => [step.step, step.status]));

  return (
    <section className="mt-4 rounded-panel border border-ink/10 bg-canvas/55 p-3 sm:p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-bold">执行进度</h3>
        <span className="font-mono text-xs text-muted">LangGraph</span>
      </div>

      <ol className="grid gap-2 sm:grid-cols-5" aria-label="Agent 执行阶段">
        {groups.map((group, index) => {
          const status = stageStatus(group, statusMap);
          return (
            <li key={group.label} className="relative">
              <div
                className={cn(
                  "flex min-h-11 items-center gap-2 rounded border px-2.5 text-xs font-semibold transition",
                  status === "pending" && "border-ink/10 bg-surface/60 text-muted",
                  status === "running" && "border-brass/30 bg-brass/10 text-brass",
                  status === "success" && "border-moss/25 bg-moss/10 text-moss",
                  status === "error" && "border-tomato/30 bg-tomato/10 text-tomato",
                )}
              >
                <span className="font-mono opacity-55">{index + 1}</span>
                <StepIcon status={status} />
                <span>{group.label}</span>
              </div>
            </li>
          );
        })}
      </ol>

      <details className="group mt-3 border-t border-ink/10 pt-3">
        <summary className="flex min-h-8 cursor-pointer list-none items-center gap-2 text-xs font-semibold text-muted hover:text-ink">
          <ChevronDown className="h-4 w-4 transition group-open:rotate-180" aria-hidden="true" />
          查看节点详情（{steps.length}）
        </summary>
        <ol className="mt-2 grid gap-1.5 sm:grid-cols-2">
          {steps.map((step) => (
            <li
              key={step.step}
              className="flex min-h-9 items-center gap-2 rounded bg-surface/70 px-3 text-xs"
            >
              <span
                className={cn(
                  "text-muted",
                  step.status === "running" && "text-brass",
                  step.status === "success" && "text-moss",
                  step.status === "error" && "text-tomato",
                )}
              >
                <StepIcon status={step.status} />
              </span>
              <span>{step.step}</span>
            </li>
          ))}
        </ol>
      </details>
    </section>
  );
}
