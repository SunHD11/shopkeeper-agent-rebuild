import { expect, test } from "@playwright/test";

const query = "按会员等级统计第一季度订单金额";

test.beforeEach(async ({ page }) => {
  await page.route("**/health/ready", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "ok",
        checks: {
          meta_mysql: { status: "up", latency_ms: 3, detail: null },
          dw_mysql: { status: "up", latency_ms: 4, detail: null },
          qdrant: { status: "up", latency_ms: 7, detail: null },
          elasticsearch: { status: "up", latency_ms: 9, detail: null },
          embedding: { status: "up", latency_ms: 12, detail: null },
        },
      }),
    });
  });

  await page.route("**/api/query", async (route) => {
    const payload = route.request().postDataJSON() as { query: string };
    expect(payload.query).toBe(query);
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream; charset=utf-8",
      headers: { "X-Request-ID": "req-e2e-001" },
      body: [
        'data: {"type":"progress","step":"抽取关键词","status":"success"}\n\n',
        'data: {"type":"progress","step":"召回字段信息","status":"success"}\n\n',
        'data: {"type":"progress","step":"召回指标信息","status":"success"}\n\n',
        'data: {"type":"progress","step":"召回字段取值","status":"success"}\n\n',
        'data: {"type":"progress","step":"合并召回信息","status":"success"}\n\n',
        'data: {"type":"progress","step":"过滤指标信息","status":"success"}\n\n',
        'data: {"type":"progress","step":"过滤表信息","status":"success"}\n\n',
        'data: {"type":"progress","step":"添加额外上下文","status":"success"}\n\n',
        'data: {"type":"progress","step":"生成SQL","status":"success"}\n\n',
        'data: {"type":"progress","step":"校验SQL","status":"success"}\n\n',
        'data: {"type":"progress","step":"执行SQL","status":"success"}\n\n',
        'data: {"type":"result","data":[{"会员等级":"黄金会员","订单金额":168320.5},{"会员等级":"白银会员","订单金额":92780}]}\n\n',
      ].join(""),
    });
  });
});

test("用户提问后可以看到执行阶段、表格结果与请求 ID", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByText("把经营问题，")).toBeVisible();

  const composer = page.getByRole("textbox", { name: "输入电商数据问题" });
  await composer.fill(query);
  await composer.press("Enter");

  await expect(page.getByText("查询完成，共 2 行结果。")).toBeVisible();
  await expect(page.getByText("2 行 · 2 列")).toBeVisible();
  await expect(page.getByRole("cell", { name: "黄金会员" })).toBeVisible();
  await expect(page.getByText("request_id: req-e2e-001")).toBeVisible();
  await expect(page.getByRole("list", { name: "Agent 执行阶段" })).toBeVisible();

  await page.screenshot({
    path: testInfo.outputPath("query-result.png"),
    fullPage: true,
  });
});

test("移动端导航可以打开和关闭", async ({ page, isMobile }) => {
  test.skip(!isMobile, "只在移动视口验证抽屉导航");
  await page.goto("/");

  await page.getByRole("button", { name: "打开导航" }).click();
  await expect(page.getByRole("complementary", { name: "问数导航" })).toBeVisible();
  await page.getByRole("button", { name: "关闭导航" }).click({ position: { x: 360, y: 20 } });
  await expect(page.getByRole("complementary", { name: "问数导航" })).toBeHidden();
});
