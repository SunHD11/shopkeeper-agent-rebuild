# shopkeeper-agent-rebuild

从零复现电商问数 Agent。当前已完成离线元数据知识库、在线 RAG Agent、
LangGraph 编排、FastAPI SSE 接口，以及真实基础服务集成验证。

## 当前开发基线

- Python 3.13
- uv
- Docker Desktop / Docker Compose
- MySQL 8.0，宿主机端口 3307
- Qdrant 1.16，rebuild 专属 HTTP/gRPC 端口 `6335/6336`
- Elasticsearch / Kibana 8.19.10，rebuild 专属端口 `9201/5602`
- Text Embeddings Inference CPU 1.8，宿主机端口 8082
- BAAI/bge-large-zh-v1.5，向量维度 1024

## 当前复现进度

当前项目已经打通：

- `conf/meta_config.yaml + DW MySQL -> Meta MySQL` 的结构化元数据链路；
- 字段和指标描述 `-> Embedding -> Qdrant` 的向量检索链路；
- 字段真实值 `-> Elasticsearch` 的全文检索链路；
- 三路召回、元数据合并、过滤、SQL 生成、校验、修正和执行的 Agent Graph；
- `POST /api/query -> QueryService -> LangGraph -> SSE` 的在线接口；
- `/health/live` 进程存活检查与 `/health/ready` 五项基础服务就绪检查；
- 统一公开错误码、request ID、120 秒总超时和客户端断连取消传播；
- 最多 4 条并发问数、DeepSeek 单次请求超时/一次重试与前端 CORS 白名单；
- Meta MySQL 幂等更新、Qdrant 稳定 Point ID 和 rebuild 专属 Collection；
- SQL 应用层只读检查、30 秒超时、最多 1000 行结果，以及修正后重新校验。

客户端采用显式生命周期：应用启动时执行 `init()`，退出时在 `finally` 中执行 `close()`。

## 构建元数据知识库

基础服务健康后执行：

```powershell
uv run python -m app.scripts.build_meta_knowledge -c conf/meta_config.yaml
```

构建命令可以重复执行；相同配置会更新现有 MySQL 记录、Qdrant Point 和
Elasticsearch 文档，不会因为重复主键失败或不断累积相同向量。

## 启动在线问数 API

请先在本机 `.env` 中填写具有可用额度的 `LLM_API_KEY`，然后执行：

```powershell
uv run fastapi dev main.py
```

Swagger 位于 `http://127.0.0.1:8000/docs`。真实问数请求会访问配置中的外部
LLM。流式响应开始后的失败会被转换为最后一条结构化 SSE 事件，例如：

```json
{
  "type": "error",
  "code": "LLM_UNAVAILABLE",
  "message": "大模型服务暂时不可用，请稍后重试",
  "request_id": "8e71...",
  "retryable": true
}
```

服务端日志保留原始异常，前端只收到安全文案；可以使用响应头或错误事件中的
`request_id` 定位同一次 LangGraph 链路。超过并发上限的请求会在 SSE 开始前
直接返回 HTTP 429，不进入 Agent，也不会创建请求级 MySQL Session 或执行 SQL。

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

`live` 只检查 FastAPI 进程；`ready` 并行检查 Meta MySQL、DW MySQL、Qdrant、
Elasticsearch 和本地 Embedding，任一不可用即返回 503。它不会调用 DeepSeek，
因此不会产生模型费用，也不会因外部模型短暂限流让本地容器被错误重启。

在线运行边界集中位于 `conf/app_config.yaml`：

```yaml
runtime:
  query_timeout_seconds: 120
  retrieval_timeout_seconds: 20
  health_timeout_seconds: 5
  max_concurrent_queries: 4
```

DeepSeek 的 `timeout_seconds` 和 `max_retries` 只作用于模型网络请求；最终 SQL
不会自动重试，避免未来引入非确定性数据库操作时发生重复执行。

完成知识库构建后，可以显式启用付费的真实端到端测试：

```powershell
$env:RUN_LIVE_LLM_TESTS = "1"
uv run pytest tests/integration/api/test_query_e2e.py -v
Remove-Item Env:RUN_LIVE_LLM_TESTS
```

该测试会真实调用 DeepSeek，并验证 HTTP、SSE、LangGraph、三类检索系统和
DW MySQL 最终共同返回预期结果；默认不启用，避免普通测试意外产生模型费用。

## 完全独立服务模式

`shopkeeper-agent-rebuild` 默认启动并管理自己的全部基础服务，不再共享原项目容器：

