"""Create and safely close asynchronous MySQL engines and session factories."""

from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.conf.app_config import DBConfig, app_config


class MySQLClientManager:
    """Own one MySQL engine and its asynchronous session factory."""

    def __init__(self, config: DBConfig):
        self.config = config
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None

    def _get_url(self) -> URL:
        """Build a URL object whose string representation masks the password."""

        return URL.create(
            drivername="mysql+asyncmy",
            username=self.config.user,
            password=self.config.password,
            host=self.config.host,
            port=self.config.port,
            database=self.config.database,
            query={"charset": "utf8mb4"},
        )

    def init(self) -> None:
        """Initialize the engine once; actual connections are opened on demand."""

        if self.engine is not None:
            return
        self.engine = create_async_engine(
            self._get_url(),
            pool_size=10,
            pool_pre_ping=True,
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            autoflush=True,
            expire_on_commit=False,
        )

    def require_session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Return the initialized factory or explain the lifecycle mistake."""

        if self.session_factory is None:
            raise RuntimeError("MySQLClientManager.init() must be called first")
        return self.session_factory

    def require_engine(self) -> AsyncEngine:
        """返回已初始化 Engine，供 readiness 等应用级探测复用。"""

        if self.engine is None:
            raise RuntimeError("MySQLClientManager.init() must be called first")
        return self.engine

    async def close(self) -> None:
        """Dispose the pool safely, even when called more than once."""

        if self.engine is not None:
            await self.engine.dispose()
        self.engine = None
        self.session_factory = None


meta_mysql_client_manager = MySQLClientManager(app_config.db_meta)
dw_mysql_client_manager = MySQLClientManager(app_config.db_dw)
