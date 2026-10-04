"""赞助者公示的 SVG：新皮肤手机上把整页撑宽。

微件:Sponsor 是一个裸 ``<img width="768">``，不是 [[文件:]] 图，没有 ``mw-file-element`` 类，
皮肤 ``base/media.css`` 那条 ``max-width:100%`` 管不到它。390 宽下图伸出 366px 的正文栏，
整页被撑到 780px（浏览器跟着缩小到一半）。这里给它行内补上 ``max-width:100%;height:auto``：
窄屏按栏宽等比缩小，桌面仍是 768px。点图照旧在新标签页打开原图。

幂等：已是目标状态就跳过。

    uv run python scripts/sponsor_svg_apply.py --dry-run               # 只打印 diff
    uv run python scripts/sponsor_svg_apply.py -c config.sandbox.toml  # 沙箱演练
    uv run python scripts/sponsor_svg_apply.py                         # 线上落地
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

SCRIPT = "prts-skin-migration/scripts/sponsor_svg_apply.py"
SUMMARY = (
    "赞助者 SVG 加 max-width:100%;height:auto：裸 <img width=768> 在新皮肤手机宽度下伸出正文栏、把整页撑宽；"
    "桌面仍是 768px。见 " + SCRIPT
)

TITLE = "微件:Sponsor"
OLD = '<img inline-block="" width="768" src='
NEW = '<img inline-block="" width="768" style="max-width:100%;height:auto" src='
# #widget 不登记嵌入关系，用到它的页面手动列
PURGE = ["PRTS:如何帮助我们完善网站", "PRTS:赞助者一览", "用户:StarHeartHunt/sponsors"]


def rewrite(text: str) -> str:
    if NEW in text:
        return text
    n = text.count(OLD)
    if n != 1:
        raise SystemExit(f"{TITLE}: 期望出现 1 次，实际 {n} 次：{OLD}")
    return text.replace(OLD, NEW)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("-c", "--config", type=Path, help="换配置文件，如 config.sandbox.toml")
    ns = ap.parse_args()

    cfg = load_config(ns.config)
    print(f"目标站点：{cfg.api_url}")
    async with Wiki(cfg.api_url, cfg.user_agent, cfg.client, dry_run=ns.dry_run) as wiki:
        await wiki.login(*get_settings().require_credentials())
        page = await wiki.read(TITLE)
        if page.missing:
            raise SystemExit(f"{TITLE} 不存在")
        new = rewrite(page.content)
        if page.content.strip() == new.strip():
            print(f"  = {TITLE}: 已是目标状态，跳过")
            return
        diff = difflib.unified_diff(
            page.content.split("\n"), new.split("\n"), f"{TITLE} (old)", f"{TITLE} (new)", lineterm="", n=0
        )
        print("\n".join(line[:300] for line in diff))
        if ns.dry_run:
            print(f"  [dry-run] {TITLE}（r{page.revid}）")
            return
        await wiki.edit(TITLE, new, SUMMARY, baserevid=page.revid, nocreate=True)
        print(f"  ✔ {TITLE} 已写入")
        await wiki.purge(PURGE)
        print(f"  purge：{'、'.join(PURGE)}")


if __name__ == "__main__":
    asyncio.run(main())
