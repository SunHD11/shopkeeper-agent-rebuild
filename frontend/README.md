# Shopkeeper Agent Rebuild Frontend

这是 `shopkeeper-agent-rebuild` 的在线自然语言问数工作台。它不是另起一套业务逻辑，
而是把 FastAPI 已经提供的 SSE 事件、健康状态和结构化错误可靠地呈现给用户。

## 数据链路

```text
用户问题
  -> POST /api/query
  -> FastAPI / QueryService / LangGraph
  -> progress | result | error SSE 事件
  -> agentApi + SseDecoder
  -> useAgentQuery 会话状态
  -> 执行阶段、结果表格或可重试错误
```

`useServiceHealth` 独立请求 `/health/ready`。健康检查失败不会阻止用户查看页面，
但会在侧栏明确展示基础服务是否就绪。

## 目录职责

| 目录 | 职责 |
|---|---|
| `src/types` | 与 FastAPI 契约对应的事件和健康状态类型 |
| `src/lib` | SSE 解码、HTTP 请求、结果格式化等无界面逻辑 |
| `src/hooks` | 将流式事件归并为 React 会话状态 |
| `src/components` | 布局、输入、进度、错误和结果展示 |
| `src/data` | 教学示例问题 |
| `e2e` | 真实浏览器中的完整交互验证 |

视觉规范与取舍统一记录在项目根目录的 `DESIGN.md`，避免组件各自“自由发挥”。

## 本地启动

先在项目根目录启动 FastAPI：

```powershell
uv run fastapi dev main.py
```

然后启动前端：

```powershell
cd frontend
pnpm install
pnpm dev
```

浏览器访问 `http://127.0.0.1:5173`。Vite 默认把 `/api` 和 `/health` 代理到
`http://127.0.0.1:8000`。若后端使用其他地址，可以复制 `.env.example` 为
`.env.local` 并修改：

```dotenv
VITE_DEV_PROXY_TARGET=http://127.0.0.1:8000
```

跨域独立部署时可设置 `VITE_API_BASE_URL`，同时必须把前端 Origin 加到后端 CORS
白名单中。

## 质量检查

```powershell
pnpm lint
pnpm test
pnpm build
pnpm exec playwright install chromium
pnpm e2e
```

单元测试覆盖 SSE 网络拆包、HTTP 错误映射、Hook 状态归并、CSV、输入快捷键和
结果表格；Playwright 用浏览器验证桌面与移动布局以及完整问数结果链路。

## 当前边界

- 会话仅保存在当前页面内，刷新后不恢复；
- 不展示或允许编辑生成 SQL，后端仍是 SQL 安全边界的唯一可信来源；
- 图表不会根据任意结果自动猜测，当前统一使用可复制、可导出的数据表；
- 真实 LLM 端到端测试仍由后端显式的 `RUN_LIVE_LLM_TESTS=1` 控制，避免误扣费。
