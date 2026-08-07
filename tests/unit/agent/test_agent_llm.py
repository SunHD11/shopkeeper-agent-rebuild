"""测试在线问数 Agent 的统一大模型初始化模块。"""

import importlib
import sys
from collections.abc import Iterator
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
from langchain import chat_models


@pytest.fixture
def mocked_llm_module(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[ModuleType, Mock, Mock, SimpleNamespace]]:
    """在隔离真实模型调用的条件下重新导入 app.agent.llm。"""

    # app.agent.llm 在模块导入时调用 init_chat_model() 创建全局 llm。
    # 因此必须先替换 LangChain 初始化函数，再导入被测模块；如果直接在文件顶部
    # import app.agent.llm，真实客户端会在 Mock 生效之前创建，测试也就失去意义。
    fake_llm = Mock(name="fake_llm")
    mock_init_chat_model = Mock(
        name="init_chat_model",
        return_value=fake_llm,
    )
    monkeypatch.setattr(
        chat_models,
        "init_chat_model",
        mock_init_chat_model,
    )

    module_name = "app.agent.llm"
    config_module_name = "app.conf.app_config"

    # llm.py 只需要 app_config.llm 下的三个字段。
    # 使用假配置可以让单元测试不读取 .env、不接触真实 API Key，
    # 也不会受其他基础服务配置是否正在重构的影响。
    fake_app_config = SimpleNamespace(
        llm=SimpleNamespace(
            model_name="test-chat-model",
            base_url="https://llm.example.test/v1",
            api_key="test-api-key",
        )
    )
    fake_config_module = ModuleType(config_module_name)
    fake_config_module.app_config = fake_app_config

    # 如果其他测试或交互环境曾经导入过该模块，Python 会直接使用 sys.modules
    # 缓存而不会重新执行初始化代码。这里暂时移除缓存，确保本测试真正覆盖
    # `llm = init_chat_model(...)` 这一行。
    previous_module = sys.modules.pop(module_name, None)
    previous_config_module = sys.modules.pop(config_module_name, None)
    sys.modules[config_module_name] = fake_config_module
    module = importlib.import_module(module_name)

    try:
        yield module, mock_init_chat_model, fake_llm, fake_app_config
    finally:
        # 清理本测试导入的 Mock 版本，避免它污染后续测试。
        sys.modules.pop(module_name, None)
        sys.modules.pop(config_module_name, None)
        if previous_module is not None:
            sys.modules[module_name] = previous_module
        if previous_config_module is not None:
            sys.modules[config_module_name] = previous_config_module


def test_llm_uses_the_original_project_model_configuration(
    mocked_llm_module: tuple[ModuleType, Mock, Mock, SimpleNamespace],
) -> None:
    """LLM 使用应用配置和原项目约定的 OpenAI 兼容初始化参数。"""

    _, mock_init_chat_model, _, fake_app_config = mocked_llm_module

    mock_init_chat_model.assert_called_once_with(
        # 模型名称、服务地址和密钥都来自 AppConfig，节点中不应重复硬编码。
        model=fake_app_config.llm.model_name,
        model_provider="openai",
        base_url=fake_app_config.llm.base_url,
        api_key=fake_app_config.llm.api_key,
        # 关键词扩展、JSON 过滤和 SQL 生成都要求稳定输出，
        # 因此按原项目关闭随机发散。
        temperature=0,
        # DeepSeek V4 默认开启思考模式；当前共享模型先统一使用非思考模式，
        # 保证严格结构输出和较低调用延迟。
        extra_body={
            "thinking": {
                "type": "disabled",
            }
        },
    )


def test_llm_module_exports_the_initialized_chat_model(
    mocked_llm_module: tuple[ModuleType, Mock, Mock, SimpleNamespace],
) -> None:
    """模块对外导出的 llm 就是 init_chat_model 返回的模型对象。"""

    module, _, fake_llm, _ = mocked_llm_module

    # 后续节点统一使用 `from app.agent.llm import llm`，
    # 所以模块不能再次包装、复制或替换初始化函数返回的对象。
    assert module.llm is fake_llm


def test_importing_llm_module_does_not_send_a_model_request(
    mocked_llm_module: tuple[ModuleType, Mock, Mock, SimpleNamespace],
) -> None:
    """普通 import 只创建客户端，不应调用 invoke 或产生真实模型请求。"""

    _, _, fake_llm, _ = mocked_llm_module

    # llm.invoke("你好") 只位于 `if __name__ == "__main__"` 调试入口中。
    # pytest 通过 import 加载模块时不应进入该分支。
    fake_llm.invoke.assert_not_called()
    fake_llm.ainvoke.assert_not_called()
