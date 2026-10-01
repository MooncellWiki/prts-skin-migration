"""页面来源：线上 API 与本地沙箱数据库。

扫描 / 预演读哪儿都行，本地库快得多（一次 SQL 拉完，不受 API 限流约束）；
真正写回必须走 API。两种来源实现同一套接口，命令行用 ``--source`` 切换。
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterable
from typing import TYPE_CHECKING, Any, Self

from wikibot.log import logger
from wikibot.models import Page, PageRef

if TYPE_CHECKING:
    from wikibot.config import Config, TargetConfig
    from wikibot.wiki import Wiki


class PageSource(ABC):
    """按目标集合列举 / 读取页面。"""

    name: str

    @abstractmethod
    def iter_refs(self, target: "TargetConfig") -> AsyncIterator[PageRef]:
        """只要标题，用于统计与列表。"""

    @abstractmethod
    def iter_pages(self, target: "TargetConfig") -> AsyncIterator[Page]:
        """连正文一起产出。"""

    @abstractmethod
    def fetch_pages(self, titles: Iterable[str]) -> AsyncIterator[Page]:
        """按标题精确读取。"""

    async def aclose(self) -> None:
        return None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()


class ApiSource(PageSource):
    """走 MediaWiki API，能读线上也能读沙箱站点。"""

    name = "api"

    def __init__(self, wiki: "Wiki", config: "Config") -> None:
        self.wiki = wiki
        self.config = config

    async def iter_refs(self, target: "TargetConfig") -> AsyncIterator[PageRef]:
        for ns in target.namespaces:
            async for ref in self.wiki.iter_allpages(ns):
                if target.matches(ref.title):
                    yield ref

    async def iter_pages(self, target: "TargetConfig") -> AsyncIterator[Page]:
        titles = [ref.title async for ref in self.iter_refs(target)]
        async for page in self.wiki.fetch_pages(titles):
            yield page

    async def fetch_pages(self, titles: Iterable[str]) -> AsyncIterator[Page]:
        async for page in self.wiki.fetch_pages(titles):
            yield page

    async def aclose(self) -> None:
        await self.wiki.aclose()


# MediaWiki 1.43 的 MCR 存储：page → slots → content → text，
# content_address 形如 "tt:12345"，后半截就是 text.old_id。
_PAGE_SELECT = """
SELECT pg.page_id, pg.page_namespace, pg.page_title, pg.page_latest,
       cm.model_name, tx.old_text, tx.old_flags
