"""活动页英文副标题适配 Skin:Arknights：
把 migration/subname/微件_Subname.wiki 写进 微件:Subname。

整页覆盖（源文件是唯一来源）；旧皮肤分支一字不改。见 migration/subname/README.md。

    uv run python scripts/subname_apply.py --dry-run               # 只打印 diff
    uv run python scripts/subname_apply.py -c config.sandbox.toml  # 沙箱演练
    uv run python scripts/subname_apply.py                         # 线上落地
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

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "migration" / "subname" / "微件_Subname.wiki"
TITLE = "微件:Subname"
SUMMARY = (
    "Skin:Arknights 下副标题改放进标题的 .ak-en 位（标题下方一行），"
    "不再右浮动把标题挤断；"
    "旧皮肤不变。见 prts-skin-migration/migration/subname/README.md"
)


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
        page = await wiki.read(TITLE)
        if page.missing:
            raise SystemExit(f"{TITLE} 不存在")
        new = SRC.read_text(encoding="utf-8").rstrip("\n")
        if page.content == new:
            print(f"  = {TITLE}: 已是目标内容，跳过")
            return
        diff = difflib.unified_diff(
            page.content.split("\n"),
            new.split("\n"),
            f"{TITLE} (old)",
            f"{TITLE} (new)",
            lineterm="",
            n=2,
        )
        print("\n".join(diff))
        if ns.dry_run:
            print(f"  [dry-run] {TITLE}（r{page.revid}）")
            return
        await wiki.edit(TITLE, new, SUMMARY, baserevid=page.revid, nocreate=True)
        print(f"  ✔ {TITLE} 已写入")


if __name__ == "__main__":
    asyncio.run(main())
