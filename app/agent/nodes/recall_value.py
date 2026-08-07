"""
字段真实取值召回节点。

负责识别用户问题中可能真实存放在 DW 字段里的业务值，例如地区、状态、
商品、会员等级等，并从 Elasticsearch 中找出这些值所属的真实字段。

处理链路：

    query + 公共 keywords
        -> 字段值语义扩展 Prompt
        -> Elasticsearch 全文检索
        -> ValueInfo 按业务 id 去重
        -> retrieved_value_infos

与字段和指标不同，真实取值搜索更关注文字是否在数据中出现，
所以这一条链路使用 Elasticsearch，而不是 Embedding + Qdrant。
"""

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.entities.value_info import ValueInfo
from app.prompt.prompt_loader import load_prompt


async def recall_value(
    state: DataAgentState,
    runtime: Runtime[DataAgentContext],
) -> dict[str, list[ValueInfo]]:
    """召回用户问题中业务值对应的 ValueInfo 实体。"""

    writer = runtime.stream_writer
    step = "召回字段取值"
    writer(
        {
            "type": "progress",
            "step": step,
            "status": "running",
        }
    )

    try:
        query = state["query"]
        keywords = state["keywords"]

        # ValueESRepository 默认读取 app_config.es.index_name，当前 rebuild 使用
        # value_index_rebuild，不会搜索原项目的 value_index。
        value_es_repository = runtime.context["value_es_repository"]

        # 字段值 Prompt 只输出可能存在于真实数据中的值，不输出字段名或指标。
        # 例如“最近三个月华东地区的销售额”可能扩展为 ["华东", "最近三个月"]。
        prompt = PromptTemplate(
            template=load_prompt("extend_keywords_for_value_recall"),
            input_variables=["query"],
        )
        output_parser = JsonOutputParser()
        chain = prompt | llm | output_parser

        expanded_keywords: list[str] = await chain.ainvoke({"query": query})

        # 公共关键词提供用户显式说法，LLM 扩展结果提供更适合值检索的候选；
        # 合并后逐个在 ES 的 value 字段上执行全文匹配。
        all_keywords = set(keywords + expanded_keywords)

        # 一个业务值可能被多个关键词命中，例如“华东地区”和“华东”都可能
        # 返回 dim_region.region_name.华东，因此使用 ValueInfo.id 去重。
        value_info_map: dict[str, ValueInfo] = {}

        for keyword in all_keywords:
            # ES Repository 内部封装 match 查询、IK 分词、最低分数和结果转换；
            # 这里直接传文本，不需要先调用 Embedding Client。
            current_value_infos: list[ValueInfo] = await value_es_repository.search(
                keyword
            )

            for value_info in current_value_infos:
                if value_info.id not in value_info_map:
                    value_info_map[value_info.id] = value_info

        retrieved_value_infos = list(value_info_map.values())
        retrieved_value_ids = [value_info.id for value_info in retrieved_value_infos]
        logger.info(f"召回字段取值成功: {retrieved_value_ids}")

        writer(
            {
                "type": "progress",
                "step": step,
                "status": "success",
            }
        )
        return {"retrieved_value_infos": retrieved_value_infos}

    except Exception as error:
        # 如果真实值召回失败却继续生成 SQL，模型可能猜错 WHERE 条件的字段和值；
        # 因此与另外两条召回链一致，报告 error 后重新抛出异常。
        logger.error(f"{step}失败: {error}")
        writer(
            {
                "type": "progress",
                "step": step,
                "status": "error",
            }
        )
        raise
