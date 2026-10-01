"""给干员一览的数据块（#filter-data）加上游戏内 ID：`data-char-id="char_002_amiya"`。

新版干员一览（prts-widgets 的 CharList）的头像 / 半身像改从 torappu.prts.wiki 取，那边按游戏内 ID
寻址（`/assets/char_avatar/<charId>.png`），而数据块里只有中文名和情报编号（`data-id="R001"`）。

- `模板:干员筛选数据/4`：多输出一个 `data-char-id="{{{36|}}}"`。属性名用连字符——MediaWiki 1.43 的
  Sanitizer 会丢掉带下划线的 data-*；给了空默认值，查询那头还没带上这一列时输出空串而不是字面的 `{{{36}}}`。
- `模板:干员筛选`：cargo 查询末尾加一列 `chara.charId`。加在最后，前 35 个位置参数不动。

先写数据行模板、再写查询，中间任何时刻页面都是好的。Widget 读不到这个属性时照旧按中文名走 media。

    uv run python scripts/charlist_charid_apply.py --dry-run                   # 只打印 diff
    uv run python scripts/charlist_charid_apply.py -c config.sandbox.toml      # 先在沙箱演练
    uv run python scripts/charlist_charid_apply.py                             # 线上落地
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

SCRIPT = "prts-skin-migration/scripts/charlist_charid_apply.py"
SUMMARY = "干员一览数据加游戏内 ID（data-char-id），头像 / 半身像改从 torappu 取。见 " + SCRIPT

LIST_PAGE = "干员一览"

# (页面, 旧片段, 新片段)；旧片段必须恰好出现一次，对不上就停，不猜
EDITS: list[tuple[str, str, str]] = [
    (
        "模板:干员筛选数据/4",
        'data-group="{{{35}}}">',
        'data-group="{{{35}}}" data-char-id="{{{36|}}}">',
    ),
    (
        "模板:干员筛选",
        "chara.org=组织\n|limit=5000",
        "chara.org=组织,\nchara.charId=干员id\n|limit=5000",
    ),
]


async def apply_page(wiki: Wiki, title: str, old_part: str, new_part: str, dry_run: bool) -> None:
    page = await wiki.read(title)
    if page.missing:
        raise SystemExit(f"  ✘ {title} 不存在")
    old = page.content
    if new_part in old:
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
        if not ns.dry_run:
            purged = await wiki.purge([LIST_PAGE])
            print(f"\n已清缓存 {purged} 页（{LIST_PAGE}）")


if __name__ == "__main__":
    asyncio.run(main())
