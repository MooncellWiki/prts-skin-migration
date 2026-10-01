"""干员一览页面上去掉 `#filter-filter`：筛选项定义已经写死进 CharList（prts-widgets 的
`src/widgets/CharList/filterGroups.ts`），模板不用再把 `微件:CharList/filter` 输出到页面上。

**顺序要紧**：旧的 CharList 包启动时 `JSON.parse(#filter-filter 的正文)`，div 没了直接抛错、整页不出。
所以写之前先看 `微件:CharList` 现在指向的那个包还读不读 `#filter-filter`，还读就停。

- `模板:干员筛选`（干员一览正式页用的）
- `微件:CharList/dev`、`微件:CharList/doc`

`微件:CharList/filter`、`微件:CharList/dev/filter` 两个页面本身留着，删页面另说。

    uv run python scripts/charlist_filter_div_apply.py --dry-run                   # 只打印 diff
    uv run python scripts/charlist_filter_div_apply.py -c config.sandbox.toml      # 先在沙箱演练
    uv run python scripts/charlist_filter_div_apply.py                             # 线上落地
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

from wikibot.config import get_settings, load_config  # noqa: E402
from wikibot.wiki import Wiki  # noqa: E402

SCRIPT = "prts-skin-migration/scripts/charlist_filter_div_apply.py"
SUMMARY = "去掉 #filter-filter：筛选项定义已写进 CharList 本身。见 " + SCRIPT

WIDGET_PAGE = "微件:CharList"
LIST_PAGE = "干员一览"
MARKER = "filter-filter"

# (页面, 旧片段)；旧片段必须恰好出现一次，对不上就停，不猜
EDITS: list[tuple[str, str]] = [
    (
        "模板:干员筛选",
        '<div id="filter-filter" style="display:none">{{#widget:CharList/filter}}</div>',
    ),
    (
        "微件:CharList/dev",
        '<div id="filter-filter" style="display:none">{{#widget:CharList/dev/filter}}</div>',
    ),
    (
        "微件:CharList/doc",
        '<div id="filter-filter" style="display:none">{{#widget:CharList/filter}}</div>',
    ),
]


async def deployed_bundle_reads_marker(wiki: Wiki, user_agent: str) -> bool:
    """`微件:CharList` 现在引的 CharList.*.js 里还有没有 `#filter-filter`。"""
    page = await wiki.read(WIDGET_PAGE)
    urls = re.findall(r'src="(https?://[^"]*/CharList\.[^"]*\.js)"', page.content)
    if not urls:
        raise SystemExit(f"  ✘ {WIDGET_PAGE} 里没找到 CharList 的入口脚本，没有动")
    async with httpx.AsyncClient(headers={"User-Agent": user_agent}, timeout=60) as client:
        for url in urls:
            resp = await client.get(url)
            resp.raise_for_status()
            print(f"  {url}: {'还在读' if MARKER in resp.text else '不读'} #{MARKER}")
            if MARKER in resp.text:
                return True
    return False


async def apply_page(wiki: Wiki, title: str, old_part: str, dry_run: bool) -> None:
    page = await wiki.read(title)
    if page.missing:
        raise SystemExit(f"  ✘ {title} 不存在")
    old = page.content
    if old.count(old_part) == 0 and MARKER not in old:
        print(f"  = {title}: 已是目标内容，跳过")
        return
    if old.count(old_part) != 1:
        raise SystemExit(f"  ✘ {title}: 旧片段出现 {old.count(old_part)} 次，页面和预期的不一样，没有动")
    new = old.replace(old_part, "")
    diff = difflib.unified_diff(
        old.split("\n"), new.split("\n"), f"{title} (old)", f"{title} (new)", lineterm="", n=1
    )
    print("\n".join(diff))
    if dry_run:
        print(f"  [dry-run] {title}")
        return
    await wiki.edit(title, new, SUMMARY, baserevid=page.revid)
    print(f"  ✔ {title} 已写入")


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

        print(f"\n=== {WIDGET_PAGE} 当前的包")
        if await deployed_bundle_reads_marker(wiki, cfg.user_agent):
            if not ns.dry_run:
                raise SystemExit(f"  ✘ 线上的包还在读 #{MARKER}，现在删会让{LIST_PAGE}挂掉，没有动")
            print("  ! 线上的包还在读，真跑会在这里停下")

        for title, old_part in EDITS:
            print(f"\n=== {title}")
            await apply_page(wiki, title, old_part, ns.dry_run)
        if not ns.dry_run:
            purged = await wiki.purge([LIST_PAGE])
            print(f"\n已清缓存 {purged} 页（{LIST_PAGE}）")


if __name__ == "__main__":
    asyncio.run(main())