FROM {p}page pg
JOIN {p}slots sl ON sl.slot_revision_id = pg.page_latest AND sl.slot_role_id = 1
JOIN {p}content ct ON ct.content_id = sl.slot_content_id
JOIN {p}text tx ON tx.old_id = CAST(SUBSTRING(ct.content_address, 4) AS UNSIGNED)
LEFT JOIN {p}content_models cm ON cm.model_id = ct.content_model
"""


class DbSource(PageSource):
    """直连本地沙箱 MySQL，只读。

    比 API 快得多，但拿不到 ``revid`` 之外的编辑上下文，也不能写；
    ``apply`` 一定要用 ApiSource。
    """

    name = "db"

    def __init__(self, config: "Config", password: str | None = None) -> None:
        self.config = config
        self.sandbox = config.sandbox
        self._password = password if password is not None else self.sandbox.password
        self._pool: Any = None

    async def _ensure_pool(self) -> Any:
        if self._pool is None:
            import aiomysql

            self._pool = await aiomysql.create_pool(
                host=self.sandbox.host,
                port=self.sandbox.port,
                user=self.sandbox.user,
                password=self._password,
                db=self.sandbox.database,
                charset="utf8mb4",
                autocommit=True,
                minsize=1,
                maxsize=2,
            )
            logger.debug(
                "已连接沙箱库 {}:{}/{}",
                self.sandbox.host,
                self.sandbox.port,
                self.sandbox.database,
            )
        return self._pool

    async def aclose(self) -> None:
        if self._pool is not None:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None

    def _sql(self, template: str) -> str:
        return template.format(p=self.sandbox.table_prefix)

    async def _stream(self, sql: str, args: tuple) -> AsyncIterator[dict[str, Any]]:
        """用非缓冲游标流式读取，避免把整个名字空间的正文一次性读进内存。"""
        import aiomysql

        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.SSDictCursor) as cur:
                await cur.execute(sql, args)
                while True:
                    row = await cur.fetchone()
                    if row is None:
                        return
                    yield row

    async def iter_refs(self, target: "TargetConfig") -> AsyncIterator[PageRef]:
        placeholders = ", ".join(["%s"] * len(target.namespaces))
        sql = self._sql(
            "SELECT pg.page_id, pg.page_namespace, pg.page_title "
            "FROM {p}page pg "
            f"WHERE pg.page_namespace IN ({placeholders}) AND pg.page_is_redirect = 0 "
            "ORDER BY pg.page_namespace, pg.page_title"
        )
        async for row in self._stream(sql, tuple(target.namespaces)):
            ref = self._to_ref(row)
            if target.matches(ref.title):
                yield ref

    async def iter_pages(self, target: "TargetConfig") -> AsyncIterator[Page]:
        placeholders = ", ".join(["%s"] * len(target.namespaces))
        sql = self._sql(
            _PAGE_SELECT
            + f"WHERE pg.page_namespace IN ({placeholders})"
            + " AND pg.page_is_redirect = 0"
            + " ORDER BY pg.page_namespace, pg.page_title"
        )
        async for row in self._stream(sql, tuple(target.namespaces)):
            page = self._to_page(row)
            if target.matches(page.title):
                yield page

    async def fetch_pages(self, titles: Iterable[str]) -> AsyncIterator[Page]:
        wanted = list(titles)
        if not wanted:
            return
        keys = [self._split_title(t) for t in wanted]
        conditions = " OR ".join(
            ["(pg.page_namespace = %s AND pg.page_title = %s)"] * len(keys)
        )
        sql = self._sql(_PAGE_SELECT + f"WHERE {conditions}")
        args = tuple(v for key in keys for v in key)
        async for row in self._stream(sql, args):
            yield self._to_page(row)

    # ------------------------------------------------------------- 行 → 模型

    def _to_ref(self, row: dict[str, Any]) -> PageRef:
        ns = int(row["page_namespace"])
        return PageRef(
            pageid=int(row["page_id"]),
            ns=ns,
            title=self.config.full_title(ns, _text(row["page_title"])),
        )

    def _to_page(self, row: dict[str, Any]) -> Page:
        ns = int(row["page_namespace"])
        flags = set(_text(row.get("old_flags")).split(","))
        if "external" in flags or "gzip" in flags:
            # 沙箱库目前全是 utf-8 明文；真碰上压缩 / 外部存储得先解开再谈
            raise RuntimeError(
                f"页面 {_text(row['page_title'])} 的正文是 "
                f"{_text(row['old_flags'])} 存储，"
                "DbSource 只支持明文，请改用 --source api"
            )
        return Page(
            pageid=int(row["page_id"]),
            ns=ns,
            title=self.config.full_title(ns, _text(row["page_title"])),
            revid=int(row["page_latest"]),
            content=_text(row["old_text"]),
            content_model=_text(row.get("model_name")) or "wikitext",
        )

    def _split_title(self, full_title: str) -> tuple[int, str]:
        """完整标题 → (名字空间, 数据库里的页面名)。"""
        prefix, _, rest = full_title.partition(":")
        for ns, name in self.config.namespace_names.items():
            if name == prefix:
                return ns, rest.replace(" ", "_")
        return 0, full_title.replace(" ", "_")


def _text(value: object) -> str:
    """MySQL 的 blob 列可能回 bytes，统一成 str。"""
    if value is None:
        return ""
    if isinstance(value, bytes | bytearray):
        return bytes(value).decode("utf-8", errors="replace")
    return str(value)
