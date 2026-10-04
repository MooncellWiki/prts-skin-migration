"""剧情跳转按钮（模板:剧情跳转）在 Skin:Arknights 下第二行字被裁：文字框写死 height:41px; overflow:hidden; line-height:initial，
新皮肤正文 16px 思源黑体，两行 46px，框里只有 43px。Vector 是 14px，两行 40px 正好放得下。

按钮是定死尺寸的图形（141×41），字号不该跟皮肤正文走：`line-height: initial;` 换成 `font-size:14px;line-height:19px;`，
两行 38px，各皮肤一致，与原来 Vector 下几乎一样。见 migration/story-play-button/README.md。

    uv run python scripts/story_jump_apply.py --dry-run
    uv run python scripts/story_jump_apply.py
    uv run python scripts/purge_embeddedin.py 模板:剧情跳转     # 写完清嵌入页缓存
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

TEMPLATE = "模板:剧情跳转"
SUMMARY = (
    "按钮文字在新皮肤下第二行被裁（正文 16px，两行放不下 41px 的框）：字号行高定成 14px / 19px，各皮肤一致。"
    "见 prts-skin-migration/migration/story-play-button/README.md"
)
OLD = "padding: 2px 0px 0px 4px;line-height: initial;"
NEW = "padding: 2px 0px 0px 4px;font-size:14px;line-height:19px;"


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
            page.content.split("\n"), content.split("\n"), f"{TEMPLATE} (old)", f"{TEMPLATE} (new)", lineterm="", n=0
        )
        print("\n".join(diff))
        if ns.dry_run:
            print(f"  [dry-run] {TEMPLATE}（原 rev {page.revid}）")
            return
        await wiki.edit(TEMPLATE, content, SUMMARY, baserevid=page.revid, nocreate=True)
        print(f"  ✔ {TEMPLATE} 已写入（原 rev {page.revid}）")


if __name__ == "__main__":
    asyncio.run(main())
