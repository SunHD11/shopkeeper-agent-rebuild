import { Check, Clipboard, Database, Download, Rows3 } from "lucide-react";
import { useState } from "react";
import { cn, formatCell, normalizeRows, toClipboardText, toCsv } from "../../lib/format";

export function ResultTable({ data }: { data: unknown }) {
  const [copied, setCopied] = useState(false);
  const rows = normalizeRows(data);
  const columns = Array.from(
    rows.reduce((keys, row) => {
      Object.keys(row).forEach((key) => keys.add(key));
      return keys;
    }, new Set<string>()),
  );

  if (rows.length === 0 || columns.length === 0) {
    return (
      <section className="mt-4 rounded-panel border border-info/20 bg-info/5 px-4 py-5">
        <h3 className="font-semibold text-info">没有匹配数据</h3>
        <p className="mt-1 text-sm leading-6 text-muted">
          查询已经成功执行，可以尝试放宽时间、地区或商品范围。
        </p>
      </section>
    );
  }

  const copy = async () => {
    await navigator.clipboard.writeText(toClipboardText(data));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  };

  const downloadCsv = () => {
    const blob = new Blob(["\uFEFF", toCsv(data)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `shopkeeper-result-${Date.now()}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="mt-4 overflow-hidden rounded-panel border border-ink/10 bg-surface shadow-line">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink/10 px-3 py-3 sm:px-4">
        <div>
          <div className="flex items-center gap-2 text-sm font-bold">
            <Database className="h-4 w-4 text-moss" aria-hidden="true" />
            查询结果
          </div>
          <div className="mt-1 flex items-center gap-1.5 text-xs text-muted">
            <Rows3 className="h-3.5 w-3.5" aria-hidden="true" />
            {rows.length} 行 · {columns.length} 列
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={copy}
            className="inline-flex min-h-11 items-center gap-2 rounded px-3 text-xs font-semibold text-muted transition hover:bg-ink/5 hover:text-ink"
          >
            {copied ? <Check className="h-4 w-4 text-moss" /> : <Clipboard className="h-4 w-4" />}
            {copied ? "已复制" : "复制 JSON"}
          </button>
          <button
            type="button"
            onClick={downloadCsv}
            className="inline-flex min-h-11 items-center gap-2 rounded px-3 text-xs font-semibold text-muted transition hover:bg-ink/5 hover:text-ink"
          >
            <Download className="h-4 w-4" aria-hidden="true" />
            导出 CSV
          </button>
        </div>
      </div>

      <div className="scrollbar-thin max-h-[420px] overflow-auto" tabIndex={0}>
        <table className="min-w-full border-separate border-spacing-0 text-left text-sm">
          <caption className="sr-only">自然语言问数查询结果</caption>
          <thead className="sticky top-0 z-10 bg-surface-strong">
            <tr>
              {columns.map((column) => (
                <th
                  key={column}
                  scope="col"
                  className="whitespace-nowrap border-b border-ink/10 px-4 py-3 font-semibold text-ink/75"
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex} className="odd:bg-surface even:bg-canvas/35 hover:bg-moss/5">
                {columns.map((column) => {
                  const value = row[column];
                  const rendered = formatCell(value);
                  return (
                    <td
                      key={column}
                      className={cn(
                        "max-w-[360px] border-b border-ink/5 px-4 py-3 text-ink/80",
                        typeof value === "number" &&
                          "text-right font-mono tabular-nums text-ink",
                      )}
                      title={rendered}
                    >
                      <span className="block truncate">{rendered}</span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="border-t border-ink/5 px-4 py-2 text-xs text-muted sm:hidden">
        表格可以左右滑动查看完整字段
      </p>
    </section>
  );
}
