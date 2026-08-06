"""
Prompt 模板加载工具。

这个模块负责从项目根目录下的 prompts 文件夹中，
读取指定名称的 .prompt 提示词文件。

例如：

    load_prompt("generate_sql")

实际读取的是：

    项目根目录/prompts/generate_sql.prompt
"""

# Path 是 Python 标准库提供的路径处理工具。
#
# 使用 Path 的好处是：
# 1. 不需要手动拼接 "/" 或 "\\"
# 2. 同时兼容 Windows、Linux 和 macOS
# 3. 可以方便地获取当前文件的父目录
from pathlib import Path


def load_prompt(name: str) -> str:
    """
    根据提示词名称读取对应的 .prompt 文件。

    参数：
        name:
            提示词文件的逻辑名称，不包含“.prompt”扩展名。

            例如：

                load_prompt("generate_sql")

            而不是：

                load_prompt("generate_sql.prompt")

    返回：
        .prompt 文件中的完整文本内容。

    异常：
        如果对应的提示词文件不存在，
        Path.read_text() 会自动抛出 FileNotFoundError。

    示例：
        prompt_text = load_prompt(
            "extend_keywords_for_column_recall"
        )
    """

    # __file__ 表示当前 Python 文件本身的路径。
    #
    # 假设当前文件位于：
    #
    # shopkeeper-agent-rebuild/
    # └── app/
    #     └── prompt/
    #         └── prompt_loader.py
    #
    # Path(__file__) 得到：
    #
    # .../app/prompt/prompt_loader.py
    #
    # 它的父目录关系如下：
    #
    # parents[0] -> .../app/prompt
    # parents[1] -> .../app
    # parents[2] -> .../shopkeeper-agent-rebuild
    #
    # 所以 parents[2] 就是项目根目录。
    project_root = Path(__file__).parents[2]

    # 找到项目根目录下面的 prompts 文件夹。
    #
    # 得到：
    #
    # .../shopkeeper-agent-rebuild/prompts
    prompt_directory = project_root / "prompts"

    # 根据传入的 name 拼出完整提示词文件名。
    #
    # 如果：
    #
    # name = "generate_sql"
    #
    # 那么：
    #
    # f"{name}.prompt" = "generate_sql.prompt"
    #
    # 最终得到：
    #
    # .../prompts/generate_sql.prompt
    prompt_path = prompt_directory / f"{name}.prompt"

    # 使用 UTF-8 编码读取提示词文件。
    #
    # 这里必须明确写 encoding="utf-8"，
    # 因为提示词中包含大量中文。
    #
    # 如果不指定编码，在不同操作系统上可能使用不同的默认编码，
    # 从而出现中文乱码或 UnicodeDecodeError。
    #
    # read_text() 返回文件的完整字符串内容。
    return prompt_path.read_text(encoding="utf-8")
