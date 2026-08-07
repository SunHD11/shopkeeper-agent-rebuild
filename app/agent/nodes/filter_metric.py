"""
候选指标过滤 节点。

``merge_retrieved_info`` 会把指标召回结果整理成完整的 ``metric_infos``，
但这些指标仍然只是“可能与用户问题相关的候选项”。本节点使用 LLM 判断哪些
候选指标真正参与回答当前问题，再由程序从原始结构中完成最终筛选。

处理链路：

    query + 候选 metric_infos
        -> 将候选指标序列化为 YAML
        -> filter_metric_info Prompt
        -> LLM 返回指标名称 JSON 数组
        -> JsonOutputParser 解析
        -> 程序按名称过滤原始 MetricInfoState
        -> 写回精简后的 metric_infos

这里采用“LLM 只做选择，程序负责裁剪”的设计。LLM 不重新生成指标对象，
因此不会改写 Meta MySQL 中已经定义好的指标描述、依赖字段和业务口径。
"""

import yaml
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState, MetricInfoState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def filter_metric(
    state: DataAgentState,
    runtime: Runtime[DataAgentContext],
) -> dict[str, list[MetricInfoState]]:
    """根据用户问题筛选当前 SQL 推理真正需要的候选指标。

    输入：

    - ``state["query"]``：用户原始自然语言问题；
    - ``state["metric_infos"]``：合并节点生成的候选指标上下文。

    输出：

    - ``metric_infos``：从原候选中筛选出的最小相关指标集合。

    返回的仍然是局部 State 更新。LangGraph 会使用过滤结果覆盖 State 中原来的
    ``metric_infos``，后续 SQL 生成节点只会看到被保留的指标上下文。
    """

    # stream_writer 向上层 Service 或前端发送节点进度事件。
    # 它只负责可观测性，不参与候选指标的筛选计算。
    writer = runtime.stream_writer
    step = "过滤指标信息"
    writer(
        {
            "type": "progress",
            "step": step,
            "status": "running",
        }
    )

    try:
        # query 提供用户真正想问的问题；metric_infos 是合并阶段尽量补全后
        # 得到的候选集合。过滤节点的目标是从“可能相关”进一步收敛到“确实需要”。
        query = state["query"]
        metric_infos: list[MetricInfoState] = state["metric_infos"]

        # PromptTemplate 负责把用户问题和候选指标填入提示词中的：
        #
        #     {query}
        #     {metric_infos}
        #
        # filter_metric_info.prompt 明确要求模型：
        # 1. 只能从候选指标中选择；
        # 2. 只选择回答问题真正需要的最小集合；
        # 3. 仅返回指标名称组成的 JSON 数组。
        prompt = PromptTemplate(
            template=load_prompt("filter_metric_info"),
            input_variables=["query", "metric_infos"],
        )

        # JsonOutputParser 把模型返回的 JSON 文本转换成 Python 对象。
        #
        # 模型输出：
        #
        #     ["GMV", "订单数量"]
        #
        # 解析结果：
        #
        #     ["GMV", "订单数量"]  # Python list[str]
        output_parser = JsonOutputParser()

        # LCEL 使用管道运算符把三个阶段连接起来：
        #
        # PromptTemplate  填充提示词
        #       ↓
        # llm             调用大模型
        #       ↓
        # JsonOutputParser 解析 JSON
        chain = prompt | llm | output_parser

        # Python 的嵌套字典虽然可以直接转成字符串，但表达容易受到 repr 格式影响。
        # YAML 能清晰保留“指标名称、描述、依赖字段、别名”的层次结构，并通过
        # allow_unicode=True 保留中文，不把“销售总额”转成 Unicode 转义序列。
        # sort_keys=False 则保持 MetricInfoState 原有字段顺序，便于模型稳定阅读。
        metric_infos_yaml = yaml.dump(
            metric_infos,
            allow_unicode=True,
            sort_keys=False,
        )

        # ainvoke() 异步执行整条 LCEL 链。这里传入的 Key 必须与 PromptTemplate
        # 声明的 input_variables 完全对应。
        selected_metric_names = await chain.ainvoke(
            {
                "query": query,
                "metric_infos": metric_infos_yaml,
            }
        )

        # JsonOutputParser 只能保证输出是合法 JSON，不能保证顶层结构一定是
        # list[str]。如果模型返回字典、数字或混合类型，立即报告清晰错误，
        # 避免后面的成员判断产生含义模糊的过滤结果。
        if not isinstance(selected_metric_names, list) or not all(
            isinstance(metric_name, str) for metric_name in selected_metric_names
        ):
            raise ValueError("指标过滤模型必须返回由指标名称组成的 JSON 字符串数组")

        # LLM 只返回“选择哪些指标的名称”，程序再从原始 metric_infos 中过滤。
        # 这样可以保留 Meta MySQL 提供的完整、可信结构，包括：
        #
        # - description：指标业务口径；
        # - relevant_columns：指标依赖字段；
        # - alias：指标别名。
        #
        # 即使模型擅自返回候选集合之外的名称，也不会凭空创建新指标；不存在的
        # 名称在这一步会自然被忽略。
        selected_metric_name_set = set(selected_metric_names)
        filtered_metric_infos = [
            metric_info
            for metric_info in metric_infos
            if metric_info["name"] in selected_metric_name_set
        ]

        logger.info(
            "指标过滤成功，保留指标: "
            f"{[metric_info['name'] for metric_info in filtered_metric_infos]}"
        )

        writer(
            {
                "type": "progress",
                "step": step,
                "status": "success",
            }
        )

        # 返回局部 State 更新。LangGraph 会用这个精简后的列表覆盖此前合并阶段
        # 产生的候选 metric_infos，但不会影响 query、table_infos 等其他字段。
        return {"metric_infos": filtered_metric_infos}

    except Exception as error:
        # Prompt 加载、LLM 调用、JSON 解析或输出结构校验任一步失败，都不能把
        # “未知结果”伪装成空指标集合，否则后续 SQL 可能悄悄丢失业务指标口径。
        logger.error(f"{step}失败: {error}")
        writer(
            {
                "type": "progress",
                "step": step,
                "status": "error",
            }
        )
        raise
