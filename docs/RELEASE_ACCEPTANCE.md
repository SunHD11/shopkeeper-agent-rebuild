# Release delivery acceptance

验收日期：2026-08-10

验收分支：`codex/10-release-delivery`

## 结论

本阶段已完成并本机验证完整的可运行交付链路：应用镜像、七服务 Compose、
Embedding 模型自动下载与缓存、知识库初始化、FastAPI、React/Nginx、SSE、
真实 DeepSeek、RAG/Graph 和 DW 查询均能协同运行。

本机已有其他进程占用 `8000`，因此部署验收临时设置
`API_HOST_PORT=8001`。这是宿主机端口覆盖，不改变容器内部端口或默认配置。

## 验收结果

| 验收项 | 结果 | 证据摘要 |
|---|---|---|
| Compose 配置 | 通过 | 七个服务可解析：MySQL、Qdrant、ES、TEI、API、Frontend、Kibana |
| API 镜像 | 通过 | Python 3.13、`uv sync --locked`、运行用户 `shopkeeper` |
| 前端镜像 | 通过 | Node 24 构建、非特权 Nginx、运行用户 `101` |
| 后端单元测试 | 通过 | `215 passed` |
| 基础服务集成测试 | 通过 | `8 passed, 1 skipped`；跳过项是默认关闭的付费 LLM 用例 |
| 前端单元测试 | 通过 | 6 个测试文件、16 个测试通过 |
| 前端浏览器测试 | 通过 | Playwright 3 个通过、1 个按桌面条件预期跳过 |
| Lint 与生产构建 | 通过 | Ruff、前端类型检查、Vite production build 全部通过 |
| 知识库幂等构建 | 通过 | 连续重复构建成功，无主键或索引冲突 |
| 停止与重启 | 通过 | `down` 保留卷；缓存模型重新装载后完整栈恢复健康 |
| 健康检查 | 通过 | API live/ready、Frontend health、Frontend→API proxy 全部通过 |
| 真实付费 E2E | 通过 | DeepSeek + 检索 + Graph + DW 返回 `[{"销售总额": 107373.0}]` |
| 部署入口真实 SSE | 通过 | 经 `:5173/api/query` 逐步收到进度事件和最终 DW 结果 |

## 关键验收命令

```powershell
# 完整启动（本机因 8000 已占用而使用 8001）
$env:API_HOST_PORT = "8001"
powershell -ExecutionPolicy Bypass -File scripts/start_full_stack.ps1

# 重复构建知识库，验证幂等性
powershell -ExecutionPolicy Bypass -File scripts/build_knowledge.ps1

# 基础服务集成测试
uv run pytest tests/integration -q

# 显式允许一次真实付费 DeepSeek 验收
$env:RUN_LIVE_LLM_TESTS = "1"
uv run pytest tests/integration/api/test_query_e2e.py -v

# 完整停止并保留持久卷
powershell -ExecutionPolicy Bypass -File scripts/stop_full_stack.ps1
```

## 已知非阻塞事项

- FastAPI TestClient 当前出现一条来自 Starlette 的 `httpx` 迁移弃用警告；不影响运行和测试结果。
- GitHub Actions 配置已完成本地语法、Compose 和镜像构建验证；远端工作流结果需要推送后由 GitHub 执行。
- 正式发布标签和主分支合并应当在远端 CI 全绿后进行，不由本机验收提前冒充完成。
