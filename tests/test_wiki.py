"""异步客户端：登录、读取、写入、重试。全部走 httpx.MockTransport，不联网。"""

import json

import httpx
import pytest

from wikibot.config import ClientConfig
from wikibot.wiki import RetryableWikiError, Wiki, WikiError

CLIENT = ClientConfig(edit_delay=0, maxlag=0, max_retries=3, read_batch_size=2)


def make_wiki(handler, **kwargs) -> Wiki:
    return Wiki(
        "https://wiki.invalid/api.php",
        "test-agent",
        CLIENT,
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def _params(request: httpx.Request) -> dict[str, str]:
    if request.method == "GET":
        return dict(request.url.params)
    return dict(httpx.QueryParams(request.content.decode()))


async def test_login_success_and_token_refresh() -> None:
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = _params(request)
        seen.append(params)
        if params.get("meta") == "tokens":
            return httpx.Response(200, json={"query": {"tokens": {"logintoken": "T1"}}})
        return httpx.Response(
            200, json={"login": {"result": "Success", "lgusername": "Bot"}}
        )

    async with make_wiki(handler) as wiki:
        assert await wiki.login("Bot", "pw") == "Bot"
    assert seen[-1]["lgtoken"] == "T1"
    assert seen[-1]["formatversion"] == "2"


async def test_login_failure_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if _params(request).get("meta") == "tokens":
            return httpx.Response(200, json={"query": {"tokens": {"logintoken": "T"}}})
        return httpx.Response(
            200, json={"login": {"result": "Failed", "reason": "口令不对"}}
        )

    async with make_wiki(handler) as wiki:
        with pytest.raises(WikiError, match="口令不对"):
            await wiki.login("Bot", "bad")


async def test_read_returns_content_and_revid() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "query": {
                    "pages": [
                        {
                            "pageid": 7,
                            "ns": 10,
                            "title": "模板:X",
                            "revisions": [
                                {
                                    "revid": 99,
                                    "timestamp": "2026-08-01T00:00:00Z",
                                    "slots": {"main": {"content": "内容"}},
                                }
                            ],
                        }
                    ]
                }
            },
        )

    async with make_wiki(handler) as wiki:
        page = await wiki.read("模板:X")
    assert (page.title, page.revid, page.content) == ("模板:X", 99, "内容")
    assert page.timestamp is not None


async def test_read_missing_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "query": {"pages": [{"ns": 10, "title": "模板:无", "missing": True}]}
            },
        )

    async with make_wiki(handler) as wiki:
        page = await wiki.read("模板:无")
    assert page.missing and page.content == ""


async def test_fetch_pages_batches_by_read_batch_size() -> None:
    batches: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        titles = _params(request)["titles"].split("|")
        batches.append(titles)
        return httpx.Response(
            200,
            json={
                "query": {
                    "pages": [
                        {
                            "pageid": i,
                            "ns": 10,
                            "title": t,
                            "revisions": [
                                {"revid": i, "slots": {"main": {"content": t}}}
                            ],
                        }
                        for i, t in enumerate(titles)
                    ]
                }
            },
        )

    async with make_wiki(handler) as wiki:
        got = [p.title async for p in wiki.fetch_pages(["A", "B", "C"])]
    assert sorted(got) == ["A", "B", "C"]
    assert sorted(len(b) for b in batches) == [1, 2]  # read_batch_size = 2


async def test_iter_allpages_follows_continuation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        params = _params(request)
        if "apcontinue" not in params:
            return httpx.Response(
                200,
                json={
                    "query": {"allpages": [{"pageid": 1, "ns": 10, "title": "模板:A"}]},
                    "continue": {"apcontinue": "模板:B", "continue": "-||"},
                },
            )
        return httpx.Response(
            200,
            json={"query": {"allpages": [{"pageid": 2, "ns": 10, "title": "模板:B"}]}},
        )

    async with make_wiki(handler) as wiki:
        titles = [ref.title async for ref in wiki.iter_allpages(10)]
    assert titles == ["模板:A", "模板:B"]