| 服务 | 来源 | 地址 |
|---|---|---|
| MySQL | rebuild 自管 | `localhost:3307` |
| Qdrant | rebuild 自管 | `http://localhost:6335` |
| Elasticsearch | rebuild 自管 | `http://localhost:9201` |
| Kibana | rebuild 自管 | `http://localhost:5602` |
| Embedding | rebuild 自管 | `http://localhost:8082` |

重建项目同时使用自己的数据卷和业务命名空间：

- Qdrant：`column_info_collection_rebuild`、`metric_info_collection_rebuild`
- Elasticsearch：`value_index_rebuild`

## 1. 安装 Python 依赖

```powershell
uv sync
uv run python main.py
uv run ruff check .
```

## 2. 准备本地配置

`.env` 已提供仅供本机学习使用的默认值，并被 Git 忽略。若要共享项目，只共享 `.env.example`。

## 3. 检查 Compose

所有命令都从项目根目录执行：

```powershell
docker compose --env-file .env -f docker/docker-compose.yaml config --quiet
docker compose --env-file .env -f docker/docker-compose.yaml config --services
```

## 4. 启动默认服务

启动 rebuild 的 MySQL、Qdrant、Elasticsearch、Kibana 和 Embedding：

```powershell
docker compose --env-file .env -f docker/docker-compose.yaml up -d
docker compose --env-file .env -f docker/docker-compose.yaml ps
powershell -ExecutionPolicy Bypass -File scripts/check_services.ps1
```

## 5. 与原项目并行运行

原项目可继续使用 `3306`、`6333/6334`、`9200`、`5601` 和 `8081`；rebuild 使用 `3307`、`6335/6336`、`9201`、`5602` 和 `8082`，两套服务可以同时运行。

为了适配本机 16 GB 内存，Compose 对 rebuild 服务设置了开发环境资源上限：MySQL `768 MB`、Qdrant `512 MB`、Elasticsearch `1.25 GB`、Kibana `1.25 GB`。Elasticsearch JVM 堆为 `512 MB`，Kibana Node.js 堆为 `768 MB`；Embedding 加载中文 BGE 模型时通常使用约 `2 GB` 内存。首次冷启动可能需要一至两分钟。

## 分项启动和验证

### MySQL

```powershell
docker compose --env-file .env -f docker/docker-compose.yaml up -d mysql
docker compose --env-file .env -f docker/docker-compose.yaml ps
docker compose --env-file .env -f docker/docker-compose.yaml logs mysql --tail 100
docker exec -it shopkeeper-rebuild-mysql mysql -uroot -p
```

连接后验证：

```sql
SHOW DATABASES;
USE dw;
SHOW TABLES;
SELECT COUNT(*) FROM fact_order;
USE meta;
SHOW TABLES;
```

### Qdrant

```powershell
docker compose --env-file .env -f docker/docker-compose.yaml up -d qdrant
Invoke-RestMethod http://localhost:6335/collections
```

### Elasticsearch

```powershell
docker compose --env-file .env -f docker/docker-compose.yaml up -d elasticsearch
Invoke-RestMethod http://localhost:9201
```

IK 中文分词验证：

```powershell
$body = @{ analyzer = "ik_max_word"; text = "华北地区销售额" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:9201/_analyze -ContentType "application/json" -Body $body
```

### Kibana

```powershell
docker compose --env-file .env -f docker/docker-compose.yaml up -d kibana
```

浏览器访问 `http://localhost:5602`。

### Embedding

```powershell
docker compose --env-file .env -f docker/docker-compose.yaml up -d embedding
docker compose --env-file .env -f docker/docker-compose.yaml logs -f embedding
```

服务就绪后验证：

```powershell
Invoke-WebRequest http://localhost:8082/health
$body = @{ inputs = "销售额" } | ConvertTo-Json
$result = Invoke-RestMethod -Method Post -Uri http://localhost:8082/embed -ContentType "application/json" -Body $body
$result[0].Count
```

预期向量维度为 `1024`。

## 启动完整服务

```powershell
docker compose --env-file .env -f docker/docker-compose.yaml up -d
docker compose --env-file .env -f docker/docker-compose.yaml ps
```

## 停止 rebuild 自管服务

```powershell
docker compose --env-file .env -f docker/docker-compose.yaml down
```

普通 `down` 会保留数据卷。只有确认所有本地教学数据都可以丢弃时，才使用 `down -v`。

## Python 客户端检查

基础服务健康后，通过 Python 客户端验证实际应用连接：

```powershell
uv run python -m app.scripts.check_clients
uv run pytest tests/unit -v
uv run pytest tests/integration -v
```

客户端遵循显式生命周期：先调用 `init()`，使用完毕后在 `finally` 中调用 `close()`。
