"""
指标召回节点。

负责把用户对“销售额、客单价、转化率”等度量目标的自然语言表达，
映射到元数据知识库中已经定义好的 MetricInfo。

处理链路：

    query + 公共 keywords
        -> 指标语义扩展 Prompt
        -> Embedding
        -> 指标 Qdrant Collection
        -> MetricInfo 按业务 id 去重
        -> retrieved_metric_infos

召回到的指标只是候选，后续 merge_retrieved_info 会补齐指标依赖字段，
filter_metric 再选择当前问题真正需要使用的最小指标集合。
"""

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.entities.metric_info import MetricInfo
from app.prompt.prompt_loader import load_prompt


async def recall_metric(
    state: DataAgentState,
    runtime: Runtime[DataAgentContext],
) -> dict[str, list[MetricInfo]]:
    """召回与用户度量意图相关的指标业务实体。"""

    writer = runtime.stream_writer
    step = "召回指标信息"
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

        # 指标召回和字段召回共享 Embedding Client，但写入和查询的是独立的
        # metric_info_collection_rebuild，避免字段向量与指标向量混在一起。
        embedding_client = runtime.context["embedding_client"]
        metric_qdrant_repository = runtime.context["metric_qdrant_repository"]

        # 指标 Prompt 面向概念级度量目标，不允许输出字段、表名或计算 SQL。
        # 例如用户说“成交总额”，模型可扩展为 ["成交总额", "交易额", "GMV"]。
        prompt = PromptTemplate(
            template=load_prompt("extend_keywords_for_metric_recall"),
            input_variables=["query"],
        )
        output_parser = JsonOutputParser()
        chain = prompt | llm | output_parser

        expanded_keywords: list[str] = await chain.ainvoke({"query": query})
        all_keywords = set(keywords + expanded_keywords)

        # 同一个指标会以名称、描述、多个别名写成多个 Qdrant Point；
        # 多个查询词也可能同时命中 GMV，因此按稳定业务 id 去重。
        metric_info_map: dict[str, MetricInfo] = {}

        for keyword in all_keywords:
            embedding = await embedding_client.aembed_query(keyword)
            current_metric_infos: list[
                MetricInfo
            ] = await metric_qdrant_repository.search(embedding)

            for metric_info in current_metric_infos:
                if metric_info.id not in metric_info_map:
                    metric_info_map[metric_info.id] = metric_info

        retrieved_metric_infos = list(metric_info_map.values())
        retrieved_metric_ids = [
            metric_info.id for metric_info in retrieved_metric_infos
        ]
        logger.info(f"召回指标成功: {retrieved_metric_ids}")

        writer(
            {
                "type": "progress",
                "step": step,
                "status": "success",
            }
        )
        return {"retrieved_metric_infos": retrieved_metric_infos}

    except Exception as error:
        # 指标召回失败后继续生成 SQL，可能使模型脱离项目定义的指标口径；
        # 因此这里发送错误事件并让异常终止当前工作流。
        logger.error(f"{step}失败: {error}")
        writer(
            {
                "type": "progress",
                "step": step,
                "status": "error",
            }
        )
        raise