async def test_maxlag_is_retried_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                200, json={"error": {"code": "maxlag", "info": "数据库滞后"}}
            )
        return httpx.Response(200, json={"query": {"general": {"sitename": "PRTS"}}})

    async with make_wiki(handler) as wiki:
        assert (await wiki.siteinfo())["general"]["sitename"] == "PRTS"
    assert calls["n"] == 2


async def test_permanent_error_is_not_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"error": {"code": "badtoken", "info": "无效"}})

    async with make_wiki(handler) as wiki:
        with pytest.raises(WikiError) as exc:
            await wiki.siteinfo()
    assert not isinstance(exc.value, RetryableWikiError)
    assert calls["n"] == 1


async def test_edit_sends_baserevid_and_bot_flags() -> None:
    sent: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        params = _params(request)
        if params.get("meta") == "tokens":
            return httpx.Response(200, json={"query": {"tokens": {"csrftoken": "C"}}})
        sent.update(params)
        return httpx.Response(
            200, json={"edit": {"result": "Success", "newrevid": 123}}
        )

    async with make_wiki(handler) as wiki:
        result = await wiki.edit("模板:X", "新内容", "摘要", baserevid=99)
    assert result["edit"]["newrevid"] == 123
    assert sent["baserevid"] == "99"
    assert sent["nocreate"] == "1"
    assert sent["bot"] == "1"
    assert sent["assert"] == "bot"
    assert sent["token"] == "C"


async def test_edit_failure_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        params = _params(request)
        if params.get("meta") == "tokens":
            return httpx.Response(200, json={"query": {"tokens": {"csrftoken": "C"}}})
        return httpx.Response(200, json={"edit": {"result": "Failure"}})

    async with make_wiki(handler) as wiki:
        with pytest.raises(WikiError, match="editfailed"):
            await wiki.edit("模板:X", "t", "s")


async def test_dry_run_never_writes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"dry-run 不该发请求：{json.dumps(_params(request))}")

    async with make_wiki(handler, dry_run=True) as wiki:
        result = await wiki.edit("模板:X", "t", "s")
    assert result["edit"]["result"] == "DryRun"


async def test_protection_skips_cascade_sources() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "query": {
                    "pages": [
                        {
                            "title": "模板:A",
                            "protection": [
                                {
                                    "type": "edit",
                                    "level": "sysop",
                                    "expiry": "infinity",
                                },
                                {
                                    "type": "edit",
                                    "level": "sysop",
                                    "expiry": "infinity",
                                    "source": "首页",
                                },
                            ],
                        },
                        {"title": "模板:B", "protection": []},
                    ]
                }
            },
        )

    async with make_wiki(handler) as wiki:
        got = await wiki.protection(["模板:A", "模板:B"])
    assert got == {"模板:A": {"edit": "sysop"}, "模板:B": {}}


async def test_protect_sends_all_levels_infinite() -> None:
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = _params(request)
        seen.append(params)
        if params.get("meta") == "tokens":
            return httpx.Response(200, json={"query": {"tokens": {"csrftoken": "C"}}})
        return httpx.Response(200, json={"protect": {"title": params["title"]}})

    async with make_wiki(handler) as wiki:
        await wiki.protect(
            "模板:A", {"edit": "autoconfirmed", "move": "autoconfirmed"}, "理由"
        )
    sent = seen[-1]
    assert sent["action"] == "protect"
    assert sent["protections"] == "edit=autoconfirmed|move=autoconfirmed"
    assert sent["expiry"] == "infinite"
    assert sent["token"] == "C"


async def test_protect_dry_run_never_writes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"dry-run 不该发请求：{json.dumps(_params(request))}")

    async with make_wiki(handler, dry_run=True) as wiki:
        await wiki.protect("模板:A", {"edit": "sysop", "move": "sysop"}, "理由")
