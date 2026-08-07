"""测试完整在线 Agent 的 LangGraph 拓扑与 SQL 条件路由。"""

import pytest
from langgraph.constants import END, START

from app.agent.graph import graph, graph_builder, route_after_validation
from app.agent.state import DataAgentState


@pytest.mark.parametrize(
    ("error", "expected_node"),
    [
        (None, "run_sql"),
        ("Unknown column 'order_total'", "correct_sql"),
    ],
    ids=["valid-sql", "invalid-sql"],
)
def test_route_after_validation_selects_expected_branch(
    error: str | None,
    expected_node: str,
) -> None:
    """校验成功直接执行，校验失败进入修正节点。"""

    assert route_after_validation(DataAgentState(error=error)) == expected_node


def test_agent_graph_contains_all_nodes() -> None:
    """编译后的 Graph 包含原项目完整在线问数链路的十二个业务节点。"""

    expected_nodes = {
        START,
        "extract_keywords",
        "recall_column",
        "recall_value",
        "recall_metric",
        "merge_retrieved_info",
        "filter_metric",
        "filter_table",
        "add_extra_context",
        "generate_sql",
        "validate_sql",
        "correct_sql",
        "run_sql",
        END,
    }

    assert set(graph.get_graph().nodes) == expected_nodes


def test_agent_graph_has_complete_execution_edges() -> None:
    """主链、并行召回、并行过滤、条件分支和 END 边全部存在。"""

    actual_edges = {(edge.source, edge.target) for edge in graph.get_graph().edges}
    expected_edges = {
        (START, "extract_keywords"),
        ("extract_keywords", "recall_column"),
        ("extract_keywords", "recall_value"),
        ("extract_keywords", "recall_metric"),
        ("recall_column", "merge_retrieved_info"),
        ("recall_value", "merge_retrieved_info"),
        ("recall_metric", "merge_retrieved_info"),
        ("merge_retrieved_info", "filter_table"),
        ("merge_retrieved_info", "filter_metric"),
        ("filter_table", "add_extra_context"),
        ("filter_metric", "add_extra_context"),
        ("add_extra_context", "generate_sql"),
        ("generate_sql", "validate_sql"),
        ("validate_sql", "run_sql"),
        ("validate_sql", "correct_sql"),
        ("correct_sql", "run_sql"),
        ("run_sql", END),
    }

    assert actual_edges == expected_edges


def test_agent_graph_waits_for_all_parallel_branches() -> None:
    """合并和上下文补全使用等待边，不会被单个并行分支提前触发。"""

    assert graph_builder.waiting_edges == {
        (
            ("recall_column", "recall_value", "recall_metric"),
            "merge_retrieved_info",
        ),
        (
            ("filter_table", "filter_metric"),
            "add_extra_context",
        ),
    }
