"""把页脚底栏一句话（MediaWiki:Arknights-footer-tagline）改成「版权段 + 备案号」两段式排版。

底栏的 `#footer-tagline` 是一个会自己折行的 flex 子项，备案号里「京|ICP|备|2002…|号」的
中西文交界处处都是断行点，窄屏下会从中间拦腰折断。这里只靠字符控制断行，不动皮肤 CSS：

- 段内的空格换成 NBSP（U+00A0），断行点后面垫 WORD JOINER（U+2060），两段各自不可拆；
- 两段之间放一个 EM SPACE（U+2003）：既是比普通空格宽的间隔，也是全句唯一的断行点，
  放不下时备案号整体掉到下一行。

全部写成字符引用而不是字面字符，源码里看得见、编辑器也不会悄悄吃掉。

    uv run python scripts/footer_tagline_apply.py --dry-run                   # 只打印 diff
    uv run python scripts/footer_tagline_apply.py -c config.sandbox.toml      # 先在沙箱演练
    uv run python scripts/footer_tagline_apply.py                             # 线上落地
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

SCRIPT = "prts-skin-migration/scripts/footer_tagline_apply.py"
SUMMARY = "页脚底栏：版权段与备案号之间加宽间隔，备案号整体换行（NBSP / WORD JOINER / EM SPACE）。见 " + SCRIPT

TITLE = "MediaWiki:Arknights-footer-tagline"

NBSP = "&nbsp;"
WJ = "&#x2060;"
EMSP = "&emsp;"

# 「–」后、中西文交界、「-」后都是断行点，逐个用 WJ 粘住
COPYRIGHT = f"©{NBSP}2019–{WJ}{{{{CURRENTYEAR}}}}{NBSP}PRTS.wiki"
BEIAN = f"[https://beian.miit.gov.cn/ 京{WJ}ICP{WJ}备{WJ}20024624{WJ}号-{WJ}1]"
TEXT = COPYRIGHT + EMSP + BEIAN


async def apply_page(wiki: Wiki, title: str, dry_run: bool) -> None:
    page = await wiki.read(title)
    old = "" if page.missing else page.content
    if old.strip() == TEXT:
        print(f"  = {title}: 已是目标内容，跳过")
        return
    diff = difflib.unified_diff(
        old.split("\n"), TEXT.split("\n"), f"{title} (old)", f"{title} (new)", lineterm="", n=2
    )
    print("\n".join(diff))
    if dry_run:
        print(f"  [dry-run] {title}")
        return
    await wiki.edit(
        title,
        TEXT,
        SUMMARY,
        baserevid=None if page.missing else page.revid,
        nocreate=False,
    )
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
        print(f"\n=== {TITLE}")
        await apply_page(wiki, TITLE, ns.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
