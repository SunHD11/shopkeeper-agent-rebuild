import { ArrowUp, Square, WandSparkles } from "lucide-react";
import { type FormEvent, type KeyboardEvent, useEffect, useRef } from "react";

export function Composer({
  value,
  isStreaming,
  onChange,
  onSubmit,
  onStop,
}: {
  value: string;
  isStreaming: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
}) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const canSubmit = value.trim().length > 0 && !isStreaming;

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 144)}px`;
  }, [value]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (canSubmit) onSubmit();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Escape" && isStreaming) {
      event.preventDefault();
      onStop();
      return;
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (canSubmit) onSubmit();
    }
  };

  return (
    <form
      onSubmit={submit}
      className="shrink-0 border-t border-ink/10 bg-canvas/92 px-3 pb-[max(12px,env(safe-area-inset-bottom))] pt-3 backdrop-blur sm:px-5 sm:pb-4"
    >
      <div className="mx-auto flex max-w-5xl items-end gap-2 rounded-panel border border-ink/15 bg-surface p-2 shadow-panel focus-within:border-moss/45">
        <div className="hidden h-11 w-11 shrink-0 place-items-center rounded bg-moss/10 text-moss sm:grid">
          <WandSparkles className="h-5 w-5" aria-hidden="true" />
        </div>
        <label htmlFor="query-composer" className="sr-only">
          输入电商数据问题
        </label>
        <textarea
          id="query-composer"
          ref={textareaRef}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          placeholder="例如：按会员等级统计第一季度订单金额"
          className="scrollbar-thin max-h-36 min-h-11 flex-1 resize-none bg-transparent px-2 py-2.5 text-base leading-6 text-ink outline-none placeholder:text-muted/65"
        />
        <button
          type={isStreaming ? "button" : "submit"}
          onClick={isStreaming ? onStop : undefined}
          disabled={!isStreaming && !canSubmit}
          className="grid h-11 w-11 shrink-0 place-items-center rounded bg-ink text-canvas transition hover:bg-ink/90 disabled:cursor-not-allowed disabled:opacity-25 data-[streaming=true]:bg-tomato"
          data-streaming={isStreaming}
          aria-label={isStreaming ? "停止查询" : "发送问题"}
          title={isStreaming ? "停止查询（Esc）" : "发送问题（Enter）"}
        >
          {isStreaming ? (
            <Square className="h-4 w-4 fill-current" aria-hidden="true" />
          ) : (
            <ArrowUp className="h-5 w-5" aria-hidden="true" />
          )}
        </button>
      </div>
      <p className="mx-auto mt-2 max-w-5xl text-center text-xs text-muted">
        Enter 发送 · Shift+Enter 换行 · Agent 只执行通过安全检查的只读 SQL
      </p>
    </form>
  );
}
