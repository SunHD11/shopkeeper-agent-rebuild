# Shopkeeper Agent Rebuild 完整交付计划

## 最终完成标准

一台只安装了 Git、Docker Desktop 和 Docker Compose 的新机器，在填写 `.env`
后应当能够：

1. 构建并启动项目专属的全部基础服务、FastAPI 和前端；
2. 等待中文 Embedding 模型自动下载并通过健康检查；
3. 幂等构建元数据知识库；
4. 在浏览器中提交自然语言问题并收到真实 DW 查询结果；
5. 在每次提交时自动执行前后端测试和镜像构建检查；
6. 通过日志中的 `request_id` 定位一次失败请求。

## 已有能力与复用策略

| 已有能力 | 复用方式 |
|---|---|
| `docker/docker-compose.yaml` 基础服务 | 原地扩展 API 和前端，不建立第二套 Compose |
| FastAPI `/health/live`、`/health/ready` | 直接作为容器健康检查和启动门槛 |
| `build_meta_knowledge.py` | 作为显式、可重复执行的知识库初始化任务 |
| `scripts/check_services.ps1` | 扩展为基础服务与完整应用两级检查 |
| 后端 pytest 与前端 Vitest/Playwright | 直接接入 CI，不更换测试框架 |
| 前端相对路径 `/api`、`/health` | 由 Nginx 同源转发，生产环境无需额外 CORS |

## 发布拓扑

```text
Browser :5173
    |
    v
Frontend / Nginx
    |-- /             -> React 静态资源
    |-- /api/*        -> api:8000（关闭代理缓冲，保留 SSE）
    `-- /health/*     -> api:8000
                           |
                           v
                    FastAPI + LangGraph
                    |      |       |       |
                    v      v       v       v
                  MySQL  Qdrant    ES     TEI
                           |
                           v
                       DeepSeek API
```

容器之间使用 Compose 服务名和容器端口；宿主机开发仍使用 `localhost` 和当前
隔离端口。两种模式共用一份 `conf/app_config.yaml`，连接地址由环境变量覆盖。

## 实施阶段

### 阶段 10A：运行配置与应用镜像

- 为 MySQL、Qdrant、Elasticsearch、Embedding 增加环境变量覆盖；
- 创建非 root FastAPI 镜像；
- 创建 React 多阶段构建镜像；
- 用 Nginx 提供静态资源并正确代理 SSE；
- 用 `.dockerignore` 排除虚拟环境、密钥、日志和构建产物。

验证：配置单元测试、`docker compose config`、两个镜像独立构建。

### 阶段 10B：完整 Compose 与启动流程

- 把 `api`、`frontend` 加入现有 Compose；
- TEI 从 Hugging Face 自动下载模型到命名卷，不再依赖 Git 忽略目录；
- 使用 readiness 控制 API 健康状态；
- 提供环境检查、基础服务启动、知识库构建和完整栈启动脚本；
- 保持普通 `down` 不删除持久卷。

验证：全栈启动、五项依赖 ready、前端首页 200、API live 200。

### 阶段 10C：持续集成与发布门禁

- Backend：锁文件检查、ruff、209+ 单元测试；
- Frontend：冻结安装、类型检查、Vitest、生产构建；
- E2E：Playwright 使用模拟 SSE 验证桌面和移动端；
- Containers：校验 Compose 并构建 API/Frontend 镜像；
- Live LLM：继续保持显式手动开关，避免 CI 产生费用。

验证：GitHub Actions 所有非付费任务通过。

### 阶段 10D：真实发布验收

- 使用有效 `LLM_API_KEY`；
- 幂等执行两次知识库构建；
- 从浏览器完成至少三个真实问题；
- 覆盖成功、空结果、停止和可重试失败；
- 保存验收命令、结果和已知限制。

验证：`RUN_LIVE_LLM_TESTS=1` 的真实 API E2E 通过，浏览器返回预期 DW 数据。

## 测试与故障矩阵

```text
配置加载
  |-- 未设置容器变量 -> 使用本机默认值                  [unit]
  `-- 设置容器变量   -> 使用服务名和内部端口            [unit]

镜像构建
  |-- uv.lock 与 pyproject 不一致 -> 构建失败           [CI]
  |-- pnpm-lock 不一致            -> 构建失败           [CI]
  `-- 本机密钥/.venv 被带入镜像   -> .dockerignore 阻止 [inspection]

完整运行
  |-- 依赖仍在启动 -> /health/ready=503，容器不冒充 ready [smoke]
  |-- 依赖全部就绪 -> /health/ready=200                  [smoke]
  |-- SSE 查询      -> Nginx 不缓冲，事件持续到达         [e2e]
  `-- LLM 不可用    -> 前端显示结构化可重试错误           [e2e/live]
```

## 现实故障模式

| 故障 | 处理 | 用户看到什么 | 证据 |
|---|---|---|---|
| 首次模型下载较慢 | API readiness 保持失败，Compose 持续探测 | 服务正在准备而不是假成功 | 健康检查 |
| MySQL/ES 尚未就绪 | API 可以启动但 readiness 返回 503 | 前端服务状态不可用 | 集成测试 |
| Nginx 缓冲 SSE | 显式关闭 buffering/cache | 进度逐条出现 | Playwright/配置检查 |
| LLM Key 缺失或占位 | 启动前脚本拒绝真实验收 | 明确指出要修改的变量 | 脚本测试 |
| 外部 LLM 限流 | 后端稳定错误码与 retryable | 可重试错误卡片 | 现有单元测试 |

## 明确不在本轮范围

- Kubernetes：单机 Compose 已满足当前交付目标，引入集群只增加运维面；
- 用户登录与多租户：属于产品化阶段，不阻塞单用户完整问数；
- 会话历史数据库：当前页面会话足够验证核心链路；
- 自动执行付费 LLM CI：会泄露或消耗密钥，保留手动门禁；
- 自动备份与异地容灾：在确定正式部署平台后再设计。

## 实施任务

- [x] T1（P1）让应用配置同时支持宿主机和 Compose 网络；
- [x] T2（P1）构建 FastAPI 与 React/Nginx 镜像；
- [x] T3（P1）扩展 Compose 并消除本地 Embedding 模型前置条件；
- [x] T4（P1）提供新机器启动、初始化和验收命令；
- [x] T5（P1）建立 GitHub Actions 前后端与镜像门禁；
- [x] T6（P1）完成容器配置、冒烟和真实 LLM 验收；
- [ ] T7（P2）合并阶段分支并创建带版本号的发布候选。

T1-T6 的本机验收证据见 `docs/RELEASE_ACCEPTANCE.md`。T7 涉及把阶段分支
合并进主分支和创建正式版本标签，需在远端 CI 通过后执行。
