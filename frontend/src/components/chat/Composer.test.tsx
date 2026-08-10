import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Composer } from "./Composer";

describe("Composer", () => {
  it("Enter 发送，Shift+Enter 保留为换行", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    const onChange = vi.fn();
    const { rerender } = render(
      <Composer
        value="查询订单"
        isStreaming={false}
        onChange={onChange}
        onSubmit={onSubmit}
        onStop={vi.fn()}
      />,
    );
    const textbox = screen.getByRole("textbox", { name: "输入电商数据问题" });

    await user.type(textbox, "{shift>}{enter}{/shift}");
    expect(onSubmit).not.toHaveBeenCalled();

    rerender(
      <Composer
        value="查询订单"
        isStreaming={false}
        onChange={onChange}
        onSubmit={onSubmit}
        onStop={vi.fn()}
      />,
    );
    await user.type(textbox, "{enter}");
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it("流式执行期间按钮和 Esc 都用于停止", async () => {
    const user = userEvent.setup();
    const onStop = vi.fn();
    render(
      <Composer
        value=""
        isStreaming
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={onStop}
      />,
    );

    await user.click(screen.getByRole("button", { name: "停止查询" }));
    await user.type(screen.getByRole("textbox"), "{escape}");
    expect(onStop).toHaveBeenCalledTimes(2);
  });
});
