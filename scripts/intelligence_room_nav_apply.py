"""情报处理室页首导航表在 Skin:Arknights 下的两处宽度问题。

**桌面封面表撑宽整页**：两张 `nomobile` 表（公共事务实录 / 特别行动记述）各两处：表头格 `width:1000px` 定表宽，
里面横向滚动的封面条 `<div style="overflow:auto;width:1000px">` 也是 1000px。新皮肤正文栏在 640–1050
（出侧栏后 1200–约 1700）都窄于 1000px，表伸出正文栏、整页能横向拖（1000 宽视口整页 1047）。

表改 `width:100%; max-width:1000px; table-layout:fixed`，去掉表头的定宽，封面条 `width:100%`。
`table-layout:fixed` 不能省：自动布局下封面条的最小内容宽度是整排不换行的封面（一万多 px），百分比宽度压不住。
封面条照旧在自己里面横滑。

**手机索引表填不满**：两张 `nodesktop` 索引表（三列链接）在 <640 吃皮肤的 `table.wikitable { display:block }`，
表的边框占满正文栏，单元格却是按内容收缩的匿名表格，右边空一截（600 宽时 576 里只占 487 / 359）。
行内补 `display:table; width:100%`（站上编辑对付这条规则的通行写法），三列短链接不会撑破。

**特别行动记述的封面不见**：每张表左边一格只放 160px 封面（`!rowspan=… class="nomobile"`），右边三列按钮格各
`width="33%"`，封面图的最小宽度又因皮肤 `.mw-file-element { max-width:100% }` 计 0，整列被挤成 20px、图 0×0（所有宽度都是）。
`模板:情报处理室/styles.css`（页面已经引着）加两条：封面图 `max-width:none` 保持 160px；正文栏放不下封面 + 三个 174px 按钮
（< 约 790px，即视口 640–899）时隐藏封面列，同手机版式。插在 theme-os 区块前面，那个区块重跑时会重新生成。

**640–719 宽仍伸出正文栏**：隐藏封面后三个写死 174px 的 `{{剧情跳转}}` 仍要 609px，正文栏 550–629 放不下。
这段宽度隐藏三列的按钮格、改显示手机版那格竖排的（`td.nodesktop`，皮肤在 ≥640 用 `!important` 藏它，这里同样 `!important`）。

已经改过的条目跳过，编辑摘要只写这次真改了的。见 migration/story-play-button/README.md。

    uv run python scripts/intelligence_room_nav_apply.py --dry-run               # 只打印 diff
    uv run python scripts/intelligence_room_nav_apply.py -c config.sandbox.toml  # 沙箱演练
    uv run python scripts/intelligence_room_nav_apply.py                         # 线上落地
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wikibot.config import get_settings, load_config  # noqa: E402
from wikibot.wiki import Wiki  # noqa: E402

TITLE = "情报处理室"
STYLES = "模板:情报处理室/styles.css"
README = "见 prts-skin-migration/migration/story-play-button/README.md"
WIDE = "页首两张封面导航表写死 1000px，窄屏把整页撑宽：改成随正文栏收窄、最宽 1000px，封面条照旧横滑。"
INDEX = "手机版两张索引表在新皮肤下填不满表格边框：补 display:table; width:100%。"
COVER = "特别行动记述的封面被三列 33% 的按钮格挤成 20px、图不见：封面图保持 160px，正文栏放不下时（视口 640–899）隐藏封面列。"
COVER_CSS = """/* 特别行动记述：封面格旁边是三列 width="33%" 的按钮格，封面图的最小宽度又因皮肤 max-width:100% 计 0，整列被挤没。
 * 图保持 160px；正文栏放不下封面 + 三个 174px 按钮（< 约 790px，视口 640–899）时隐藏封面列，同手机版式 */
.intelligence-room-story-table > tbody > tr > th.nomobile[rowspan] .mw-file-element {
\tmax-width: none;
}

@media (min-width: 640px) and (max-width: 899px) {
\t.intelligence-room-story-table > tbody > tr > th.nomobile[rowspan] {
\t\tdisplay: none;
\t}
}

