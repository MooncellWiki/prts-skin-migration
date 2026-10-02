"""站点公告横幅适配新皮肤：把 migration/sitenotice/ 下的两段写进
MediaWiki:Sitenotice top（桌面）和 MediaWiki:Sitenotice mobile（手机）。

两页只换外层样式，公告文字原样保留。公告是 Rafom 在站内维护的，文字随时会换：
现网正文里找不到源文件里的那句公告时直接停下，不拿旧文字盖掉。见 migration/sitenotice/README.md。

    uv run python scripts/sitenotice_apply.py --dry-run                   # 只打印 diff
    uv run python scripts/sitenotice_apply.py -c config.sandbox.toml      # 先在沙箱演练
    uv run python scripts/sitenotice_apply.py                             # 线上落地
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wikibot.config import get_settings, load_config
from wikibot.wiki import Wiki

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "migration" / "sitenotice"
SUMMARY = (
    "公告横幅适配新皮肤：去掉 800px 定宽，窄屏不再撑宽页面；暗色下链接不再是浅青色。"
    "见 prts-skin-migration/migration/sitenotice/README.md"
)

PAGES = {
    "MediaWiki:Sitenotice top": SRC / "MediaWiki_Sitenotice_top.wiki",
    "MediaWiki:Sitenotice mobile": SRC / "MediaWiki_Sitenotice_mobile.wiki",
}

# 源文件是单个 <div style="…">公告</div>，取出中间的公告文字
MESSAGE_RE = re.compile(r'^<div style="[^"]*">(.*)</div>$', re.S)


async def apply_page(wiki: Wiki, title: str, src: Path, dry_run: bool) -> None:
    text = src.read_text(encoding="utf-8").strip()
    m = MESSAGE_RE.match(text)
    if not m:
        raise SystemExit(f"{src.name} 不是单个 <div style=…> 包着的公告")
    message = m.group(1)

    page = await wiki.read(title)
    if page.missing:
        raise SystemExit(f"{title} 不存在")
    if page.content.strip() == text:
        print(f"  = {title}: 已是目标内容，跳过")
        return
    if message not in page.content:
        raise SystemExit(
            f"{title} 的公告文字和源文件对不上（站内改过？），先把 {src.name} 的文字同步成现网再跑：\n"
            f"  现网：{page.content.strip()}"
        )
    diff = difflib.unified_diff(
        page.content.strip().split("\n"),
        text.split("\n"),
        f"{title} (old)",
        f"{title} (new)",
        lineterm="",
        n=0,
    )
    print("\n".join(diff))
    if dry_run:
        print(f"  [dry-run] {title}")
        return
    await wiki.edit(title, text, SUMMARY, baserevid=page.revid)
    print(f"  ✔ {title} 已写入")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "-c",
        "--config",
        type=Path,
        help="换配置文件，如 config.sandbox.toml 先在沙箱演练",
    )
    ns = ap.parse_args()

    cfg = load_config(ns.config)
    print(f"目标站点：{cfg.api_url}")
    async with Wiki(
        cfg.api_url, cfg.user_agent, cfg.client, dry_run=ns.dry_run
    ) as wiki:
        await wiki.login(*get_settings().require_credentials())
        for title, src in PAGES.items():
            print(f"\n=== {title}")
            await apply_page(wiki, title, src, ns.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
