"""侧栏「新增干员」后的 NEW 角标偏下 1.7px：内联样式补一句 vertical-align。

`MediaWiki:MenuSidebar` 里这枚角标是 10px 的内联 span，默认 baseline 对齐，跟在 14px 的标签后面，
红块的中线比中文字形的中线低 ~1.7px（新皮肤 / Vector 一样；两套皮肤共用这一页）。
`vertical-align: middle` 不管用——它对的是 x-height 的一半，中文字的中线比那高。
按字形墨迹量（canvas measureText），提 .1em 时新皮肤（思源黑体 14px）差 0.05px，Vector（sans-serif 14.4px）
从 1.72px 降到 0.72px。用 em 不用 px：读者放大字号时跟着角标自己的字号走。

    uv run python scripts/sidebar_badge_apply.py --dry-run                 # 只打印 diff
    uv run python scripts/sidebar_badge_apply.py -c config.sandbox.toml    # 先在沙箱演练
    uv run python scripts/sidebar_badge_apply.py                           # 线上落地
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

TITLE = "MediaWiki:MenuSidebar"
SUMMARY = "侧栏 NEW 角标与文字竖向居中（vertical-align:.1em）。见 prts-skin-migration/scripts/sidebar_badge_apply.py"
OLD = 'font-weight:bold">NEW</span>'
NEW = 'font-weight:bold;vertical-align:.1em">NEW</span>'


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("-c", "--config", type=Path, help="换配置文件，如 config.sandbox.toml 先在沙箱演练")
    ns = ap.parse_args()

    cfg = load_config(ns.config)
    print(f"目标站点：{cfg.api_url}")
    settings = get_settings()
    async with Wiki(cfg.api_url, cfg.user_agent, cfg.client, dry_run=ns.dry_run) as wiki:
        username, password = settings.require_credentials()
        await wiki.login(username, password)
        page = await wiki.read(TITLE)
        if page.missing:
            raise SystemExit(f"{TITLE} 不存在")
        if NEW in page.content:
            print(f"  = {TITLE}: 已是目标状态，跳过")
            return
        n = page.content.count(OLD)
        if n != 1:
            raise SystemExit(f"NEW 角标的写法和脚本里记的不一样了（命中 {n} 次），人工看一下")
        new = page.content.replace(OLD, NEW)
        diff = difflib.unified_diff(
            page.content.split("\n"), new.split("\n"), f"{TITLE} (old)", f"{TITLE} (new)", lineterm="", n=0
        )
        print("\n".join(diff))
        if ns.dry_run:
            print(f"  [dry-run] {TITLE}（原 rev {page.revid}）")
            return
        await wiki.edit(TITLE, new, SUMMARY, baserevid=page.revid, nocreate=True)
        print(f"  ✔ {TITLE} 已写入（原 rev {page.revid}）")


if __name__ == "__main__":
    asyncio.run(main())
