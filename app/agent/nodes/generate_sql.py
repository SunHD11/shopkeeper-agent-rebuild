"""
候选 SQL 生成节点。

本节点把前面准备完成的用户问题、表字段结构、指标口径、日期信息和数据库
环境交给 LLM，生成一条只读候选 SQL。它只负责“生成”，不会在这里校验或
执行 SQL；候选结果会继续交给 ``validate_sql`` 使用真实 DW MySQL 检查。
"""

import yaml
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def generate_sql(
    state: DataAgentState,
    runtime: Runtime[DataAgentContext],
) -> dict[str, str]:
    """根据已检索、补齐和过滤的可信上下文生成候选 SQL。"""

    writer = runtime.stream_writer
    step = "生成SQL"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        # 这些字段分别由前置节点准备：
        # merge/filter -> table_infos、metric_infos
        # add_extra_context -> date_info、db_info
        # 初始请求 -> query
        table_infos = state["table_infos"]
        metric_infos = state["metric_infos"]
        date_info = state["date_info"]
        db_info = state["db_info"]
        query = state["query"]

        # generate_sql.prompt 明确约束模型只能使用给定 Schema、只能生成一条
        # 查询 SQL、遵循指标口径与数据库方言，并且不能输出 Markdown 代码块。
        prompt = PromptTemplate(
            template=load_prompt("generate_sql"),
            input_variables=[
                "table_infos",
                "metric_infos",
                "date_info",
                "db_info",
                "query",
            ],
        )

        # SQL 是纯文本，不需要 JSON 结构，因此使用 StrOutputParser。
        # LCEL 管道负责：填充 Prompt -> 调用 LLM -> 提取消息文本。
        output_parser = StrOutputParser()
        chain = prompt | llm | output_parser

        # YAML 能稳定表达嵌套的表字段和指标结构，并保留中文、字段顺序。
        # query 本身是自然语言字符串，无需转换。
        generated_sql = await chain.ainvoke(
            {
                "table_infos": yaml.dump(
                    table_infos,
                    allow_unicode=True,
                    sort_keys=False,
                ),
                "metric_infos": yaml.dump(
                    metric_infos,
                    allow_unicode=True,
                    sort_keys=False,
                ),
                "date_info": yaml.dump(
                    date_info,
                    allow_unicode=True,
                    sort_keys=False,
                ),
                "db_info": yaml.dump(
                    db_info,
                    allow_unicode=True,
                    sort_keys=False,
                ),
                "query": query,
            }
        )

        # 去除模型可能附带的首尾空白。空输出不能交给数据库 EXPLAIN，
        # 所以在生成节点立即给出清晰错误。
        sql = generated_sql.strip()
        if not sql:
            raise ValueError("SQL 生成模型返回了空内容")

        logger.info(f"生成的 SQL: {sql}")
        writer({"type": "progress", "step": step, "status": "success"})

        # 只返回自己负责更新的 sql，LangGraph 会保留其他 State 字段。
        return {"sql": sql}

    except Exception as error:
        logger.error(f"{step}失败: {error}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
