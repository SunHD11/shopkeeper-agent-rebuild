"""
Prompt 模板加载工具。

按名称从项目根目录的 prompts 目录读取 .prompt 文件。
业务节点只需要传入逻辑名称，不需要关心提示词文件的具体路径。
"""

from pathlib import Path


def load_prompt(name: str) -> str:
    """读取指定名称的 Prompt 模板内容。"""

    # 当前文件位于 app/prompt/prompt_loader.py。
    # parents[2] 会从当前文件向上两级回到项目根目录，
    # 然后进入 prompts 目录，并为逻辑名称补充 .prompt 后缀。
    prompt_path = Path(__file__).parents[2] / "prompts" / f"{name}.prompt"

    # Prompt 中包含中文，因此明确使用 UTF-8 编码读取。
    # 文件不存在时 read_text() 会自然抛出 FileNotFoundError，
    # 方便调用方及时发现 Prompt 名称拼写错误。
    return prompt_path.read_text(encoding="utf-8")
