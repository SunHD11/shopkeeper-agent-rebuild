"""
关键词抽取节点。

负责从用户自然语言问题中抽取公共检索关键词，并写入 DataAgentState。
后续字段、指标和字段值三路召回都会以这些关键词作为基础检索入口。

本节点只进行本地文本处理，不调用大模型，也不访问任何数据库。
"""

# jieba.analyse.extract_tags() 使用 TF-IDF 从中文文本中抽取关键词。
import jieba.analyse

# Runtime 提供 LangGraph 节点执行时的上下文和自定义流式消息 Writer。
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger


async def extract_keywords(
    state: DataAgentState,
    runtime: Runtime[DataAgentContext],
) -> dict[str, list[str]]:
    """从用户原始问题中抽取公共关键词，并返回局部 State 更新。"""

    # 节点通过 stream_writer 报告执行进度。
    # QueryService 后续会把这些字典包装成 SSE 消息，供前端实时展示。
    writer = runtime.stream_writer
    step = "抽取关键词"

    # 进入节点时先发送 running；无论后面成功还是失败，前端都能知道
    # 这个步骤已经真正开始，而不是仍在等待 Graph 调度。
    writer(
        {
            "type": "progress",
            "step": step,
            "status": "running",
        }
    )

    try:
        # QueryService 创建初始 DataAgentState 时写入用户原始问题。
        # 本节点只读取 query，不直接修改传入的 state。
        query = state["query"]

        # 只保留更可能承载业务语义的词性，减少“的、帮我、一下”等
        # 对检索没有帮助的虚词和口语噪声。
        allow_pos = (
            "n",  # 普通名词：商品、订单、金额
            "nr",  # 人名：员工、客户或销售人员姓名
            "ns",  # 地名：华东、北京、上海
            "nt",  # 机构团体名：门店、品牌、渠道
            "nz",  # 其他专有名词：SKU、GMV、AOV
            "v",  # 动词：查询、统计、对比
            "vn",  # 名动词：销售、成交、退款
            "a",  # 形容词：新增、活跃、异常
            "an",  # 名形词：有效、可用
            "eng",  # 英文业务缩写：GMV、SKU、ROI
            "i",  # 成语或习用语
            "l",  # 固定短语：销售总额、客单价
        )

        # extract_tags() 使用 TF-IDF 返回关键词列表。
        # allowPOS 让 Jieba 只保留上面声明的业务相关词性。
        keywords = jieba.analyse.extract_tags(
            query,
            allowPOS=allow_pos,
        )

        # 完整原始问题必须作为兜底检索入口保留。
        # 即使 Jieba 把“销售总额”拆成“销售”和“总额”，后续向量召回仍能
        # 使用整句话捕获完整语义。set 同时去掉重复关键词。
        #
        # 原项目不依赖关键词顺序，因此这里忠实使用 list(set(...))；
        # 单元测试也会比较集合，而不是绑定某一种随机排列。
        keywords = list(set(keywords + [query]))

        writer(
            {
                "type": "progress",
                "step": step,
                "status": "success",
            }
        )
        logger.info(f"抽取关键词成功: {keywords}")

        # 节点只返回自己负责的局部更新。
        # LangGraph 会把 keywords 合并进原本只包含 query 的 State。
        return {"keywords": keywords}

    except Exception as error:
        # 抽取失败时不能返回空列表继续运行，否则三路召回会在缺少检索入口的
        # 情况下产生误导结果。记录错误、发送 error 事件后继续向上抛出。
        logger.error(f"抽取关键词失败: {error}")
        writer(
            {
                "type": "progress",
                "step": step,
                "status": "error",
            }
        )
        raise
