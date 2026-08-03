"""Request-local context shared by logs and later API handlers."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="system")


@contextmanager
def request_context(request_id: str | None = None) -> Iterator[str]:
    """Set a request ID for the current context and reliably restore the old one."""

    current_request_id = request_id or str(uuid.uuid4())
    token = request_id_ctx_var.set(current_request_id)
    try:
        yield current_request_id
    finally:
        request_id_ctx_var.reset(token)
