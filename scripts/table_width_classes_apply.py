"""Common.css 表格布局类的两处遗留：定宽类撑破页面、prts-table-display 压不过皮肤。

1. 定宽类（.prts-table-600 / 700 等）是模板内联 width 挪进 Common.css 的产物，
   table-fixed-width 迁移只改了正文 / 模板里的内联 width，没管到这里：视口 640 起
   皮肤不再给 .wikitable 加 max-width:100%，正文栏比定宽窄时表格超出正文栏
   （如 陈 的「干员异格任务」，640 宽下正文栏 550px、表 600px）。全站只有两个模板用，
   改回表格开头的行内 width:min(定宽, 100%)，同 table-fixed-width；4 个定宽类随后删掉。
2. 皮肤窄屏（<640）把正文表格改成 display:block，表格按内容收缩、右侧空出一截框。
   模板原先写行内 display:table 压得过，挪成 .prts-table-display 后特指度不够，
   这里加 !important；干员异格任务原本就没写 display:table，挂上这个类。

见 migration/table-fixed-width/README.md「第三批」。
各处替换按顺序做，新文本已在页面里就跳过，重跑不会重复改。

    uv run python scripts/table_width_classes_apply.py --dry-run  # 只打印 diff
    uv run python scripts/table_width_classes_apply.py -c config.sandbox.toml
    uv run python scripts/table_width_classes_apply.py            # 线上落地
    uv run python scripts/purge_embeddedin.py 模板:干员异格任务    # 落地后清引用页缓存
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wikibot.config import get_settings, load_config
from wikibot.wiki import Wiki

DOC = "见 prts-skin-migration/migration/table-fixed-width/README.md"
NARROW_GAP = "窄屏（<640）下皮肤把表格改成 display:block，表格按内容收缩、右侧空出一截框"

DISPLAY_NOTE = (
    "/* 皮肤窄屏（<640）把正文表格改成 display:block（Arknights：.mw-parser-output"
    " table.wikitable；\n"
    "   Minerva：.content table），表格按内容收缩、右侧空出一截框。"
    "模板原先写行内 display:table 压得过，\n"
    "   挪成类后要 !important 才压得过 */\n"
)

# 标题 → (编辑摘要, [(可能的原文, 新文本), ...])
EDITS: dict[str, tuple[str, list[tuple[tuple[str, ...], str]]]] = {
    "MediaWiki:Common.css": (
        "删掉已无人使用的表格定宽类 .prts-table-wide-850 / 700 / 600 / 500；"
        f".prts-table-display 加 !important：{NARROW_GAP}，"
        f"原先模板行内的 display:table 压得过，挪成类后压不过。{DOC}",
        [
            (
                (".prts-table-display { display: table; }",),
                DISPLAY_NOTE + ".prts-table-display { display: table !important; }",
            ),
            (
                (
                    ".prts-table-fixed { table-layout: fixed; }\n"
                    ".prts-table-wide-850 { width: 850px; }\n"
                    ".prts-table-full",
                ),
                ".prts-table-fixed { table-layout: fixed; }\n.prts-table-full",
            ),
            (
                (
                    ".prts-table-compact-full { width: 100%; margin: 0; }\n"
                    ".prts-table-700 { width: 700px; }\n"
                    ".prts-table-600 { width: 600px; }\n"
                    ".prts-table-500 { width: 500px; }\n"
                    ".prts-table-45em",
                ),
                ".prts-table-compact-full { width: 100%; margin: 0; }\n"
                ".prts-table-45em",
            ),
        ],
    ),
    "模板:干员异格任务": (
        "表格定宽 600px 改成 width:min(600px, 100%)（去掉 prts-table-600 类），"
        f"正文栏比定宽窄时不再撑破页面；挂 prts-table-display：{NARROW_GAP}。{DOC}",
        [
            (
                (
                    '{| class="wikitable prts-table-card-bg prts-table-600'
                    ' prts-table-center prts-table-normal"',
                    '{| class="wikitable prts-table-card-bg prts-table-center'
                    ' prts-table-normal" style="width:min(600px, 100%)"',
                ),
                '{| class="wikitable prts-table-card-bg prts-table-display'
                ' prts-table-center prts-table-normal" style="width:min(600px, 100%)"',
            ),
        ],
    ),
    "模板:分支特性信息表格": (
        "表格定宽 700px 改成 width:min(700px, 100%)（去掉 prts-table-700 类），"
        f"正文栏比定宽窄时不再撑破页面（同 table-fixed-width 迁移）。{DOC}",
        [
            (
                (
                    '{|class="wikitable logo prts-table-display prts-table-normal'
                    ' prts-table-700"',
                ),
                '{|class="wikitable logo prts-table-display prts-table-normal"'
                ' style="width:min(700px, 100%)"',
            ),
        ],
    ),
}


def transform(title: str, text: str) -> str:
    for olds, new in EDITS[title][1]:
        if new in text:
            continue
        found = [old for old in olds if text.count(old) == 1]
        if len(found) != 1:
            raise SystemExit(f"{title} 里找不到唯一的一处：{olds[0]}")
        text = text.replace(found[0], new)
    return text


async def apply_page(wiki: Wiki, title: str, dry_run: bool) -> None:
    page = await wiki.read(title)
    if page.missing:
        raise SystemExit(f"{title} 不存在")
    new = transform(title, page.content)
    if new == page.content:
        print(f"  = {title}: 已是目标内容，跳过")
        return
    diff = difflib.unified_diff(
        page.content.split("\n"),
        new.split("\n"),
        f"{title} (old)",
        f"{title} (new)",
        lineterm="",
        n=1,
    )
    print("\n".join(diff))
    if dry_run:
        print(f"  [dry-run] {title}（r{page.revid}）")
        return
    await wiki.edit(title, new, EDITS[title][0], baserevid=page.revid, nocreate=True)
    print(f"  ✔ {title} 已写入")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "-c", "--config", type=Path, help="换配置文件，如 config.sandbox.toml"
    )
    ns = ap.parse_args()

    cfg = load_config(ns.config)
    print(f"目标站点：{cfg.api_url}")
    async with Wiki(
        cfg.api_url, cfg.user_agent, cfg.client, dry_run=ns.dry_run
    ) as wiki:
        await wiki.login(*get_settings().require_credentials())
        for title in EDITS:
            print(f"\n=== {title}")
            await apply_page(wiki, title, ns.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
