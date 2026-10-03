"""衍生作品导航手机版改成手风琴。见 migration/derivative-nav/README.md。

- 新建 模块:衍生作品导航（源文件 migration/derivative-nav/模块_衍生作品导航.lua）；
- 模板:衍生作品导航/styles.css 整页换成手风琴样式（源文件同目录）；
- 模板:衍生作品导航：手机版那张 wikitable 按表头的 rowspan 还原成树，改写成 {{#invoke:衍生作品导航|main|…}}，
  条目原样搬过去；后面的桌面版 Navbox 不动。

先写模块和样式再改模板：模板引用了不存在的模块 / 样式页会在正文里输出报错。
幂等：已是目标状态就跳过。

    uv run python scripts/derivative_nav_apply.py --dry-run                           # 只打印 diff
    uv run python scripts/derivative_nav_apply.py -c config.sandbox.toml --from-live  # 沙箱演练，以线上模板正文为底
    uv run python scripts/derivative_nav_apply.py                                     # 线上落地
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wikibot.config import get_settings, load_config
from wikibot.wiki import Wiki

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "migration" / "derivative-nav"
NAV = "模板:衍生作品导航"
NAV_STYLES = "模板:衍生作品导航/styles.css"
MODULE = "模块:衍生作品导航"
LIVE_RAW = "https://prts.wiki/index.php"
SUMMARY = {
    MODULE: "衍生作品导航手机版的手风琴：当前页面所在的路径默认展开，其余收起。"
    "见 prts-skin-migration/migration/derivative-nav/README.md",
    NAV_STYLES: "衍生作品导航手机版改手风琴：样式整页替换，开合记号对齐 PRTS Design 的 Accordion。"
    "见 prts-skin-migration/migration/derivative-nav/README.md",
    NAV: "衍生作品导航手机版从整张展开的表改成手风琴（模块:衍生作品导航），条目不变；桌面版 Navbox 不动。"
    "见 prts-skin-migration/migration/derivative-nav/README.md",
}
# 代表页：单曲 / EP / OST / 出版物 / 大类总览 / 导航首页（全部收起）
PURGE = ["Runaway", "Summer Calling", "孤星OST", "CURFEW", "衍生作品/音乐", "衍生作品"]

TS_TAG = '<templatestyles src="衍生作品导航/styles.css" />'
TABLE_START = '{| class="wikitable nodesktop'
TABLE_END = '|}<div class="nomobile">'
INVOKE = "{{#invoke:衍生作品导航|"
ATTRS = re.compile(r'\s*((?:[\w-]+="[^"]*"\s*)+)\|(?!\|)')


@dataclass
class Node:
    label: str = ""
    items: str = ""
    children: list[Node] = field(default_factory=list)


def parse_cell(line: str) -> tuple[str, int, str]:
    """一行一个单元格：``! 属性 | 内容`` 或 ``| 内容``。返回（! 或 |，rowspan，内容）。"""
    kind, rest = line[0], line[1:]
    attrs = ""
    if m := ATTRS.match(rest):
        attrs, rest = m.group(1), rest[m.end() :]
    span = re.search(r'rowspan="(\d+)"', attrs)
    return kind, int(span.group(1)) if span else 1, rest.strip()


def parse_table(table: str) -> tuple[str, Node]:
    """手机版表格 → （标题，树）。表头按 rowspan 往下罩住后面的行，还原出每一行的路径。"""
    rows = [r.strip() for r in re.split(r"^\|-[ \t]*$", table, flags=re.M)]
    title = re.search(r"<big>(.*)</big>", rows[1])
    if not rows[0].startswith(TABLE_START) or not title:
        raise SystemExit("手机版表格的开头 / 标题行不是预期的样子")
    root = Node()
    active: list[list] = []  # [节点, 还罩着几行]
    for row in rows[2:]:
        parent = active[-1][0] if active else root
        cells = [parse_cell(line) for line in row.split("\n")]
        if [c[0] for c in cells if c[0] != "!"] != ["|"] or cells[-1][0] != "|":
            raise SystemExit(f"这一行不是「若干表头 + 一个内容格」：{row[:80]}")
        for kind, span, content in cells:
            if kind == "!":
                node = Node(label=content)
                parent.children.append(node)
                active.append([node, span])
                parent = node
            else:
                parent.items = content
        for item in active:
            item[1] -= 1
        while active and active[-1][1] == 0:
            active.pop()
    if active:
        raise SystemExit("rowspan 没有在表格结束时收完")
    return title.group(1), root


def emit(node: Node, depth: int, fn: str = "child", title: str = "") -> str:
    """写法同 Navbox：groupN / listN，没有 group 的 list 是这一层自己的条目。"""
    pad = "  " * depth
    lines = [f"{INVOKE}{fn}"]
    if title:
        lines.append(f"{pad}|title = {title}")
    n = 0
    if node.items:
        n += 1
        lines.append(f"{pad}|list{n} = {node.items}")
    for child in node.children:
        n += 1
        lines.append(f"{pad}|group{n} = {child.label}")
        value = emit(child, depth + 1) if child.children else child.items
        lines.append(f"{pad}|list{n} = {value}")
    lines.append(pad + "}}")
    return "\n".join(lines)


def lists(node: Node) -> list[str]:
    return ([node.items] if node.items else []) + [
        x for c in node.children for x in lists(c)
    ]


def convert(text: str) -> str:
    if INVOKE + "main" in text:
        return text
    if not text.startswith(TABLE_START) or text.count(TABLE_END) != 1:
        raise SystemExit(f"{NAV}: 找不到手机版表格的起止位置")
    end = text.index(TABLE_END)
    title, root = parse_table(text[:end])
    new = TS_TAG + emit(root, 0, "main", title) + text[end + len("|}") :]
    # 条目必须一条不少、原样搬过去
    cells = [
        parse_cell(line)[2]
        for line in text[:end].split("\n")
        if line.startswith("|") and not line.startswith("|-")
    ]
    if lists(root) != cells or any(new.count(x) < text[:end].count(x) for x in cells):
        raise SystemExit(f"{NAV}: 转换前后的条目对不上")
    return new


def show_diff(title: str, old: str, new: str) -> None:
    diff = difflib.unified_diff(
        old.split("\n"),
        new.split("\n"),
        f"{title} (old)",
        f"{title} (new)",
        lineterm="",
        n=0,
    )
    print("\n".join(line[:200] for line in diff))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "-c", "--config", type=Path, help="换配置文件，如 config.sandbox.toml"
    )
    ap.add_argument(
        "--from-live", action="store_true", help="模板正文以线上为底（沙箱演练用）"
    )
    ns = ap.parse_args()

    cfg = load_config(ns.config)
    print(f"目标站点：{cfg.api_url}")
    async with Wiki(
        cfg.api_url, cfg.user_agent, cfg.client, dry_run=ns.dry_run
    ) as wiki:
        await wiki.login(*get_settings().require_credentials())
        module, styles, nav = (
            await wiki.read(MODULE),
            await wiki.read(NAV_STYLES),
            await wiki.read(NAV),
        )
        if nav.missing:
            raise SystemExit(f"{NAV} 不存在")
        base = nav.content
        if ns.from_live:
            async with httpx.AsyncClient(
                headers={"User-Agent": cfg.user_agent}
            ) as http:
                resp = await http.get(LIVE_RAW, params={"title": NAV, "action": "raw"})
                resp.raise_for_status()
                base = resp.text

        targets = (
            (module, (SRC / "模块_衍生作品导航.lua").read_text(encoding="utf-8")),
            (
                styles,
                (SRC / "模板_衍生作品导航_styles.css").read_text(encoding="utf-8"),
            ),
            (nav, convert(base)),
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
            # 其余嵌入页用 scripts/purge_embeddedin.py 清
            await wiki.purge(PURGE)
            print(f"  purge：{'、'.join(PURGE)}")


if __name__ == "__main__":
    asyncio.run(main())
