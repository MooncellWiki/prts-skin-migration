"""道具图标：新皮肤手机上在窄表格里被挤成十几像素。见 migration/item-icon-shrink/README.md。

- 模板:物品数量角标/styles.css：末尾加一条规则，道具图标外壳里的图不随容器收缩；
- 模板:道具图标：外壳加 ``prts-item-icon`` 类。

样式页是站内编辑在维护的，这里只在末尾追加，不整页覆盖。先写样式再改模板。
幂等：已是目标状态就跳过。

    uv run python scripts/item_icon_shrink_apply.py --dry-run               # 只打印 diff
    uv run python scripts/item_icon_shrink_apply.py -c config.sandbox.toml  # 沙箱演练
    uv run python scripts/item_icon_shrink_apply.py                         # 线上落地
    uv run python scripts/purge_embeddedin.py 模板:道具图标                  # 嵌入页 5600 多个，等任务队列太慢
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

ICON = "模板:道具图标"
STYLES = "模板:物品数量角标/styles.css"
README = "见 prts-skin-migration/migration/item-icon-shrink/README.md"
SUMMARY = {
    STYLES: "道具图标不随容器收缩：新皮肤给 [[文件:]] 图 max-width:100%，在收缩包裹的外壳里按 0 算最小宽度，"
    f"手机上窄表格里的图标被挤成十几像素。Vector / Minerva 渲染不变。{README}",
    ICON: f"外壳加 prts-item-icon 类，配合 物品数量角标/styles.css 让图标在窄表格里保持原尺寸。{README}",
}

RULE = """\
/* 道具图标不随容器收缩。新皮肤给 [[文件:]] 图 max-width:100%，外壳是收缩包裹的 inline-block，
   百分比按 0 算最小宽度，手机上窄表格里的图标被挤成十几像素、数量角标盖住图标。
   放不下时由表格横滑。见 prts-skin-migration/migration/item-icon-shrink/README.md */
.prts-item-icon .mw-file-element {
	max-width: none;
}
"""
_BOX = '<div style="display:inline-block;position:relative">[[文件:道具 带框 '
# （原文, 改后），原文必须恰好出现一次
ICON_EDITS = [(_BOX, _BOX.replace("<div ", '<div class="prts-item-icon" ', 1))]
# purge 的代表页；其余嵌入页用 scripts/purge_embeddedin.py 清
PURGE = ["采购中心", "采购中心/凭证交易所", "模板:道具图标/doc"]


def rewrite(title: str, text: str, edits: list[tuple[str, str]]) -> str:
    for old, new in edits:
        if new in text:
            continue
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"{title}: 期望出现 1 次，实际 {n} 次：{old}")
        text = text.replace(old, new)
    return text


def add_rule(css: str) -> str:
    if ".prts-item-icon" in css:
        return css
    return css.rstrip("\n") + "\n\n" + RULE


def show_diff(title: str, old: str, new: str) -> None:
    diff = difflib.unified_diff(
        old.split("\n"),
        new.split("\n"),
        f"{title} (old)",
        f"{title} (new)",
        lineterm="",
        n=0,
    )
    print("\n".join(line[:300] for line in diff))


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
        styles, icon = await wiki.read(STYLES), await wiki.read(ICON)
        for page in (styles, icon):
            if page.missing:
                raise SystemExit(f"{page.title} 不存在")

        targets = (
            (styles, add_rule(styles.content)),
            (icon, rewrite(ICON, icon.content, ICON_EDITS)),
        )
        changed = False
        for page, new in targets:
            if page.content.strip() == new.strip():
                print(f"  = {page.title}: 已是目标状态，跳过")
                continue
            show_diff(page.title, page.content, new)
            changed = True
            if ns.dry_run:
                print(f"  [dry-run] {page.title}（r{page.revid}）")
                continue
            await wiki.edit(
                page.title,
                new,
                SUMMARY[page.title],
                baserevid=page.revid,
                nocreate=True,
            )
            print(f"  ✔ {page.title} 已写入")

        if changed and not ns.dry_run:
            await wiki.purge(PURGE)
            print(f"  purge：{'、'.join(PURGE)}")


if __name__ == "__main__":
    asyncio.run(main())
