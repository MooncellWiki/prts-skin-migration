"""干员立绘舞台（CharinfoV2）宽度适配：
把 migration/charinfo-fit/微件_CharinfoV2.wiki 写进 微件:CharinfoV2。

整页覆盖（源文件是唯一来源），源文件基于 BASE_REVID；
线上若已有别人的新修订，先把它合进源文件再改 BASE_REVID，否则会被整页覆盖掉。
见 migration/charinfo-fit/README.md。

    uv run python scripts/charinfo_fit_apply.py --dry-run               # 只打印 diff
    uv run python scripts/charinfo_fit_apply.py -c config.sandbox.toml  # 沙箱演练
    uv run python scripts/charinfo_fit_apply.py                         # 线上落地
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
SRC = ROOT / "migration" / "charinfo-fit" / "微件_CharinfoV2.wiki"
TITLE = "微件:CharinfoV2"
BASE_REVID = 410622  # 线上 2026-07-27 的修订，源文件在它的基础上改
SUMMARY = (
    "立绘舞台写死 1024px 宽，正文栏不够宽时收窄到正文栏宽，不再溢出容器（纯 CSS）。"
    "见 prts-skin-migration/migration/charinfo-fit/README.md"
)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "-c", "--config", type=Path, help="换配置文件，如 config.sandbox.toml"
    )
    ap.add_argument(
        "--force", action="store_true", help="线上修订不是 BASE_REVID 时也覆盖"
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
        if page.revid != BASE_REVID and not ns.force:
            raise SystemExit(
                f"{TITLE} 线上是 r{page.revid}，源文件基于 r{BASE_REVID}："
                "先把新修订合进源文件，或确认无误后加 --force"
            )
        if ns.dry_run:
            print(f"  [dry-run] {TITLE}（r{page.revid}）")
            return
        await wiki.edit(TITLE, new, SUMMARY, baserevid=page.revid, nocreate=True)
        print(f"  ✔ {TITLE} 已写入")


if __name__ == "__main__":
    asyncio.run(main())
