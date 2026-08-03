# shopkeeper-agent-rebuild

从零复现电商问数 Agent。当前已完成开发环境、基础服务，以及应用基础设施层。

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

第三轮已建立应用访问基础服务所需的公共层：

- `app/conf`：YAML + `.env` 结构化配置
- `app/core`：请求 ID 上下文与 Loguru 日志
- `app/clients`：MySQL、Qdrant、Elasticsearch、Embedding 客户端管理器
- `app/scripts/check_clients.py`：统一真实连接检查
- `tests/unit`：不依赖 Docker 的快速单元测试
- `tests/integration`：连接真实本地服务的集成测试

客户端采用显式生命周期：应用启动时执行 `init()`，退出时在 `finally` 中执行 `close()`。

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
