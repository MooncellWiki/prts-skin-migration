"""干员一览页面上去掉没人读的两块数据：`#filter-map` 和 `#filter-shortLinkMap`。

两块都是旧版 CharList 用的（势力归并表 / 短链接缩写表），prts-widgets 在 2023-06 的
`refactor(charList): 筛选势力 (#23)` 之后就不读了：归并改成筛选项里的 `{label, value}`，
地址栏参数直接写字段名 + 选项文字。全站模板 / 微件 / 模块 / MediaWiki 名字空间里也没有别的地方引用。

- `微件:CharList/dev`：noinclude 里去掉这两个 div。
- `微件:CharList/doc`：去掉末尾那个裸的 `{{#widget:CharList/shortLinkMap}}</div>`
  （没有开标签，整份 JSON 直接印在文档页上）。

`#filter-filter` 这次不动：现网的 CharList 包还在读它，要等筛选项写死进 widget 的那一版上线之后再删。
`微件:CharList/map`、`微件:CharList/shortLinkMap` 两个页面本身也留着，删页面另说。

    uv run python scripts/charlist_unused_maps_apply.py --dry-run                   # 只打印 diff
    uv run python scripts/charlist_unused_maps_apply.py -c config.sandbox.toml      # 先在沙箱演练
    uv run python scripts/charlist_unused_maps_apply.py                             # 线上落地
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

SCRIPT = "prts-skin-migration/scripts/charlist_unused_maps_apply.py"
SUMMARY = "去掉 CharList 早已不读的 #filter-map / #filter-shortLinkMap。见 " + SCRIPT

# (页面, 旧片段, 新片段)；旧片段必须恰好出现一次，对不上就停，不猜
EDITS: list[tuple[str, str, str]] = [
    (
        "微件:CharList/dev",
        '<div id="filter-map" style="display:none">{{#widget:CharList/map}}</div>'
        '<div id="filter-shortLinkMap" style="display: none;">{{#widget:CharList/shortLinkMap}}</div>',
        "",
    ),
    (
        "微件:CharList/doc",
        "{{#widget:CharList/filter}}</div>{{#widget:CharList/shortLinkMap}}</div>",
        "{{#widget:CharList/filter}}</div>",
    ),
]


async def apply_page(wiki: Wiki, title: str, old_part: str, new_part: str, dry_run: bool) -> None:
    page = await wiki.read(title)
    if page.missing:
        raise SystemExit(f"  ✘ {title} 不存在")
    old = page.content
    if old.count(old_part) == 0:
        print(f"  = {title}: 已是目标内容，跳过")
        return
    if old.count(old_part) != 1:
        raise SystemExit(f"  ✘ {title}: 旧片段出现 {old.count(old_part)} 次，页面和预期的不一样，没有动")
    new = old.replace(old_part, new_part)
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
        for title, old_part, new_part in EDITS:
            print(f"\n=== {title}")
            await apply_page(wiki, title, old_part, new_part, ns.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
