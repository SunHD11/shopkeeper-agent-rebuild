"""
电商问数 Agent 的状态结构定义。

State 是 LangGraph 各个节点之间共享和传递的数据。

一次问数流程开始时，State 通常只有用户原始问题 ``query``；随后关键词抽取、
多路召回、元数据合并、上下文补全、SQL 生成和 SQL 校验节点会分别返回局部字典，
LangGraph 再把这些局部结果逐步合并到同一份 State 中。

这个文件只定义“数据长什么样”，不负责调用大模型、查询数据库或执行 SQL。
外部客户端和 Repository 会放在 ``DataAgentContext`` 中，而不是放进 State。
"""

from typing import TypedDict

from app.entities.column_info import ColumnInfo
from app.entities.metric_info import MetricInfo
from app.entities.value_info import ValueInfo


class MetricInfoState(TypedDict):
    """面向指标过滤和 SQL 生成提示词的指标上下文。"""

    # 指标的标准业务名称，例如 GMV。
    # filter_metric 节点会根据这个名称保留用户真正需要的指标。
    name: str

    # 指标的业务含义和统计口径。
    # SQL 生成节点会把它交给大模型，避免模型仅凭指标名称自由猜测算法。
    description: str

    # 指标依赖的真实字段 id，例如 ["fact_order.order_amount"]。
    # merge_retrieved_info 会根据这些 id 从 Meta MySQL 补齐未被向量检索命中的字段。
    relevant_columns: list[str]

    # 指标的同义表达，例如 GMV 的别名可以是“成交总额”和“订单总额”。
    # 它帮助模型理解用户用不同说法表达的同一个业务指标。
    alias: list[str]


class ColumnInfoState(TypedDict):
    """面向表过滤和 SQL 生成提示词的字段上下文。"""

    # DW MySQL 中真实存在的字段名，例如 order_amount。
    # 最终生成的 SQL 只能使用这里提供的真实名称。
    name: str

    # 从 DW MySQL 表结构读取到的真实字段类型，例如 float、varchar(64)。
    # 它帮助模型判断比较、聚合以及日期处理方式。
    type: str

    # 字段的业务角色，例如 dimension、measure、primary_key 或 foreign_key。
    # 角色信息可以帮助模型区分分组字段、度量字段和表关联字段。
    role: str

    # 字段的真实样例值。
    # 既可以来自离线构建阶段采样，也可以由字段值召回结果补充；
    # 例如 region_name 的 examples 可以包含“华东”，用于辅助生成 WHERE 条件。
    # 不限定元素类型，是因为样例可能是字符串、数字、日期等不同类型。
    examples: list

    # 字段的中文业务说明，例如“订单最终成交金额”。
    # 它负责连接用户自然语言和数据库物理字段名。
    description: str

    # 字段的业务别名，例如 order_amount 可以对应“销售额”“成交金额”。
    alias: list[str]


class TableInfoState(TypedDict):
    """SQL 生成阶段使用的表结构上下文。"""

    # DW MySQL 中真实存在的表名，例如 fact_order。
    name: str

    # 表的业务角色，例如 fact 或 dimension。
    # 它帮助模型识别事实表、维度表以及可能的 JOIN 方向。
    role: str

    # 表的业务说明，例如“记录订单金额、数量和关联维度的订单事实表”。
    description: str

    # 当前查询可能需要使用的字段列表。
    # Meta MySQL 中表和字段通过 table_id 分开保存；merge_retrieved_info 节点
    # 会把它们重新组装成“表 -> 字段列表”的嵌套结构，方便提示词和大模型阅读。
    columns: list[ColumnInfoState]


class DateInfoState(TypedDict):
    """SQL 生成阶段使用的当前日期上下文。"""

    # 当前日期，格式通常为 YYYY-MM-DD。
    # 它是解释“今天”“本月”“最近三个月”等相对时间表达的计算基准。
    date: str

    # 当前星期，例如 Monday、Thursday。
    # 后续如果用户询问“本周”或“工作日”，模型可以结合该信息计算范围。
    weekday: str

    # 当前季度，例如 Q1、Q2、Q3 或 Q4。
    # 它用于辅助解释“本季度”“上季度”等自然语言时间条件。
    quarter: str


class DBInfoState(TypedDict):
    """SQL 生成阶段使用的目标数据库环境信息。"""

    # 数据库方言，例如 mysql。
    # 不同方言在日期函数、字符串函数和分页语法等方面存在差异。
    dialect: str

    # 数据库版本，例如 8.0.36。
    # 某些 SQL 函数或特性只在特定版本中可用，因此版本也是生成 SQL 的约束。
    version: str


class DataAgentState(TypedDict):
    """一次自然语言问数工作流中由所有 LangGraph 节点共享的总状态。"""

    # ------------------------- 1. 用户输入 -------------------------

    # 用户提交的原始自然语言问题。
    # QueryService 创建初始 State 时通常只写入这个字段，后续节点再逐步补齐其他字段。
    query: str

    # ----------------------- 2. 关键词抽取 -------------------------

    # extract_keywords 节点从 query 中抽取出的通用检索关键词。
    # recall_column、recall_metric 和 recall_value 三个节点都会读取它，
    # 并分别结合各自的 LLM 扩展词执行多路召回。
    keywords: list[str]

    # ----------------------- 3. 三路召回结果 -----------------------

    # recall_column 从字段 Qdrant Collection 召回并去重后的字段业务实体。
    # 这里保存 ColumnInfo，而不是 Qdrant 原始 Point，让后续节点只依赖业务模型。
    retrieved_column_infos: list[ColumnInfo]

    # recall_metric 从指标 Qdrant Collection 召回并去重后的指标业务实体。
    retrieved_metric_infos: list[MetricInfo]

    # recall_value 从 Elasticsearch 字段值索引召回并去重后的字段值业务实体。
    # merge_retrieved_info 会根据 ValueInfo.column_id 定位字段，并把真实 value
    # 补充进对应 ColumnInfoState 的 examples。
    retrieved_value_infos: list[ValueInfo]

    # -------------------- 4. 合并后的提示词上下文 ------------------

    # merge_retrieved_info 把三路召回结果按照表进行组织后的候选表结构；
    # filter_table 随后会删除与当前问题无关的表和字段，并把结果写回同一个字段。
    table_infos: list[TableInfoState]

    # merge_retrieved_info 整理出的候选指标上下文；
    # filter_metric 会筛掉当前问题不需要的指标，并把结果写回同一个字段。
    metric_infos: list[MetricInfoState]

    # add_extra_context 根据当前系统日期生成的时间上下文。
    date_info: DateInfoState

    # add_extra_context 通过 DW Repository 获取的数据库方言和版本信息。
    db_info: DBInfoState

    # ----------------------- 5. SQL 处理闭环 -----------------------

    # generate_sql 生成的候选 SQL。
    # 如果校验失败，correct_sql 会返回修正后的 SQL，并覆盖这个字段；
    # validate_sql 和 run_sql 都从这里读取当前最新的 SQL。
    sql: str

    # validate_sql 使用 DW MySQL 校验 SQL 后写入的结果：
    # - 校验成功时为 None，Graph 会进入 run_sql；
    # - 校验失败时为数据库错误字符串，Graph 会进入 correct_sql。
    # 原项目标注为 str，但实际成功分支会返回 None，因此这里使用联合类型表达真实状态。
    error: str | None
