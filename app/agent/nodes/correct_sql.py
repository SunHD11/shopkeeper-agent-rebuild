"""
SQL 错误修正节点。

当 ``validate_sql`` 把数据库错误写入 ``state["error"]`` 后，LangGraph 条件边
才会进入本节点。模型同时看到原始问题、可信 Schema、指标口径、日期环境、
原 SQL 和数据库错误，从而进行保持业务语义不变的最小必要修正。
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


async def correct_sql(
    state: DataAgentState,
    runtime: Runtime[DataAgentContext],
) -> dict[str, str]:
    """根据数据库校验错误修正候选 SQL，并覆盖 State 中的 sql。"""

    writer = runtime.stream_writer
    step = "校正SQL"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        table_infos = state["table_infos"]
        metric_infos = state["metric_infos"]
        date_info = state["date_info"]
        db_info = state["db_info"]
        query = state["query"]
        sql = state["sql"]
        error = state["error"]

        # 正常图编排只会在 error 非空时进入本节点。显式检查可以尽早发现
        # 条件边配置错误或手动调用时遗漏校验结果的问题。
        if error is None or not error.strip():
            raise ValueError("SQL 修正节点需要非空的数据库校验错误")

        prompt = PromptTemplate(
            template=load_prompt("correct_sql"),
            input_variables=[
                "table_infos",
                "metric_infos",
                "date_info",
                "db_info",
                "query",
                "sql",
                "error",
            ],
        )

        # 修正结果仍是一条纯 SQL 文本，不让模型返回 JSON 或 Markdown。
        output_parser = StrOutputParser()
        chain = prompt | llm | output_parser

        corrected_sql = await chain.ainvoke(
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
                "sql": sql,
                "error": error,
            }
        )

        result = corrected_sql.strip()
        if not result:
            raise ValueError("SQL 修正模型返回了空内容")

        logger.info(f"校正后的 SQL: {result}")
        writer({"type": "progress", "step": step, "status": "success"})

        # 相同 State Key 会被 LangGraph 覆盖，所以后续 run_sql 读取到的是
        # 修正后的 SQL，而不是最初 generate_sql 生成的版本。
        return {"sql": result}

    except Exception as error:
        logger.error(f"{step}失败: {error}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
