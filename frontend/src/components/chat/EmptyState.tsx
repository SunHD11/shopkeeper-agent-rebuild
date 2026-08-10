import { ArrowUpRight, Braces, Search, ShieldCheck } from "lucide-react";

export function EmptyState({
  examples,
  onUseExample,
}: {
  examples: string[];
  onUseExample: (example: string) => void;
}) {
  return (
    <div className="mx-auto flex min-h-full w-full max-w-5xl flex-col justify-center px-4 py-10 sm:px-8 sm:py-16">
      <div className="max-w-3xl">
        <div className="mb-5 inline-flex items-center gap-2 border-b border-moss/35 pb-1 text-sm font-bold text-moss">
          <span className="h-2 w-2 bg-moss" aria-hidden="true" />
          Shopkeeper Agent Rebuild
        </div>
        <h1 className="font-display text-4xl font-bold leading-[1.12] tracking-tight text-ink sm:text-6xl">
          把经营问题，
          <span className="text-moss">问成可信数据。</span>
        </h1>
        <p className="mt-5 max-w-2xl text-base leading-8 text-muted sm:text-lg">
          Agent 会检索字段、指标和真实取值，生成只读 SQL，通过数据库校验后返回结果。
          你能看到每一步，而不是等一个神秘的加载圈自行参悟人生。
        </p>
      </div>

      <div className="mt-8 flex flex-wrap gap-x-5 gap-y-2 border-y border-ink/10 py-3 text-xs font-semibold text-muted">
        <span className="inline-flex items-center gap-2">
          <Search className="h-4 w-4 text-brass" aria-hidden="true" />
          三路元数据召回
        </span>
        <span className="inline-flex items-center gap-2">
          <Braces className="h-4 w-4 text-info" aria-hidden="true" />
          SQL 自动校验
        </span>
        <span className="inline-flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-moss" aria-hidden="true" />
          只读安全边界
        </span>
      </div>

      <section className="mt-8" aria-labelledby="starter-heading">
        <div className="mb-3 flex items-end justify-between gap-4">
          <div>
            <p className="font-mono text-xs text-brass">START HERE</p>
            <h2 id="starter-heading" className="mt-1 text-lg font-bold">
              试一个真实经营问题
            </h2>
          </div>
          <p className="hidden text-xs text-muted sm:block">点击后立即开始查询</p>
        </div>
        <div className="grid border-l border-t border-ink/10 sm:grid-cols-2">
          {examples.map((example, index) => (
            <button
              key={example}
              type="button"
              onClick={() => onUseExample(example)}
              className="group flex min-h-24 items-start gap-4 border-b border-r border-ink/10 bg-surface/55 p-4 text-left transition hover:bg-surface focus:z-10 sm:p-5"
            >
              <span className="font-mono text-xs text-brass">0{index + 1}</span>
              <span className="flex-1 text-sm font-medium leading-6 sm:text-base">
                {example}
              </span>
              <ArrowUpRight
                className="h-4 w-4 shrink-0 text-muted transition group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-moss"
                aria-hidden="true"
              />
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
