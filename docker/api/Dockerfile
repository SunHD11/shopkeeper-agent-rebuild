# syntax=docker/dockerfile:1

FROM python:3.13-slim-bookworm

# uv 官方建议复制固定版本二进制，避免每次构建得到不同工具版本。
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# 依赖层只在锁文件变化时重建，日常代码改动可以复用这一层。
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# 当前项目不是需要安装的 Python 包，运行时只复制明确需要的源代码和配置。
COPY app ./app
COPY conf ./conf
COPY prompts ./prompts
COPY main.py ./main.py

# API 进程不使用 root；logs 是唯一需要写权限的应用目录。
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin shopkeeper \
    && mkdir -p /app/logs \
    && chown -R shopkeeper:shopkeeper /app/logs

USER shopkeeper

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=12 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
