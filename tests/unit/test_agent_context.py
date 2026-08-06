"""测试在线问数 Agent 的 LangGraph 运行时上下文。"""

from typing import get_type_hints
from unittest.mock import Mock

from langchain_huggingface import HuggingFaceEndpointEmbeddings

from app.agent.context import DataAgentContext
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository


def test_data_agent_context_holds_all_runtime_dependencies() -> None:
    """Context 能够保存一次图执行需要复用的六项外部依赖。"""

    # 使用带 spec 的 Mock 表达真实依赖类型，但不实例化客户端、Repository，
    # 因此本测试不会连接 MySQL、Qdrant、Elasticsearch 或 Embedding 服务。
    column_repository = Mock(spec=ColumnQdrantRepository)
    embedding_client = Mock(spec=HuggingFaceEndpointEmbeddings)
    metric_repository = Mock(spec=MetricQdrantRepository)
    value_repository = Mock(spec=ValueESRepository)
    meta_repository = Mock(spec=MetaMySQLRepository)
    dw_repository = Mock(spec=DWMySQLRepository)

    context = DataAgentContext(
        column_qdrant_repository=column_repository,
        embedding_client=embedding_client,
        metric_qdrant_repository=metric_repository,
        value_es_repository=value_repository,
        meta_mysql_repository=meta_repository,
        dw_mysql_repository=dw_repository,
    )

    # 使用 is 验证 Context 保存的是调用方注入的原对象，
    # 而不是在内部复制或重新创建的对象。
    assert context["column_qdrant_repository"] is column_repository
    assert context["embedding_client"] is embedding_client
    assert context["metric_qdrant_repository"] is metric_repository
    assert context["value_es_repository"] is value_repository
    assert context["meta_mysql_repository"] is meta_repository
    assert context["dw_mysql_repository"] is dw_repository


def test_data_agent_context_defines_only_runtime_tool_keys() -> None:
    """Context 的字段只描述外部工具，不混入查询过程中的业务状态。"""

    expected_keys = {
        "column_qdrant_repository",
        "embedding_client",
        "metric_qdrant_repository",
        "value_es_repository",
        "meta_mysql_repository",
        "dw_mysql_repository",
    }

    # DataAgentContext 默认 total=True，因此六个依赖都是必填字段。
    assert DataAgentContext.__required_keys__ == frozenset(expected_keys)
    assert DataAgentContext.__optional_keys__ == frozenset()

    # query、keywords、sql 等会被节点持续修改的业务数据属于 DataAgentState，
    # 不应该出现在运行时依赖 Context 中。
    assert "query" not in DataAgentContext.__annotations__
    assert "keywords" not in DataAgentContext.__annotations__
    assert "sql" not in DataAgentContext.__annotations__


def test_data_agent_context_preserves_original_project_type_contract() -> None:
    """六个 Context 字段的类型与原项目节点使用的具体依赖保持一致。"""

    # get_type_hints() 会解析 TypedDict 上的真实类型标注，
    # 这个测试可以及时发现字段被误写成通用 object、客户端或错误 Repository。
    type_hints = get_type_hints(DataAgentContext)

    assert type_hints == {
        "column_qdrant_repository": ColumnQdrantRepository,
        "embedding_client": HuggingFaceEndpointEmbeddings,
        "metric_qdrant_repository": MetricQdrantRepository,
        "value_es_repository": ValueESRepository,
        "meta_mysql_repository": MetaMySQLRepository,
        "dw_mysql_repository": DWMySQLRepository,
    }
