"""进程内在线问数并发保护。"""

import asyncio


class QueryLimiter:
    """以非阻塞方式限制同时运行的 LangGraph 数量。"""

    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("并发上限必须大于 0")
        self.limit = limit
        self._active = 0
        self._lock = asyncio.Lock()

    @property
    def active(self) -> int:
        """返回当前已占用槽位数，主要用于监控和测试。"""

        return self._active

    async def try_acquire(self) -> bool:
        """有空位时立即占用；满载时返回 False，不让请求排队耗尽连接。"""

        async with self._lock:
            if self._active >= self.limit:
                return False
            self._active += 1
            return True

    async def release(self) -> None:
        """释放一个槽位；重复释放属于编程错误。"""

        async with self._lock:
            if self._active == 0:
                raise RuntimeError("QueryLimiter 槽位不能重复释放")
            self._active -= 1
