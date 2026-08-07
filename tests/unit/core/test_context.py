"""Unit tests for request-local context restoration."""

from app.core.context import request_context, request_id_ctx_var


def test_request_context_restores_previous_value() -> None:
    assert request_id_ctx_var.get() == "system"
    with request_context("test-request") as request_id:
        assert request_id == "test-request"
        assert request_id_ctx_var.get() == "test-request"
    assert request_id_ctx_var.get() == "system"
