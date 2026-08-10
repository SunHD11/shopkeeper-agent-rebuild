import { describe, expect, it } from "vitest";
import { normalizeRows, summarizeResult, toCsv } from "./format";

describe("result formatting", () => {
  it("把标量和对象统一为表格行", () => {
    expect(normalizeRows(42)).toEqual([{ 值: 42 }]);
    expect(normalizeRows({ region: "华东" })).toEqual([{ region: "华东" }]);
  });

  it("CSV 会合并不同记录的列并正确转义逗号和双引号", () => {
    expect(
      toCsv([
        { region: "华东,华南", amount: 12 },
        { region: '直营"一部', orders: 3 },
      ]),
    ).toBe('region,amount,orders\r\n"华东,华南",12,\r\n"直营""一部",,3');
  });

  it("空结果拥有明确摘要", () => {
    expect(summarizeResult([])).toBe("查询完成，没有匹配数据。");
  });
});
