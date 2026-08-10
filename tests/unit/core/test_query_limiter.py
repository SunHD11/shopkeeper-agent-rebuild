"""测试进程内问数并发槽位。"""

import pytest

from app.core.query_limiter import QueryLimiter


def test_query_limiter_rejects_invalid_limit() -> None:
    with pytest.raises(ValueError, match="大于 0"):
        QueryLimiter(0)


async def test_query_limiter_acquires_rejects_and_reuses_slot() -> None:
    limiter = QueryLimiter(limit=1)

    assert await limiter.try_acquire() is True
    assert limiter.active == 1
    assert await limiter.try_acquire() is False

    await limiter.release()
    assert limiter.active == 0
    assert await limiter.try_acquire() is True
    await limiter.release()


async def test_query_limiter_rejects_duplicate_release() -> None:
    limiter = QueryLimiter(limit=1)

    with pytest.raises(RuntimeError, match="重复释放"):
        await limiter.release()
