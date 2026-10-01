"""navbox 窄屏不撑破页面：把 migration/navbox-narrow/navbox-narrow.css
写进 模板:Navbox/styles.css。

区块放在布局规则之后、theme:begin 配色区块之前，用 layout:begin/end 标记包住，
重跑只替换标记之间的内容。见 migration/navbox-narrow/README.md。

    uv run python scripts/navbox_narrow_apply.py --dry-run               # 只打印 diff
    uv run python scripts/navbox_narrow_apply.py -c config.sandbox.toml  # 沙箱演练
    uv run python scripts/navbox_narrow_apply.py                         # 线上落地
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
CSS = ROOT / "migration" / "navbox-narrow" / "navbox-narrow.css"
TITLE = "模板:Navbox/styles.css"
NAME = "navbox-narrow"
NOTE = "窄屏不撑破页面，见 prts-skin-migration/migration/navbox-narrow/README.md"
ANCHOR = "/* theme:begin navbox-palette"
SUMMARY = (
    "navbox 窄屏（≤1119px）不再撑宽页面：列表项可在项内折行，"
    "手机上分组名按空格 / 标点折行。见 prts-skin-migration/migration/navbox-narrow/README.md"
)

BLOCK_RE = re.compile(
    rf"/\* layout:begin {re.escape(NAME)} .*?\*/\n.*?/\* layout:end {re.escape(NAME)} \*/",
    re.S,
)


def upsert(text: str) -> str:
    body = CSS.read_text(encoding="utf-8").strip()
    block = f"/* layout:begin {NAME} {NOTE} */\n{body}\n/* layout:end {NAME} */"
    if BLOCK_RE.search(text):
        return BLOCK_RE.sub(lambda _: block, text, count=1)
    n = text.count(ANCHOR)
    if n != 1:
        raise SystemExit(f"插入锚点期望出现 1 次，实际 {n} 次：{ANCHOR}")
    return text.replace(ANCHOR, block + "\n\n" + ANCHOR)


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
        new = upsert(page.content)
        if new == page.content:
            print(f"  = {TITLE}: 已是目标状态，跳过")
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
