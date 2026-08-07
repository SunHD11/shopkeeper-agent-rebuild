"""
三路召回信息合并节点。

字段、指标和字段真实取值由三个独立节点并行召回，它们返回的仍然只是
“可能相关的零散候选”。本节点负责把这些候选补全并重组为后续过滤节点和
SQL 生成节点可以直接使用的统一上下文。

处理链路：

    retrieved_column_infos
    + retrieved_metric_infos
    + retrieved_value_infos
        -> 按字段业务 id 合并和去重
        -> 补齐指标依赖字段
        -> 把真实字段值写入字段 examples
        -> 按 table_id 组织字段
        -> 补齐每张表的主键和外键
        -> 查询表业务信息
        -> table_infos + metric_infos

这个节点不调用 LLM，也不访问 Qdrant 或 Elasticsearch。召回系统负责“找候选”，
Meta MySQL 负责提供可信的完整元数据，本节点则负责把两者整理成生成 SQL 前的
结构化知识上下文。
"""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import (
    ColumnInfoState,
    DataAgentState,
    MetricInfoState,
    TableInfoState,
)
from app.core.log import logger
from app.entities.column_info import ColumnInfo
from app.entities.metric_info import MetricInfo
from app.entities.table_info import TableInfo
from app.entities.value_info import ValueInfo


