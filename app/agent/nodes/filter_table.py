"""
候选表和字段过滤节点。

``merge_retrieved_info`` 会尽量补齐当前问题可能涉及的表、字段、指标依赖字段
以及主外键，因此生成的 ``table_infos`` 强调“不遗漏”，候选范围通常会偏大。
本节点进一步判断哪些表和字段真正参与当前查询，并删除无关候选。

处理链路：

    query + 候选 table_infos
        -> 将嵌套表结构序列化为 YAML
        -> filter_table_info Prompt
        -> LLM 返回“表名 -> 字段名列表”的 JSON 对象
        -> JsonOutputParser 解析
        -> 程序从原始 TableInfoState 中裁剪表和字段
        -> 写回精简后的 table_infos

本节点遵循“LLM 只做语义选择，程序负责可信结构裁剪”的原则。LLM 不重新生成
表信息或字段信息，因此不能修改 Meta MySQL 提供的真实名称、类型、角色和说明。
"""

import yaml
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState, TableInfoState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def filter_table(
    state: DataAgentState,
    runtime: Runtime[DataAgentContext],
) -> dict[str, list[TableInfoState]]:
    """根据用户问题筛选生成 SQL 真正需要的候选表和字段。

    输入：

    - ``state["query"]``：用户原始自然语言问题；
    - ``state["table_infos"]``：合并节点生成的候选表结构上下文。

    输出：

    - ``table_infos``：只保留被模型选择且在原候选中真实存在的表和字段。

    返回结果是局部 State 更新。LangGraph 会使用它覆盖此前较宽泛的候选
    ``table_infos``，后续 SQL 生成节点只会看到过滤后的 Schema 上下文。
    """

    # stream_writer 用于向 QueryService 或前端发送节点进度。
    # 它只负责可观测性，不参与表和字段的过滤逻辑。
    writer = runtime.stream_writer
    step = "过滤表信息"
    writer(
        {
            "type": "progress",
            "step": step,
            "status": "running",
        }
    )

    try:
        # query 是语义判断依据；table_infos 是合并节点尽量补全后的候选 Schema。
        # 例如一个“华东销售总额”问题可能同时带有订单表、地区表及其主外键。
        query = state["query"]
        table_infos: list[TableInfoState] = state["table_infos"]

        # Prompt 中包含两个占位符：
        #
        #     {query}
        #     {table_infos}
        #
        # filter_table_info.prompt 要求模型只返回当前问题实际需要的表和字段，
        # 并在多表查询中保留完成 JOIN 所需的主外键字段。
        prompt = PromptTemplate(
            template=load_prompt("filter_table_info"),
            input_variables=["query", "table_infos"],
        )

        # JsonOutputParser 将模型输出的 JSON 文本转换成 Python 对象。
        #
        # 模型输出示例：
        #
        #     {
        #         "fact_order": ["order_amount", "region_id"],
        #         "dim_region": ["region_id", "region_name"]
        #     }
        #
        # 解析后得到 Python 的 dict[str, list[str]]。
        output_parser = JsonOutputParser()

        # LCEL 管道依次完成：填充 Prompt -> 调用 LLM -> 解析 JSON。
        # 节点只需要调用一次 chain.ainvoke()，无需手动处理中间消息对象。
        chain = prompt | llm | output_parser

        # table_infos 是“表 -> 字段列表”的嵌套结构。转换成 YAML 后层次关系清晰，
        # 同时保留字段类型、角色、样例、说明和别名，便于模型判断字段用途。
        # allow_unicode=True 保留中文，sort_keys=False 保留 State 中原有字段顺序。
        table_infos_yaml = yaml.dump(
            table_infos,
            allow_unicode=True,
            sort_keys=False,
        )

        # 异步执行完整 LCEL 链。传入字典的 Key 必须与 PromptTemplate 声明的
        # input_variables 一致，否则提示词无法完成变量填充。
        selected_table_columns = await chain.ainvoke(
            {
                "query": query,
                "table_infos": table_infos_yaml,
            }
        )

        # JsonOutputParser 只能保证输出是合法 JSON，不能保证它遵守业务格式。
        # 这里进一步要求：
        #
        # 1. 顶层必须是 dict；
        # 2. 每个表名必须是 str；
        # 3. 每个表对应的值必须是 list；
        # 4. 字段列表中的每一项必须是 str。
        #
        # 空字典 {} 是合法结果，表示当前问题不需要使用任何候选表。
        if not isinstance(selected_table_columns, dict) or not all(
            isinstance(table_name, str)
            and isinstance(column_names, list)
            and all(isinstance(column_name, str) for column_name in column_names)
            for table_name, column_names in selected_table_columns.items()
        ):
            raise ValueError(
                "表过滤模型必须返回“表名 -> 字段名称字符串数组”的 JSON 对象"
            )

        # LLM 只提供名称选择，真正的表字段结构仍然从原始 table_infos 中取得。
        # 这样即使模型返回不存在的表、字段，程序也不会创建虚假 Schema。
        filtered_table_infos: list[TableInfoState] = []

        for table_info in table_infos:
            table_name = table_info["name"]

            # 当前表名没有被模型选择，直接跳过整张表。
            if table_name not in selected_table_columns:
                continue

            # 使用 set 对模型重复返回的字段名称去重，同时让成员判断保持高效。
            selected_column_name_set = set(selected_table_columns[table_name])

            # 从原始 ColumnInfoState 列表中筛选，而不是采用模型生成的新结构。
            # 因此字段 type、role、examples、description 和 alias 都保持不变。
            filtered_columns = [
                column_info
                for column_info in table_info["columns"]
                if column_info["name"] in selected_column_name_set
            ]

            # Prompt 约定每张被选中的表至少保留一个字段。如果模型只返回未知
            # 字段或空列表，过滤结果为空，此表不应进入后续 SQL 上下文。
            if not filtered_columns:
                continue

            # 创建新的 TableInfoState，而不是原地修改 table_info["columns"]。
            # 这样本节点的输入候选仍保持原样，测试、日志或其他并行分支读取它时
            # 不会观察到难以追踪的隐式修改。
            filtered_table_infos.append(
                TableInfoState(
                    name=table_info["name"],
                    role=table_info["role"],
                    description=table_info["description"],
                    columns=filtered_columns,
                )
            )

        logger.info(
            "表信息过滤成功，保留表: "
            f"{[table_info['name'] for table_info in filtered_table_infos]}"
        )

        writer(
            {
                "type": "progress",
                "step": step,
                "status": "success",
            }
        )

        # 返回局部更新。LangGraph 会用过滤后的表结构覆盖 State 中原来的候选
        # table_infos，但 query、metric_infos 等其他字段不会被这个返回值改变。
        return {"table_infos": filtered_table_infos}

    except Exception as error:
        # Prompt 加载、YAML 序列化、LLM 调用、JSON 解析或输出结构校验失败时，
        # 不能伪装成“没有相关表”，否则 SQL 生成节点可能在空 Schema 下编造 SQL。
        logger.error(f"{step}失败: {error}")
        writer(
            {
                "type": "progress",
                "step": step,
                "status": "error",
            }
        )
        raise
