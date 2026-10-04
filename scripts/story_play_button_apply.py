"""情报处理室等页的剧情播放按钮在 Skin:Arknights 下被挤小、640–1050 宽时挤没：按钮外套 50px 宽的 inline-block。

`模板:剧情简介` 一行三格：关卡格 `width:120px`、简介格 `width:620px`、播放格不定宽，只装一张
`[[文件:情报处理室 播放按钮.png|50px]]`。皮肤 `.mw-file-element { max-width:100% }` 让这张图的最小内容宽度计 0，
自动表格布局先满足两列定宽格，播放格只分剩下的：桌面版式正文栏 < 约 964px 时只剩 2px 内边距（按钮 0×0），
最宽也只有 36px；手机版式（20vw 关卡格 + 长文本简介格）按比例只分到 6–20px。

外套 `<span style="display:inline-block;width:50px">`：图的 100% 有了确定的参照，格子最小宽度回到 52px。
只改模板一行，不加样式页；Vector（本来就没缩）不变，Minerva（同样缩到 13px）一并修好。
见 migration/story-play-button/README.md。

    uv run python scripts/story_play_button_apply.py --dry-run               # 只打印 diff
    uv run python scripts/story_play_button_apply.py -c config.sandbox.toml  # 沙箱演练
    uv run python scripts/story_play_button_apply.py                         # 线上落地
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

TEMPLATE = "模板:剧情简介"
SUMMARY = (
    "播放按钮在新皮肤下被表格挤小、部分宽度下消失：按钮外套 50px 宽的 inline-block，格子保底按钮宽。"
    "见 prts-skin-migration/migration/story-play-button/README.md"
)

BUTTON = (
    "[[文件:情报处理室 播放按钮.png|50px|link={{{链接|{{{1|}}}_{{{关卡名|{{{2|}}}}}}"
    "/{{#switch:{{{3|}}}|行动前=BEG|行动后=END|幕间=NBT}}}}}]]"
)
OLD = f'| class="event-story-play" style="background-color:#F0F0F0;"|{BUTTON}'
NEW = (
    '| class="event-story-play" style="background-color:#F0F0F0;"|'
    f'<span style="display:inline-block;width:50px">{BUTTON}</span>'
)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("-c", "--config", type=Path, help="换配置文件，如 config.sandbox.toml 先在沙箱演练")
    ns = ap.parse_args()

    cfg = load_config(ns.config)
    print(f"目标站点：{cfg.api_url}")
    async with Wiki(cfg.api_url, cfg.user_agent, cfg.client, dry_run=ns.dry_run) as wiki:
        await wiki.login(*get_settings().require_credentials())
        page = await wiki.read(TEMPLATE)
        if page.missing:
            raise SystemExit(f"{TEMPLATE} 不存在")
        if NEW in page.content:
            print(f"  = {TEMPLATE}: 已是目标状态，跳过")
            return
        n = page.content.count(OLD)
        if n != 1:
            raise SystemExit(f"{TEMPLATE} 的写法和脚本里记的不一样了（命中 {n} 次），人工看一下")
        content = page.content.replace(OLD, NEW)
        diff = difflib.unified_diff(
            page.content.split("\n"),
            content.split("\n"),
            f"{TEMPLATE} (old)",
            f"{TEMPLATE} (new)",
            lineterm="",
            n=0,
        )
        print("\n".join(diff))
        if ns.dry_run:
            print(f"  [dry-run] {TEMPLATE}（原 rev {page.revid}）")
            return
        await wiki.edit(TEMPLATE, content, SUMMARY, baserevid=page.revid, nocreate=True)
        print(f"  ✔ {TEMPLATE} 已写入（原 rev {page.revid}）")

        titles = [ref.title async for ref in wiki.iter_embeddedin(TEMPLATE)]
        purged = await wiki.purge(titles, forcelinkupdate=False)
        print(f"  ✔ 已清 {purged} / {len(titles)} 个嵌入页的解析缓存")


if __name__ == "__main__":
    asyncio.run(main())
