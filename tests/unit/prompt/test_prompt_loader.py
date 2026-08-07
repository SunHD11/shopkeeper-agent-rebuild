"""测试 Prompt 模板加载工具以及七个在线 RAG Prompt 文件。"""

from pathlib import Path

import pytest
from langchain_core.prompts import PromptTemplate

from app.prompt.prompt_loader import load_prompt

# 七个 Prompt 文件及其应该暴露给 LangChain 的模板变量。
#
# 使用集合而不是列表进行比较，是因为我们只关心变量是否完整，
# 不要求 LangChain 必须按照某种固定顺序返回变量。
PROMPT_VARIABLES = {
    "extend_keywords_for_column_recall": {"query"},
    "extend_keywords_for_metric_recall": {"query"},
    "extend_keywords_for_value_recall": {"query"},
    "filter_table_info": {"query", "table_infos"},
    "filter_metric_info": {"query", "metric_infos"},
    "generate_sql": {
        "query",
        "table_infos",
        "metric_infos",
        "date_info",
        "db_info",
    },
    "correct_sql": {
        "query",
        "table_infos",
        "metric_infos",
        "date_info",
        "db_info",
        "sql",
        "error",
    },
}


@pytest.mark.parametrize("prompt_name", PROMPT_VARIABLES)
def test_load_prompt_reads_every_online_rag_prompt(prompt_name: str) -> None:
    """七个在线 RAG Prompt 都能按逻辑名称读取到非空文本。"""

    # 调用时只传逻辑名称，不需要传 prompts/ 目录和 .prompt 后缀。
    prompt_text = load_prompt(prompt_name)

    # 每个 Prompt 都必须有实际内容，防止只创建了空文件却没有填写模板。
    assert prompt_text.strip()


def test_load_prompt_reads_chinese_with_utf8() -> None:
    """Prompt 加载器使用 UTF-8 读取中文内容，不应出现乱码。"""

    prompt_text = load_prompt("extend_keywords_for_column_recall")

    # 这段中文来自字段召回 Prompt。
    # 如果读取编码不正确，这个断言就无法通过。
    assert "数据表字段推断专家" in prompt_text
    assert "用户问题" in prompt_text


@pytest.mark.parametrize(
    ("prompt_name", "expected_variables"),
    PROMPT_VARIABLES.items(),
)
def test_prompt_exposes_the_expected_template_variables(
    prompt_name: str,
    expected_variables: set[str],
) -> None:
    """每个 Prompt 只能暴露其 Agent 节点实际需要提供的变量。"""

    prompt_text = load_prompt(prompt_name)

    # 让 LangChain 真正解析模板，而不是仅用字符串查找花括号。
    # 这也能检查 filter_table_info.prompt 中的 JSON 示例是否正确使用了
    # {{ 和 }}；如果没有转义，JSON 内容会被误识别为模板变量。
    prompt_template = PromptTemplate.from_template(prompt_text)

    assert set(prompt_template.input_variables) == expected_variables


def test_load_prompt_does_not_depend_on_current_working_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """即使程序不从项目根目录启动，也应正确定位 prompts 目录。"""

    # 模拟 API、测试脚本或命令行从其他目录启动的场景。
    monkeypatch.chdir(tmp_path)

    prompt_text = load_prompt("generate_sql")

    # 如果 load_prompt() 错误地使用了 Path("prompts/..."),
    # 切换工作目录后这里就会抛出 FileNotFoundError。
    assert "将用户的自然语言查询转换为" in prompt_text
    assert "{table_infos}" in prompt_text


def test_load_prompt_raises_file_not_found_error_for_unknown_prompt() -> None:
    """提示词名称不存在时，应向调用方暴露清晰的文件不存在错误。"""

    # 原项目没有吞掉这个异常，也没有返回空字符串。
    # 让 FileNotFoundError 继续向上传递，可以更快发现名称拼写错误。
    with pytest.raises(FileNotFoundError):
        load_prompt("prompt_that_does_not_exist")
