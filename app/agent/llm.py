"""
电商问数 Agent 共用的大模型实例。

这个模块负责根据应用配置集中创建一个 OpenAI 协议兼容的 Chat Model，
字段召回、指标召回、字段值召回、候选过滤、SQL 生成和 SQL 修正节点
都从这里导入同一个 ``llm`` 对象，而不是在每个节点中重复初始化模型。

导入本模块只会创建模型客户端对象，不会立即向远端发送请求；
只有节点调用 ``llm.invoke()`` 或 ``llm.ainvoke()`` 时才会真正访问模型服务。
"""

# init_chat_model 是 LangChain 提供的统一聊天模型初始化入口。
#
# 相比直接实例化某个厂商的模型类，它允许项目通过 model_provider、base_url
# 和 api_key 接入实现 OpenAI Chat Completions 协议的服务。这样上层 Agent 节点
# 只依赖统一的 LangChain Chat Model 接口，不需要了解具体模型供应商 SDK。
from langchain.chat_models import init_chat_model

from app.conf.app_config import app_config

# 在模块级集中创建模型对象，后续节点只需要：
#
#     from app.agent.llm import llm
#
# 就可以复用相同的模型名称、服务地址、认证信息和生成参数。
llm = init_chat_model(
    # 模型名称来自 conf/app_config.yaml：
    #
    #     llm:
    #       model_name: Pro/zai-org/GLM-5.1
    #
    # 将模型选择留在配置层，切换模型时不需要修改字段召回或 SQL 节点代码。
    model=app_config.llm.model_name,
    # 当前配置的硅基流动服务提供 OpenAI 兼容接口，因此使用 openai provider。
    # 这里描述的是通信协议/适配器，不代表模型本身一定由 OpenAI 提供。
    model_provider="openai",
    # OpenAI 兼容服务的 API 根地址，例如：
    #
    #     https://api.siliconflow.cn/v1
    #
    # LangChain 会在这个地址之上调用对应的 Chat Completions 接口。
    base_url=app_config.llm.base_url,
    # API Key 来自 .env 中的 LLM_API_KEY，并通过 app_config 统一读取。
    # LLMConfig 使用 field(repr=False)，可以减少配置对象被打印时泄漏密钥的风险。
    # 代码中不要硬编码真实 Key，也不要在日志和测试输出中打印它。
    api_key=app_config.llm.api_key,
    # temperature 控制模型输出的随机程度。
    #
    # 当前 Agent 的输出需要可解析、可执行且尽可能稳定：
    #
    # - 关键词扩展 Prompt 要求返回 JSON 数组；
    # - 过滤 Prompt 要求返回严格的 JSON 对象或数组；
    # - SQL Prompt 要求只返回一条纯 SQL；
    # - SQL 修正需要保持原始业务语义不变。
    #
    # 因此按原项目设置为 0，减少无关发散和相同输入下的随机差异。
    temperature=0,
)


if __name__ == "__main__":
    # 直接执行下面命令时，可以对 LLM 配置做一次最小人工连通性验证：
    #
    #     uv run python -m app.agent.llm
    #
    # 只有直接运行本文件时才会真正请求模型服务；正常 import 不会执行这里。
    # 该验证需要有效的 LLM_API_KEY 和可访问的网络，并可能产生少量调用费用。
    print(llm.invoke("你好").content)