async def merge_retrieved_info(
    state: DataAgentState,
    runtime: Runtime[DataAgentContext],
) -> dict[str, list[TableInfoState] | list[MetricInfoState]]:
    """合并三路召回结果，生成候选表上下文和候选指标上下文。

    输入来自三个召回节点写入的 State：

    - ``retrieved_column_infos``：Qdrant 召回到的字段实体；
    - ``retrieved_metric_infos``：Qdrant 召回到的指标实体；
    - ``retrieved_value_infos``：Elasticsearch 召回到的真实字段值实体。

    输出仍然是局部 State 更新：

    - ``table_infos``：按表组织，并补齐依赖字段和主外键后的表结构；
    - ``metric_infos``：适合后续 Prompt 使用的指标结构。

    LangGraph 会把返回值合并回当前 ``DataAgentState``，后续的
    ``filter_table`` 和 ``filter_metric`` 节点再进一步缩小候选范围。
    """

    # stream_writer 用于把当前步骤的运行状态实时交给上层 Service 或前端。
    # 它只负责进度通知，不参与业务数据的合并。
    writer = runtime.stream_writer
    step = "合并召回信息"
    writer(
        {
            "type": "progress",
            "step": step,
            "status": "running",
        }
    )

    try:
        # 三组输入都是上一阶段已经转换好的业务实体，而不是 Qdrant Point、
        # Elasticsearch Hit 或 ORM 对象。因此，本节点可以只围绕业务含义工作。
        retrieved_column_infos: list[ColumnInfo] = state["retrieved_column_infos"]
        retrieved_metric_infos: list[MetricInfo] = state["retrieved_metric_infos"]
        retrieved_value_infos: list[ValueInfo] = state["retrieved_value_infos"]

        # Qdrant 和 ES 只能提供“检索命中的候选”；完整字段、表结构和主外键
        # 仍以 Meta MySQL 为准，所以缺失信息统一通过 Meta Repository 补齐。
        meta_mysql_repository = runtime.context["meta_mysql_repository"]

        # ------------------------------------------------------------------
        # 第 1 步：把字段召回结果转换为以 column_id 为 Key 的字典。
        # ------------------------------------------------------------------
        #
        # 同一个字段可能被多个关键词、字段描述或字段别名重复命中。
        # 使用稳定的业务 id（例如 fact_order.order_amount）作为 Key，可以：
        #
        # 1. 对初始字段召回结果自然去重；
        # 2. 快速判断指标依赖字段是否已经存在；
        # 3. 快速定位字段值应该被补充到哪个字段。
        column_info_map: dict[str, ColumnInfo] = {
            column_info.id: column_info for column_info in retrieved_column_infos
        }

        # ------------------------------------------------------------------
        # 第 2 步：补齐每个指标依赖的真实字段。
        # ------------------------------------------------------------------
        #
        # MetricInfo 告诉系统“用户可能想计算什么”，relevant_columns 告诉系统
        # “这个指标实际上依赖哪些 DW 字段”。例如 GMV 可能依赖
        # fact_order.order_amount。即使字段召回没有命中该字段，也必须从
        # Meta MySQL 补齐，否则后续 SQL 生成只有指标名称，却没有计算依据。
        for metric_info in retrieved_metric_infos:
            for column_id in metric_info.relevant_columns:
                if column_id in column_info_map:
                    continue

                column_info = await meta_mysql_repository.get_column_info_by_id(
                    column_id
                )

                # Repository 的查询结果允许为 None。这里主动抛出包含业务 id 的
                # 明确错误，比稍后访问 None.table_id 更容易定位元数据库缺失问题。
                if column_info is None:
                    raise ValueError(
                        f"Meta MySQL 中不存在指标 {metric_info.id} "
                        f"依赖的字段: {column_id}"
                    )

                column_info_map[column_id] = column_info

        # ------------------------------------------------------------------
        # 第 3 步：把字段真实取值合并到对应字段的 examples。
        # ------------------------------------------------------------------
        #
        # ValueInfo 只记录“值是什么、属于哪个字段”，例如：
        #
        #     value="华东"
        #     column_id="dim_region.region_name"
        #
        # SQL 生成节点真正需要的是完整字段上下文，因此这里先确保对应字段存在，
        # 然后把“华东”补入 examples。模型后续就能更可靠地生成：
        #
        #     WHERE region_name = '华东'
        for value_info in retrieved_value_infos:
            column_id = value_info.column_id

            if column_id not in column_info_map:
                column_info = await meta_mysql_repository.get_column_info_by_id(
                    column_id
                )
                if column_info is None:
                    raise ValueError(
                        "Meta MySQL 中不存在字段取值 "
                        f"{value_info.id} 所属的字段: {column_id}"
                    )
                column_info_map[column_id] = column_info

            # 相同真实值可能被多个关键词重复召回；写入 examples 前再次去重，
            # 避免提示词中出现大量重复样例。
            target_column = column_info_map[column_id]
            if value_info.value not in target_column.examples:
                target_column.examples.append(value_info.value)

        # ------------------------------------------------------------------
        # 第 4 步：根据 table_id 把分散字段组织到各自所属表中。
        # ------------------------------------------------------------------
        #
        # 检索结果是“字段列表”，而 SQL 生成提示词需要的是：
        #
        #     表
        #       -> 字段 1
        #       -> 字段 2
        #
        # 因此使用 table_id 建立分组。内层仍然使用 column_id -> ColumnInfo，
        # 方便下一步补充主外键时继续进行 O(1) 去重。
        table_to_column_map: dict[str, dict[str, ColumnInfo]] = {}
        for column_info in column_info_map.values():
            table_columns = table_to_column_map.setdefault(column_info.table_id, {})
            table_columns[column_info.id] = column_info

        # ------------------------------------------------------------------
        # 第 5 步：为每张候选表补齐主键和外键字段。
        # ------------------------------------------------------------------
        #
        # 用户通常不会在问题中直接说“请使用 customer_id 外键”，所以主外键
        # 很容易被语义召回遗漏；但多表 SQL 的 JOIN 又必须依靠这些字段。
        # 因此，只要一张表进入候选范围，就从 Meta MySQL 兜底查询它的
        # primary_key 和 foreign_key 字段，并按字段业务 id 合并去重。
        for table_id, table_columns in table_to_column_map.items():
            key_columns: list[
                ColumnInfo
            ] = await meta_mysql_repository.get_key_columns_by_table_id(table_id)

            for key_column in key_columns:
                table_columns.setdefault(key_column.id, key_column)

        # ------------------------------------------------------------------
        # 第 6 步：生成面向后续 Agent 节点的 TableInfoState。
        # ------------------------------------------------------------------
        #
        # Meta MySQL 中表和字段分开保存，但 Prompt 更适合读取嵌套结构。
        # 这里查询每张表的名称、角色和描述，并把刚才整理好的字段转换为
        # ColumnInfoState。id、table_id 等内部关联字段在完成组装后不再传给 LLM，
        # 从而让提示词内容更聚焦，也减少模型处理无关信息的负担。
        table_infos: list[TableInfoState] = []

        for table_id, table_column_map in table_to_column_map.items():
            table_info: (
                TableInfo | None
            ) = await meta_mysql_repository.get_table_info_by_id(table_id)
            if table_info is None:
                raise ValueError(f"Meta MySQL 中不存在候选表: {table_id}")

            columns = [
                ColumnInfoState(
                    name=column_info.name,
                    type=column_info.type,
                    role=column_info.role,
                    examples=column_info.examples,
                    description=column_info.description,
                    alias=column_info.alias,
                )
                for column_info in table_column_map.values()
            ]

            table_infos.append(
                TableInfoState(
                    name=table_info.name,
                    role=table_info.role,
                    description=table_info.description,
                    columns=columns,
                )
            )

        # ------------------------------------------------------------------
        # 第 7 步：把指标业务实体转换为 MetricInfoState。
        # ------------------------------------------------------------------
        #
        # 指标已经在第 2 步完成依赖字段补齐。此处只保留后续指标过滤和
        # SQL 生成真正需要的名称、业务口径、依赖字段和别名。
        metric_infos: list[MetricInfoState] = [
            MetricInfoState(
                name=metric_info.name,
                description=metric_info.description,
                relevant_columns=metric_info.relevant_columns,
                alias=metric_info.alias,
            )
            for metric_info in retrieved_metric_infos
        ]

        logger.info(
            "合并召回信息成功，候选表: "
            f"{[table_info['name'] for table_info in table_infos]}，"
            "候选指标: "
            f"{[metric_info['name'] for metric_info in metric_infos]}"
        )

        writer(
            {
                "type": "progress",
                "step": step,
                "status": "success",
            }
        )

        # 返回局部更新即可。LangGraph 会把它与 query、keywords 和三路召回结果
        # 合并进同一份 DataAgentState，供后续两个过滤节点读取。
        return {
            "table_infos": table_infos,
            "metric_infos": metric_infos,
        }

    except Exception as error:
        # 元数据补齐失败时不能继续生成 SQL，否则模型可能在缺少字段或表关系的
        # 情况下自行猜测 Schema。因此记录错误、发送 error 事件并重新抛出异常。
        logger.error(f"{step}失败: {error}")
        writer(
            {
                "type": "progress",
                "step": step,
                "status": "error",
            }
        )
        raise
