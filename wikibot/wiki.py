"""MediaWiki API 异步客户端（httpx + asyncio）。

只封装迁移需要的部分：登录、列举、批量读取、提交、渲染预览。
所有请求带 ``formatversion=2``（JSON 结构干净）与 ``maxlag``（机器人礼节），
网络错误与服务器滞后由 tenacity 重试；读请求受信号量限流，写请求串行且限速。
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Sequence
from typing import TYPE_CHECKING, Any, Self

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from wikibot.log import logger
from wikibot.models import Page, PageRef

if TYPE_CHECKING:
    from wikibot.config import ClientConfig


class WikiError(RuntimeError):
    """API 返回了 error 字段。"""

    def __init__(self, code: str, info: str) -> None:
        super().__init__(f"[{code}] {info}")
        self.code = code
        self.info = info


class RetryableWikiError(WikiError):
    """maxlag / readonly / ratelimited 等可重试的错误。"""


RETRYABLE_CODES = frozenset(
    {"maxlag", "readonly", "ratelimited", "internal_api_error_DBQueryError"}
)


class Wiki:
    """一个已登录（或匿名）的 MediaWiki 异步会话。

    用法::

        async with Wiki(cfg.api_url, cfg.user_agent, cfg.client) as wiki:
            await wiki.login(user, password)
            page = await wiki.read("模板:Sandbox")

    ``dry_run=True`` 时所有写操作只打日志不落地，读操作照常。
    """

    def __init__(
        self,
        api_url: str,
        user_agent: str,
        client: "ClientConfig",
        dry_run: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_url = api_url
        self.client = client
        self.dry_run = dry_run
        self.username: str | None = None
        self._csrf_token: str | None = None
        self._last_edit_at = 0.0

        self.http = httpx.AsyncClient(
            headers={"User-Agent": user_agent},
            timeout=client.timeout,
            follow_redirects=True,
            transport=transport,  # 测试时注入 MockTransport
        )
        self._read_sem = asyncio.Semaphore(client.concurrency)
        self._edit_lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self.http.aclose()

    # ------------------------------------------------------------------ 底层

    def _new_retrying(self) -> AsyncRetrying:
        """每次调用建一个新的重试器，避免并发共享内部状态。"""
        return AsyncRetrying(
            stop=stop_after_attempt(self.client.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=30),
            retry=retry_if_exception_type((httpx.HTTPError, RetryableWikiError)),
            reraise=True,
        )

    async def _do_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = {"format": "json", "formatversion": "2", **params}
        if self.client.maxlag:
            payload["maxlag"] = str(self.client.maxlag)
        if method == "GET":
            res = await self.http.get(self.api_url, params=payload)
        else:
            res = await self.http.post(self.api_url, data=payload)
        if res.status_code >= 500:
            res.raise_for_status()
        data = res.json()
        if error := data.get("error"):
            code = error.get("code", "unknown")
            info = error.get("info", "")
            if code in RETRYABLE_CODES:
                raise RetryableWikiError(code, info)
            raise WikiError(code, info)
        for warning in data.get("warnings", {}).values():
            logger.warning("API warning: {}", warning)
        return data

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        retrying = self._new_retrying()
        return await retrying(self._do_request, method, params)

    async def get(self, **params: Any) -> dict[str, Any]:
        async with self._read_sem:
            return await self._request("GET", params)

    async def post(self, **params: Any) -> dict[str, Any]:
        return await self._request("POST", params)

    async def _token(self, type_: str = "csrf") -> str:
        if type_ == "csrf" and self._csrf_token:
            return self._csrf_token
        data = await self.get(action="query", meta="tokens", type=type_)
        token = data["query"]["tokens"][f"{type_}token"]
        if type_ == "csrf":
            self._csrf_token = token
        return token

    # ------------------------------------------------------------------ 会话

    async def login(self, username: str, password: str) -> str:
        """用 BotPasswords 登录，返回实际登录到的用户名。"""
        res = await self.post(
            action="login",
            lgname=username,
            lgpassword=password,
            lgtoken=await self._token("login"),
        )
        login = res["login"]
        if login.get("result") != "Success":
            raise WikiError(login.get("result", "Failed"), login.get("reason", ""))
        self._csrf_token = None  # 登录后旧 token 失效
        self.username = login.get("lgusername", username)
        logger.info("已登录 {}", self.username)
        return self.username

    async def userinfo(self) -> dict[str, Any]:
        """当前账号信息，含用户组与权限，用于自检。"""
        data = await self.get(action="query", meta="userinfo", uiprop="groups|rights")
        return data["query"]["userinfo"]

    async def siteinfo(self, siprop: str = "general") -> dict[str, Any]:
        data = await self.get(action="query", meta="siteinfo", siprop=siprop)
        return data["query"]

    # ------------------------------------------------------------------ 读取

    async def _iter_query(self, **params: Any) -> AsyncIterator[dict[str, Any]]:
        """处理 continuation 的 query 迭代器，逐页产出 ``data["query"]``。

        continuation 天生串行，无法并发。
        """
        cont: dict[str, Any] = {}
        while True:
            data = await self.get(action="query", **params, **cont)
            if "query" in data:
                yield data["query"]
            if "continue" not in data:
                return
            cont = data["continue"]

    async def iter_allpages(
        self,
        namespace: int,
        prefix: str = "",
        redirects: bool = False,
    ) -> AsyncIterator[PageRef]:
        """列举一个名字空间下的全部页面。"""
        params: dict[str, Any] = {
            "list": "allpages",
            "apnamespace": namespace,
            "aplimit": "max",
            "apfilterredir": "all" if redirects else "nonredirects",
        }
        if prefix:
            params["apprefix"] = prefix
        async for query in self._iter_query(**params):
            for item in query.get("allpages", []):
                yield PageRef.model_validate(item)

    async def iter_categorymembers(self, category: str) -> AsyncIterator[PageRef]:
        """列举分类成员，category 需带名字空间前缀（如 ``分类:需要迁移``）。"""
        async for query in self._iter_query(
            list="categorymembers", cmtitle=category, cmlimit="max"
        ):
            for item in query.get("categorymembers", []):
                yield PageRef.model_validate(item)

    async def iter_embeddedin(
        self, title: str, namespace: int | None = None
    ) -> AsyncIterator[PageRef]:
        """列举嵌入（transclude）了某模板 / 微件的页面，用于评估改动影响面。"""
        params: dict[str, Any] = {
            "list": "embeddedin",
            "eititle": title,
            "eilimit": "max",
        }
        if namespace is not None:
            params["einamespace"] = namespace
        async for query in self._iter_query(**params):
            for item in query.get("embeddedin", []):
                yield PageRef.model_validate(item)

    async def fetch_pages(self, titles: Iterable[str]) -> AsyncIterator[Page]:
        """按 ``read_batch_size`` 分批并发拉取正文，谁先回来先产出。"""
        batches = list(_chunked(list(titles), self.client.read_batch_size))
        if not batches:
            return
        tasks = [asyncio.create_task(self._fetch_batch(b)) for b in batches]
        try:
            for task in asyncio.as_completed(tasks):
                for page in await task:
                    yield page
        finally:
            for task in tasks:
                task.cancel()

    async def _fetch_batch(self, titles: Sequence[str]) -> list[Page]:
        data = await self.get(
            action="query",
            titles="|".join(titles),
            prop="revisions",
            rvprop="ids|timestamp|content",
            rvslots="main",
        )
        pages = data.get("query", {}).get("pages", [])
        return [_page_from_api(item) for item in pages]

    async def read(self, title: str) -> Page:
        """读单个页面；不存在时返回 ``missing=True`` 的空页面。"""
        pages = await self._fetch_batch([title])
        return pages[0] if pages else Page(title=title, missing=True)

    async def parse(self, text: str, title: str) -> str:
        """把 wikitext 渲染成 HTML，用于比对迁移前后的渲染结果。"""
        data = await self.post(
            action="parse",
            title=title,
            text=text,
            contentmodel="wikitext",
            prop="text",
            disablelimitreport="1",
        )
        return data["parse"]["text"]

    # ------------------------------------------------------------------ 写入

    async def edit(
        self,
        title: str,
        text: str,
        summary: str,
        baserevid: int | None = None,
        basetimestamp: str | None = None,
        minor: bool = False,
        bot: bool = True,
        nocreate: bool = True,
    ) -> dict[str, Any]:
        """提交一次编辑。

        默认带 ``nocreate`` 与 ``baserevid``：页面被删掉或在抓取之后被改过时
        直接失败，而不是覆盖别人的编辑。``dry_run`` 下只打日志。
        """
        if self.dry_run:
            logger.info("[dry-run] 跳过写入 {}（{}）", title, summary)
            return {"edit": {"result": "DryRun", "title": title}}

        params: dict[str, Any] = {
            "action": "edit",
            "title": title,
            "text": text,
            "summary": summary,
            "token": await self._token(),
            "assert": "bot" if bot else "user",
        }
        if bot:
            params["bot"] = "1"
        if minor:
            params["minor"] = "1"
        if nocreate:
            params["nocreate"] = "1"
        if baserevid:
            params["baserevid"] = str(baserevid)
        if basetimestamp:
            params["basetimestamp"] = basetimestamp

        # 写操作串行：既守住 edit_delay 限速，也避免 token 竞争
        async with self._edit_lock:
            await self._throttle()
            data = await self.post(**params)
        result = data.get("edit", {})
        if result.get("result") != "Success":
            raise WikiError("editfailed", f"{title}: {result}")
        if "nochange" in result:
            logger.debug("{} 内容无变化，服务器未创建新修订", title)
        return data

    async def purge(self, titles: "Sequence[str]", forcelinkupdate: bool = True) -> int:
        """清页面缓存。

        改完模板后刷依赖页面用；prts.wiki 前面有 CDN，不刷看不到新内容。
        """
        if self.dry_run:
            logger.info("[dry-run] 跳过 purge {}", ", ".join(titles))
            return 0
        params: dict[str, Any] = {"action": "purge", "titles": "|".join(titles)}
        if forcelinkupdate:
            params["forcelinkupdate"] = "1"
        data = await self.post(**params)
        return sum(1 for item in data.get("purge", []) if "purged" in item)

    async def protection(self, titles: "Sequence[str]") -> dict[str, dict[str, str]]:
        """各页面自身的保护级别：``{标题: {"edit": "sysop", "move": ...}}``，没保护的是空字典。

        不含级联保护（那是别的页面带过来的，改不了也不用改）。
        """
        out: dict[str, dict[str, str]] = {}
        for chunk in _chunked(list(titles), 50):
            data = await self.get(
                action="query", titles="|".join(chunk), prop="info", inprop="protection"
            )
            for item in data.get("query", {}).get("pages", []):
                out[item["title"]] = {
                    p["type"]: p["level"]
                    for p in item.get("protection", [])
                    if "source" not in p
                }
        return out

    async def protect(self, title: str, levels: dict[str, str], reason: str) -> None:
        """无限期保护：``levels`` 形如 ``{"edit": "autoconfirmed", "move": "autoconfirmed"}``。

        API 会把**没列出的**动作的保护撤掉，所以 edit / move 要一起给。
        """
        if self.dry_run:
            logger.info("[dry-run] 跳过保护 {}（{}）", title, levels)
            return
        async with self._edit_lock:
            await self._throttle()
            data = await self.post(
                action="protect",
                title=title,
                protections="|".join(f"{k}={v}" for k, v in levels.items()),
                expiry="infinite",
                reason=reason,
                token=await self._token(),
            )
        if "protect" not in data:
            raise WikiError("protectfailed", f"{title}: {data}")

    async def _throttle(self) -> None:
        """两次写入之间至少间隔 ``edit_delay`` 秒。"""
        delay = self.client.edit_delay
        if delay <= 0:
            return
        loop = asyncio.get_running_loop()
        elapsed = loop.time() - self._last_edit_at
        if elapsed < delay:
            await asyncio.sleep(delay - elapsed)
        self._last_edit_at = loop.time()


async def gather_limited[T](
    limit: int, jobs: Iterable[Callable[[], Awaitable[T]]]
) -> list[T]:
    """带并发上限地跑一批协程工厂，返回值顺序与传入一致。"""
    sem = asyncio.Semaphore(limit)

    async def run(job: Callable[[], Awaitable[T]]) -> T:
        async with sem:
            return await job()

    return list(await asyncio.gather(*(run(job) for job in jobs)))


def _chunked[T](items: Sequence[T], size: int) -> list[Sequence[T]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _page_from_api(item: dict[str, Any]) -> Page:
    """把 formatversion=2 的 query.pages 元素转成 Page。"""
    if item.get("missing"):
        return Page(title=item["title"], ns=item.get("ns", 0), missing=True)
    revisions = item.get("revisions") or [{}]
    rev = revisions[0]
    slot = (rev.get("slots") or {}).get("main", {})
    return Page(
        pageid=item.get("pageid", 0),
        ns=item.get("ns", 0),
        title=item["title"],
        revid=rev.get("revid", 0),
        timestamp=rev.get("timestamp"),
        content=slot.get("content", ""),
        content_model=slot.get("contentmodel", "wikitext"),
    )
