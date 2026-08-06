"""
数仓 MySQL Repository。

这一层负责访问真实 DW MySQL，读取配置文件中没有维护的技术事实，
例如字段类型、字段示例值和数据库版本。

它还负责后续问数流程中的 SQL 校验和最终 SQL 执行。
Service 只需要说明“需要什么数据”，不需要知道具体 SQL 怎样编写。

它告诉系统：
数据库真实有什么表和字段；
字段真实类型是什么；
字段真实数据长什么样；
最终 SQL 查询结果是什么。
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class DWMySQLRepository:
    """负责查询 DW MySQL 中的真实表结构和业务数据。"""

    def __init__(self, session: AsyncSession):
        """
        保存外部传入的异步数据库 Session。

        Repository 不负责创建 Session。
        Session 由 dw_mysql_client_manager 创建，
        再通过构造方法注入 Repository。
        """
        self.session = session

    async def get_column_types(
        self,
        table_name: str,
    ) -> dict[str, str]:
        """
        查询一张 DW 表的全部字段类型。

        参数：
            table_name：DW 中的真实表名，例如 fact_order。

        返回：
            以字段名为 Key、MySQL 字段类型为 Value 的字典，例如：

            {
                "order_id": "varchar(64)",
                "order_amount": "decimal(10,2)",
            }

        这些类型会成为 ColumnInfo.type 的真实来源。
        """
        # MySQL 的 SHOW COLUMNS 可以读取字段名称、类型、
        # 是否为空、索引类型等表结构信息。
        sql = f"show columns from {table_name}"

        # text() 将普通字符串转换成 SQLAlchemy 可以执行的 TextClause。
        #
        # session.execute() 会真正向 DW MySQL 发送 SQL，
        # 因为 AsyncSession.execute() 是异步操作，所以需要 await。
        result = await self.session.execute(text(sql))

        # SHOW COLUMNS 的查询结果包含：
        #
        # Field、Type、Null、Key、Default、Extra
        #
        # mappings() 将每一行转换成类似字典的 RowMapping，
        # fetchall() 读取全部结果。
        rows = result.mappings().fetchall()

        # 只保留当前项目需要的 Field 和 Type。
        #
        # 转换前：
        # [
        #     {"Field": "order_id", "Type": "varchar(64)", ...},
        #     {"Field": "order_amount", "Type": "decimal(10,2)", ...},
        # ]
        #
        # 转换后：
        # {
        #     "order_id": "varchar(64)",
        #     "order_amount": "decimal(10,2)",
        # }
        return {row["Field"]: row["Type"] for row in rows}

    async def get_column_values(
        self,
        table_name: str,
        column_name: str,
        limit: int = 10,
    ) -> list:
        """
        查询字段的不重复真实值。

        参数：
            table_name：真实表名，例如 dim_region。
            column_name：真实字段名，例如 region_name。
            limit：最多返回多少个值，默认 10 个。

        返回：
            字段值列表，例如：

            ["华东", "华南", "华北"]

        这个方法有两个用途：

        1. limit=10：
           抽取少量值作为 ColumnInfo.examples。

        2. limit=100000：
           为 sync=true 的字段抽取大量枚举值，
           后续写入 Elasticsearch。
        """

        # DISTINCT 可以去除重复值。
        #
        # 例如 region_name 有一万行数据，
        # 但只有华东、华南、华北等少量不同值，
        # DISTINCT 最终只返回这些不同值。
        sql = f"select distinct {column_name} from {table_name} limit {limit}"

        result = await self.session.execute(text(sql))

        # result.fetchall() 返回类似：
        #
        # [
        #     ("华东",),
        #     ("华南",),
        # ]
        #
        # 因为 SELECT 只查询一个字段，所以每一行只有一个元素。
        # row[0] 用来取出这一列的真实值。
        return [row[0] for row in result.fetchall()]

    async def get_db_info(
        self,
    ) -> dict[str, str | None]:
        """
        获取当前 DW 数据库的方言和版本。

        返回示例：

        {
            "dialect": "mysql",
            "version": "8.4.6",
        }

        这些信息会在后续 SQL 生成流程中提供给模型，
        告诉模型应该生成哪种数据库语法。
        """

        # 查询真实 MySQL 版本。
        result = await self.session.execute(text("select version()"))

        # scalar() 读取查询结果第一行第一列。
        #
        # SELECT VERSION() 的结果只有一个值，
        # 因此不需要使用 fetchall()。
        version = result.scalar()

        # session.bind 是当前 Session 绑定的数据库 Engine。
        # dialect.name 表示 SQLAlchemy 数据库方言，例如 mysql。
        #
        # rebuild 通过 mysql+asyncmy 创建 Session，
        # 所以这里应当得到 mysql。
        dialect = self.session.bind.dialect.name

        return {
            "dialect": dialect,
            "version": version,
        }

    async def validate(
        self,
        sql: str,
    ) -> None:
        """
        使用 EXPLAIN 让 MySQL 提前解析 SQL。

        这个方法用于后续问数流程。

        它可以发现：
        - SQL 语法错误；
        - 表不存在；
        - 字段不存在；
        - JOIN 条件无法解析。

        它不会执行完整业务查询，也不返回最终查询数据。
        """

        explain_sql = f"explain {sql}"

        # SQL 正确时正常结束。
        # SQL 错误时让数据库异常继续向上抛出，
        # 由后续 Service 或 Agent 决定如何修正 SQL。
        await self.session.execute(text(explain_sql))

    async def run(
        self,
        sql: str,
    ) -> list[dict]:
        """
        执行最终 SQL，并返回普通字典列表。

        输入示例：

            SELECT region_name, SUM(order_amount) AS gmv
            FROM ...
            GROUP BY region_name

        输出示例：

            [
                {"region_name": "华东", "gmv": 10000},
                {"region_name": "华南", "gmv": 8000},
            ]
        """

        result = await self.session.execute(text(sql))

        # mappings() 把每行转换成带字段名的 RowMapping。
        #
        # dict(row) 再把 SQLAlchemy RowMapping 转换成普通字典，
        # 让 Service、Agent 或 API 层不需要理解 SQLAlchemy 对象。
        return [dict(row) for row in result.mappings().fetchall()]