"""

# 页面 → [(摘要, 旧写法, 新写法)]；新写法已在页面里就跳过（插在锚点前的块只看块本身），否则旧写法得恰好命中一次
EDITS: dict[str, list[tuple[str, str, str]]] = {}
EDITS[TITLE] = [
    *(
        (
            WIDE,
            f'{{| class="nomobile"\n! style="background:#464646;color:white;width:1000px;"|<big>{name}</big>',
            f'{{| class="nomobile" style="width:100%;max-width:1000px;table-layout:fixed;"\n'
            f'! style="background:#464646;color:white;"|<big>{name}</big>',
        )
        for name in ("公共事务实录", "特别行动记述")
    ),
    *(
        (
            WIDE,
            f'<div style="clear:both;overflow:auto;width:1000px;height:{h};',
            f'<div style="clear:both;overflow:auto;width:100%;height:{h};',
        )
        for h in ("270px", "290px")
    ),
    *(
        (
            INDEX,
            f'{{| class="wikitable nodesktop intelligence-room-mobile-index" style="text-align:center;"\n! colspan="{n}"',
            f'{{| class="wikitable nodesktop intelligence-room-mobile-index" style="text-align:center;display:table;width:100%;"\n'
            f'! colspan="{n}"',
        )
        for n in ("3", "5")
    ),
]
BAND = "视口 640–719 正文栏放不下三个写死 174px 的剧情跳转按钮，特别行动记述伸出正文栏：这段宽度改用手机版那格竖排的按钮。"
BAND_CSS = """/* 视口 640–719：正文栏 550–629 放不下三个写死 174px 的 {{剧情跳转}}（至少 609px），改用手机版那格竖排的按钮。
 * 皮肤在 ≥640 用 !important 隐藏 .nodesktop，这里也得 !important（选择器带 .mw-parser-output，优先级更高） */
@media (min-width: 640px) and (max-width: 719px) {
\t.intelligence-room-story-table > tbody > tr > td.nomobile {
\t\tdisplay: none;
\t}

\t.intelligence-room-story-table > tbody > tr > td.nodesktop {
\t\tdisplay: table-cell !important;
\t}
}

"""
EDITS[STYLES] = [
    (COVER, "/* theme-os:begin", COVER_CSS + "/* theme-os:begin"),
    (BAND, "/* theme-os:begin", BAND_CSS + "/* theme-os:begin"),
]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("-c", "--config", type=Path, help="换配置文件，如 config.sandbox.toml 先在沙箱演练")
    ns = ap.parse_args()

    cfg = load_config(ns.config)
    print(f"目标站点：{cfg.api_url}")
    async with Wiki(cfg.api_url, cfg.user_agent, cfg.client, dry_run=ns.dry_run) as wiki:
        await wiki.login(*get_settings().require_credentials())
        for title, edits in EDITS.items():
            await apply(wiki, title, edits, dry_run=ns.dry_run)


async def apply(wiki: Wiki, title: str, edits: list[tuple[str, str, str]], *, dry_run: bool) -> None:
    page = await wiki.read(title)
    if page.missing:
        raise SystemExit(f"{title} 不存在")
    content = page.content
    applied: list[str] = []
    for summary, old, new in edits:
        # 插在锚点前面的块：块本身在就算改过（锚点前面可能后来又插了别的）
        if (new[: -len(old)] if new.endswith(old) else new) in content:
            continue
        n = content.count(old)
        if n != 1:
            raise SystemExit(f"{title} 的写法和脚本里记的不一样了（{old[:40]}… 命中 {n} 次），人工看一下")
        content = content.replace(old, new)
        if summary not in applied:
            applied.append(summary)
    if not applied:
        print(f"  = {title}: 已是目标状态，跳过")
        return
    diff = difflib.unified_diff(
        page.content.split("\n"),
        content.split("\n"),
        f"{title} (old)",
        f"{title} (new)",
        lineterm="",
        n=0,
    )
    print("\n".join(diff))
    if dry_run:
        print(f"  [dry-run] {title}（原 rev {page.revid}）")
        return
    await wiki.edit(title, content, "".join(applied) + README, baserevid=page.revid, nocreate=True)
    print(f"  ✔ {title} 已写入（原 rev {page.revid}）")


if __name__ == "__main__":
    asyncio.run(main())
