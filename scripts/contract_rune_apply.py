"""合约矩阵：新皮肤下图标被压小、连线错位。见 migration/contract-rune/README.md。

- 新建 模板:危机合约词条/styles.css（源文件 migration/contract-rune/模板_危机合约词条_styles.css）；
- 模板:危机合约词条：引入样式，图标外壳和两种连线加类，连线的长度从行内样式挪进样式页；
- 主名字空间里带连线的合约矩阵：表格加 ``prts-cc-matrix`` 类；还没包横滑外壳的包
  ``<div class="ak-table-scroll">``，写法与 scripts/mobile_table_scroll_apply.py 相同。

先写样式再改模板：模板引用了不存在的样式页会在正文里输出报错。幂等：已是目标状态就跳过。

    uv run python scripts/contract_rune_apply.py template --dry-run
    uv run python scripts/contract_rune_apply.py matrix --dry-run
    uv run python scripts/contract_rune_apply.py template -c config.sandbox.toml --from-live   # 沙箱演练
    uv run python scripts/contract_rune_apply.py matrix -c config.sandbox.toml --from-live
    uv run python scripts/contract_rune_apply.py template                                      # 线上落地
    uv run python scripts/contract_rune_apply.py matrix
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mobile_table_scroll_apply import blockers, find_tables, rewrite, wrap

from wikibot.config import get_settings, load_config
from wikibot.wiki import Wiki

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "migration" / "contract-rune"
RUNE = "模板:危机合约词条"
RUNE_STYLES = "模板:危机合约词条/styles.css"
LIVE_API = "https://prts.wiki/api.php"
README = "见 prts-skin-migration/migration/contract-rune/README.md"
SUMMARY = {
    RUNE_STYLES: "危机合约词条的连线长度与图标尺寸：新皮肤下横滑外壳里的图标不再被压小，"
    f"连线按新皮肤的单元格内边距补长；其他皮肤不变。{README}",
    RUNE: "引入 危机合约词条/styles.css：图标外壳和连线加类，连线长度挪进样式页。"
    f"Vector / Minerva 渲染不变，新皮肤下连线重新对上图标。{README}",
}
MATRIX_SUMMARY = (
    "带连线的合约矩阵加 prts-cc-matrix 类、包横滑外壳（ak-table-scroll）："
    f"新皮肤下图标保持原尺寸、连线对得上，放不下时表格横滑；旧皮肤渲染不变。{README}"
)

TS_TAG = '<templatestyles src="危机合约词条/styles.css" />'
_SPAN = '<span style="position:relative;width:55px;height:55px;line-height:55px">'
_LINE = (
    "background-color:var(--prts-page-card-bg);left:{};box-shadow: 0px 3px 5px black;"
)
_DOWN, _RIGHT = _LINE.format("23px;top:30px"), _LINE.format("42px;top:10px")
_ICON = '<span style="display:inline-block;position:relative">[[文件:{{{1|}}}.png'
# （原文, 改后），原文必须恰好出现一次
EDITS = [
    (f"<includeonly>{_SPAN}", f"<includeonly>{TS_TAG}{_SPAN}"),
    (
        f'<div style="position:absolute;width:3px;height:18px;{_DOWN}">',
        f'<div class="prts-cc-rune-line-down" style="position:absolute;width:3px;{_DOWN}">',
    ),
    (
        f'<div style="position:absolute;width:27px;height:3px;{_RIGHT}">',
        f'<div class="prts-cc-rune-line-right" style="position:absolute;height:3px;{_RIGHT}">',
    ),
    (_ICON, _ICON.replace("<span ", '<span class="prts-cc-rune-icon" ', 1)),
]
# 第 5 个参数带连线的调用
_CONN = re.compile(r"\{\{危机合约词条\|[^{}]*\|\s*(?:下|右|下右|右下|D|R|DR|RD)\s*\}\}")
MATRIX_CLASS = "prts-cc-matrix"
_CLASS = re.compile(r'class="([^"]*)"')
# purge 的代表页；其余嵌入页用 scripts/purge_embeddedin.py 清
PURGE = ["荒野 无序矿区/历史合约", "危机合约/历史合约", "模板:危机合约词条/doc"]


def show_diff(title: str, old: str, new: str) -> None:
    diff = difflib.unified_diff(
        old.split("\n"),
        new.split("\n"),
        f"{title} (old)",
        f"{title} (new)",
        lineterm="",
        n=0,
    )
    print("\n".join(line[:240] for line in diff))


def fix_matrices(text: str) -> tuple[str, int, int, list[str]]:
    """带连线的顶层表格：加 prts-cc-matrix 类，还没包外壳的包上。

    返回（新正文，加类几张，包外壳几张，跳过的理由）。
    """
    classed, skipped = 0, []
    for t in reversed(find_tables(text)):
        if t.end < 0 or not t.top or not _CONN.search(text[t.start : t.end]):
            continue
        head_end = text.find("\n", t.start)
        m = _CLASS.search(text, t.start, head_end)
        if not m:
            skipped.append(f"#{t.mt}：表格开头没有 class 属性")
        elif MATRIX_CLASS not in m[1].split():
            text = f"{text[: m.end(1)]} {MATRIX_CLASS}{text[m.end(1) :]}"
            classed += 1
    tables = find_tables(text)
    ids = set()
    for t in tables:
        if t.end < 0 or not _CONN.search(text[t.start : t.end]):
            continue
        why = blockers(text, t)
        if not why:
            ids.add(t.mt)
        elif why != ["已在外壳里"]:
            skipped.append(f"#{t.mt}：{'、'.join(why)}")
    return wrap(text, tables, ids, marked=False), classed, len(ids), skipped


async def live_text(http: httpx.AsyncClient, title: str) -> str:
    resp = await http.get(
        LIVE_API.replace("api.php", "index.php"),
        params={"title": title, "action": "raw"},
    )
    resp.raise_for_status()
    return resp.text


async def cmd_template(
    ns: argparse.Namespace, wiki: Wiki, http: httpx.AsyncClient
) -> None:
    styles, rune = await wiki.read(RUNE_STYLES), await wiki.read(RUNE)
    if rune.missing:
        raise SystemExit(f"{RUNE} 不存在")
    base = await live_text(http, RUNE) if ns.from_live else rune.content
    targets = (
        (styles, (SRC / "模板_危机合约词条_styles.css").read_text(encoding="utf-8")),
        (rune, rewrite(RUNE, base, EDITS)),
    )
    changed = False
    for page, new in targets:
        if not page.missing and page.content.strip() == new.strip():
            print(f"  = {page.title}: 已是目标状态，跳过")
            continue
        show_diff(page.title, "" if page.missing else page.content, new)
        changed = True
        if ns.dry_run:
            print(f"  [dry-run] {page.title}（r{page.revid}）")
            continue
        await wiki.edit(
            page.title,
            new,
            SUMMARY[page.title],
            baserevid=None if page.missing else page.revid,
            nocreate=not page.missing,
        )
        print(f"  ✔ {page.title} 已写入")
    if changed and not ns.dry_run:
        await wiki.purge(PURGE)
        print(f"  purge：{'、'.join(PURGE)}")


async def cmd_matrix(
    ns: argparse.Namespace, wiki: Wiki, http: httpx.AsyncClient
) -> None:
    if ns.only:
        todo = ns.only
    elif ns.from_live:
        resp = await http.get(
            LIVE_API,
            params={
                "action": "query",
                "format": "json",
                "list": "embeddedin",
                "eititle": RUNE,
                "einamespace": 0,
                "eilimit": "max",
            },
        )
        resp.raise_for_status()
        todo = [p["title"] for p in resp.json()["query"]["embeddedin"]]
    else:
        todo = [ref.title async for ref in wiki.iter_embeddedin(RUNE, 0)]
    done, total = [], 0
    for title in sorted(todo):
        page = await wiki.read(title)
        if page.missing and not ns.from_live:
            print(f"  ! {title} 不存在")
            continue
        base = await live_text(http, title) if ns.from_live else page.content
        new, classed, wrapped, skipped = fix_matrices(base)
        for why in skipped:
            print(f"  - {title} {why}")
        if not page.missing and new == page.content:
            if _CONN.search(base):
                print(f"  = {title}: 已是目标状态，跳过")
            continue
        if new == base and not ns.from_live:
            continue
        if ns.verbose:
            show_diff(title, "" if page.missing else page.content, new)
        what = f"加类 {classed} 张、包外壳 {wrapped} 张"
        total += classed
        if ns.dry_run:
            print(f"  [dry-run] {title}（r{page.revid}）{what}")
            done.append(title)
            continue
        await wiki.edit(
            title,
            new,
            MATRIX_SUMMARY,
            baserevid=None if page.missing else page.revid,
            nocreate=not page.missing,
        )
        done.append(title)
        print(f"  ✔ {title} 已写入（{what}）")
    if not ns.dry_run:
        for i in range(0, len(done), 20):
            await wiki.purge(done[i : i + 20], forcelinkupdate=False)
    print(f"{'预演' if ns.dry_run else '写入'} {len(done)} 页，共 {total} 张矩阵")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["template", "matrix"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true", help="matrix 时打印 diff")
    ap.add_argument("--only", nargs="*", help="matrix 只处理这些页面")
    ap.add_argument(
        "-c", "--config", type=Path, help="换配置文件，如 config.sandbox.toml"
    )
    ap.add_argument(
        "--from-live", action="store_true", help="正文以线上为底（沙箱演练用）"
    )
    ns = ap.parse_args()
    if ns.from_live and not ns.config:
        raise SystemExit("--from-live 只用于沙箱演练，要配合 -c config.sandbox.toml")

    cfg = load_config(ns.config)
    print(f"目标站点：{cfg.api_url}")
    async with (
        Wiki(cfg.api_url, cfg.user_agent, cfg.client, dry_run=ns.dry_run) as wiki,
        httpx.AsyncClient(headers={"User-Agent": cfg.user_agent}, timeout=30) as http,
    ):
        await wiki.login(*get_settings().require_credentials())
        await {"template": cmd_template, "matrix": cmd_matrix}[ns.cmd](ns, wiki, http)


if __name__ == "__main__":
    asyncio.run(main())
