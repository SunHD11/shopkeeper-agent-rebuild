import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ResultTable } from "./ResultTable";

describe("ResultTable", () => {
  it("渲染列、数值和行列统计", () => {
    render(<ResultTable data={[{ region: "华东", amount: 1200 }]} />);

    expect(screen.getByText("1 行 · 2 列")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "region" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "华东" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "1,200" })).toBeInTheDocument();
  });

  it("复制按钮向剪贴板写入格式化 JSON", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    const data = [{ sku: "A-1" }];
    render(<ResultTable data={data} />);

    await user.click(screen.getByRole("button", { name: /复制 JSON/ }));
    expect(writeText).toHaveBeenCalledWith(JSON.stringify(data, null, 2));
    expect(screen.getByText("已复制")).toBeInTheDocument();
  });

  it("空数组呈现业务空状态而不是空白表格", () => {
    render(<ResultTable data={[]} />);
    expect(screen.getByText("没有匹配数据")).toBeInTheDocument();
  });
});
