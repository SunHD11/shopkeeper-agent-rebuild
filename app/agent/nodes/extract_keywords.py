"""
关键词抽取节点。

这个节点负责从用户的自然语言问题中提取适合检索的公共关键词。

它是在线 RAG 检索链路的第一个节点：

    用户问题
        ↓
    extract_keywords
        ↓
    keywords
        ↓
    recall_column / recall_metric / recall_value

本节点只负责关键词抽取：

- 不调用大模型；
- 不查询 MySQL；
- 不查询 Qdrant；
- 不查询 Elasticsearch；
- 不执行 SQL。

抽取出的关键词会写入 DataAgentState，
供后续三条召回链共同使用。
"""

# jieba.analyse 提供基于 TF-IDF、TextRank 等算法的关键词抽取功能。
#
# 当前项目使用 extract_tags()，也就是 TF-IDF 关键词抽取。
import jieba.analyse

# Runtime 是 LangGraph 提供的节点运行时对象。
#
# 节点可以通过它访问：
#
# runtime.context
#     获取 DataAgentContext 中的 Repository 和客户端。
#
# runtime.stream_writer
#     向 QueryService 和前端发送当前节点的执行进度。
from langgraph.runtime import Runtime

# DataAgentContext 描述节点可以使用哪些外部工具。
#
# 当前 extract_keywords 节点不需要访问 Repository，
# 但仍保持与其他节点一致的 Runtime 类型定义。
from app.agent.context import DataAgentContext

# DataAgentState 描述本节点读取和写入的数据结构。
#
# 本节点读取：
#
#     state["query"]
#
# 本节点返回：
#
#     {
#         "keywords": [...]
#     }
from app.agent.state import DataAgentState

# 使用项目统一的 logger 记录关键词结果和异常。
from app.core.log import logger


