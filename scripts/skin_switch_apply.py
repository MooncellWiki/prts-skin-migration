"""新旧皮肤切换按钮：把 migration/skin-switch/微件_SkinSwitch.wiki 写进 微件:SkinSwitch。

页面不存在就新建，已存在就整页覆盖（源文件是唯一来源）。见 migration/skin-switch/README.md。

    uv run python scripts/skin_switch_apply.py --dry-run               # 只打印 diff
    uv run python scripts/skin_switch_apply.py -c config.sandbox.toml  # 沙箱演练
    uv run python scripts/skin_switch_apply.py                         # 线上落地
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

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "migration" / "skin-switch" / "微件_SkinSwitch.wiki"
TITLE = "微件:SkinSwitch"
SUMMARY = "新旧皮肤切换按钮。见 prts-skin-migration/migration/skin-switch/README.md"


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
        old = "" if page.missing else page.content
        new = SRC.read_text(encoding="utf-8").rstrip("\n")
        if old == new:
            print(f"  = {TITLE}: 已是目标内容，跳过")
            return
        diff = difflib.unified_diff(
            old.split("\n"),
            new.split("\n"),
            f"{TITLE} (old)",
            f"{TITLE} (new)",
            lineterm="",
            n=2,
        )
        print("\n".join(diff))
        if ns.dry_run:
            print(f"  [dry-run] {TITLE}")
            return
        await wiki.edit(
            TITLE,
            new,
            SUMMARY,
            baserevid=None if page.missing else page.revid,
            nocreate=not page.missing,
        )
        print(f"  ✔ {TITLE} 已写入")


if __name__ == "__main__":
    asyncio.run(main())