async def extract_keywords(
    state: DataAgentState,
    runtime: Runtime[DataAgentContext],
) -> dict[str, list[str]]:
    """
    从用户原始问题中抽取公共检索关键词。

    参数：
        state：
            当前 LangGraph 状态。

            本节点要求其中已经存在：

                state["query"]

        runtime：
            当前节点的 LangGraph 运行环境。

            本节点主要使用：

                runtime.stream_writer

            向调用方输出执行进度。

    返回：
        只包含 keywords 的局部 State 更新。

        例如：

            {
                "keywords": [
                    "华东",
                    "销售总额",
                    "查询华东地区的销售总额",
                ]
            }

        LangGraph 会把这个返回值合并进原 State，
        节点不需要自行修改或返回整份 State。

    异常：
        如果关键词抽取失败：

        1. 记录错误日志；
        2. 发送 error 进度事件；
        3. 继续向上抛出异常；
        4. 终止后续召回流程。
    """

    # stream_writer 用来向 QueryService 或前端发送自定义流式消息。
    #
    # 节点不直接关心这些消息最终如何通过 FastAPI 返回，
    # 只需要按照统一格式写出执行进度。
    writer = runtime.stream_writer

    # step 是用户能够看到的节点名称。
    #
    # 后面的 running、success 和 error 事件都使用同一个 step，
    # 前端可以根据它更新对应步骤的状态。
    step = "抽取关键词"

    # 节点开始执行时，先发出 running 事件。
    #
    # QueryService 将来会把它包装成 SSE：
    #
    # data: {
    #     "type": "progress",
    #     "step": "抽取关键词",
    #     "status": "running"
    # }
    writer(
        {
            "type": "progress",
            "step": step,
            "status": "running",
        }
    )

    try:
        # 用户原始自然语言问题来自 QueryService 创建的初始 State。
        #
        # 例如：
        #
        # 查询华东地区最近三个月的销售总额
        query = state["query"]

        # allow_pos 表示 Jieba 抽取关键词时允许保留哪些词性。
        #
        # 这样可以过滤掉：
        #
        # 的、了、一下、帮我、请问
        #
        # 这些通常没有业务检索价值的词。
        allow_pos = (
            # 普通名词。
            #
            # 例如：
            # 商品、订单、地区、金额
            "n",
            # 人名。
            #
            # 某些业务问题可能按员工、客户或销售人员查询。
            "nr",
            # 地名。
            #
            # 例如：
            # 华东、北京、上海
            "ns",
            # 机构或组织名称。
            #
            # 例如：
            # 门店、公司、渠道
            "nt",
            # 其他专有名词。
            #
            # 例如：
            # SKU、GMV、AOV
            "nz",
            # 动词。
            #
            # 例如：
            # 查询、统计、对比
            "v",
            # 名动词。
            #
            # 既具有名词性质，也具有动词性质。
            #
            # 例如：
            # 销售、成交、退款
            "vn",
            # 形容词。
            #
            # 例如：
            # 新增、有效、活跃
            "a",
            # 名形词。
            #
            # 例如：
            # 可用、有效、异常
            "an",
            # 英文。
            #
            # 例如：
            # GMV、SKU、ROI
            "eng",
            # 成语或习用语。
            #
            # 保留整体表达，避免拆分后丢失语义。
            "i",
            # 固定短语。
            #
            # 例如：
            # 销售总额、客单价
            "l",
        )

        # extract_tags() 使用 TF-IDF 算法提取关键词。
        #
        # 输入：
        #
        #     查询华东地区最近三个月的销售总额
        #
        # 可能返回：
        #
        #     [
        #         "华东",
        #         "地区",
        #         "销售总额",
        #     ]
        #
        # allowPOS 用于限制只保留上面指定的词性。
        keywords = jieba.analyse.extract_tags(
            query,
            allowPOS=allow_pos,
        )

        # 把完整原始问题加入关键词集合。
        #
        # 这样做非常重要，因为 Jieba 的分词和关键词抽取不一定完全符合业务语义。
        #
        # 例如：
        #
        #     销售总额
        #
        # 可能被拆成：
        #
        #     销售
        #     总额
        #
        # 单独检索两个词可能无法准确召回 GMV。
        #
        # 保留完整问题后，后续向量召回仍然可以利用整句话的语义。
        keywords.append(query)

        # 使用 set 去除重复关键词。
        #
        # 例如 extract_tags() 已经返回了完整问题时，
        # 再 append(query) 会重复，set 可以将它们合并。
        #
        # set 不保证顺序，但原项目后续只使用关键词执行检索，
        # 不依赖关键词排列顺序。
        keywords = list(set(keywords))

        # 关键词抽取完成后发送成功事件。
        writer(
            {
                "type": "progress",
                "step": step,
                "status": "success",
            }
        )

        # 记录关键词，方便调试召回效果。
        #
        # 如果后面字段或指标没有召回，可以先从日志中确认：
        #
        # - 用户问题是否正确进入节点；
        # - Jieba 抽取了哪些关键词；
        # - 完整问题是否被保留。
        logger.info(f"抽取关键词成功: {keywords}")

        # 节点只返回自己负责更新的字段。
        #
        # LangGraph 会把它合并到已有 State：
        #
        # {
        #     "query": "...",
        #     "keywords": [...]
        # }
        return {
            "keywords": keywords,
        }

    except Exception as error:
        # 捕获本节点中的任何异常并记录详细错误。
        #
        # 例如：
        #
        # - query 不存在；
        # - query 不是字符串；
        # - Jieba 抽取过程异常。
        logger.error(f"抽取关键词失败: {error}")

        # 告诉流式调用方这个节点执行失败。
        writer(
            {
                "type": "progress",
                "step": step,
                "status": "error",
            }
        )

        # 不能悄悄返回空关键词。
        #
        # 如果吞掉异常并返回：
        #
        #     {"keywords": []}
        #
        # 后面的三路召回仍会继续执行，最终可能生成缺少上下文的错误 SQL，
        # 反而更难定位真正的问题。
        raise
