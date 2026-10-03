"""干员一览、公招计算顶部挂 {{页面迭代}}（「这个页面的样式将要发生重大变化」），只在 Arknights 以外的皮肤显示。

- `模板:页面迭代/styles.css`：新建，源文件 migration/page-iteration/模板_页面迭代_styles.css，
  `body.skin-arknights .prts-page-iteration` 藏掉。
- `模板:页面迭代`：框外包一层 `.prts-page-iteration`，带上样式。模板是 Rafom 在站内维护的，文案随时会换：
  不拿快照覆盖，只给现网正文套外壳。
- `干员一览` / `公招计算`：正文最前面加 {{页面迭代}}，和原来第一行接在一起，不多出空行。

解析缓存不分皮肤，所以模板对谁都输出，由 body 上的皮肤类二选一（同 模板:首页/旧版）。见 migration/page-iteration/README.md。

    uv run python scripts/page_iteration_apply.py --dry-run                   # 只打印 diff
    uv run python scripts/page_iteration_apply.py -c config.sandbox.toml      # 先在沙箱演练
    uv run python scripts/page_iteration_apply.py                             # 线上落地
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
SRC = ROOT / "migration" / "page-iteration"
SCRIPT = "prts-skin-migration/scripts/page_iteration_apply.py"
SUMMARY = "{{页面迭代}} 只在 Arknights 以外的皮肤显示，挂到干员一览、公招计算顶部。见 " + SCRIPT

TEMPLATE_PAGE = "模板:页面迭代"
STYLES_PAGE = "模板:页面迭代/styles.css"
STYLES_SRC = SRC / "模板_页面迭代_styles.css"
MARKER = "prts-page-iteration"
OPEN = f'<templatestyles src="页面迭代/styles.css" /><div class="{MARKER}">'
CLOSE = "</div>"
NOTE = "只在 Arknights 以外的皮肤显示，Arknights 皮肤下由 [[模板:页面迭代/styles.css]] 藏掉。"
CALL = "{{页面迭代}}"
PAGES = ["干员一览", "公招计算"]


def show_diff(title: str, old: str, new: str) -> None:
    diff = difflib.unified_diff(
        old.split("\n"), new.split("\n"), f"{title} (old)", f"{title} (new)", lineterm="", n=1
    )
    print("\n".join(diff))


async def write(
    wiki: Wiki, title: str, old: str, new: str, revid: int | None, dry_run: bool, create: bool = False
) -> None:
    show_diff(title, old, new)
    if dry_run:
        print(f"  [dry-run] {title}")
        return
    await wiki.edit(title, new, SUMMARY, baserevid=revid, nocreate=not create)
    print(f"  ✔ {title} 已写入")


def wrap_template(text: str) -> str:
    """把 <noinclude> 之前的框包进 .prts-page-iteration；结构对不上就停，不猜。"""
    body, sep, tail = text.partition("<noinclude>")
    if not sep or "<noinclude>" in tail or not body.lstrip().startswith("{{cbox2"):
        raise SystemExit(f"  ✘ {TEMPLATE_PAGE}: 不是「{{{{cbox2…}}}}<noinclude>…</noinclude>」，站内改过结构？没有动")
    return f"{OPEN}{body.strip()}{CLOSE}<noinclude>{NOTE}{tail}"


async def apply_styles(wiki: Wiki, dry_run: bool) -> None:
    text = STYLES_SRC.read_text(encoding="utf-8")
    page = await wiki.read(STYLES_PAGE)
    old = "" if page.missing else page.content
    if old.strip() == text.strip():
        print(f"  = {STYLES_PAGE}: 已是目标内容，跳过")
        return
    await write(wiki, STYLES_PAGE, old, text, None if page.missing else page.revid, dry_run, create=True)


async def apply_template(wiki: Wiki, dry_run: bool) -> None:
    page = await wiki.read(TEMPLATE_PAGE)
    if page.missing:
        raise SystemExit(f"  ✘ {TEMPLATE_PAGE} 不存在")
    if MARKER in page.content:
        print(f"  = {TEMPLATE_PAGE}: 已是目标内容，跳过")
        return
    await write(wiki, TEMPLATE_PAGE, page.content, wrap_template(page.content), page.revid, dry_run)


async def apply_page(wiki: Wiki, title: str, dry_run: bool) -> None:
    page = await wiki.read(title)
    if page.missing:
        raise SystemExit(f"  ✘ {title} 不存在")
    if CALL in page.content:
        print(f"  = {title}: 已挂上，跳过")
        return
    await write(wiki, title, page.content, CALL + page.content, page.revid, dry_run)


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

        # 样式 → 模板 → 页面：模板先挂上页面的话，样式到位前 Arknights 皮肤下会露出来
        print(f"\n=== {STYLES_PAGE}")
        await apply_styles(wiki, ns.dry_run)
        print(f"\n=== {TEMPLATE_PAGE}")
        await apply_template(wiki, ns.dry_run)
        for title in PAGES:
            print(f"\n=== {title}")
            await apply_page(wiki, title, ns.dry_run)
        if not ns.dry_run:
            purged = await wiki.purge([TEMPLATE_PAGE, *PAGES])
            print(f"\n已清缓存 {purged} 页（{TEMPLATE_PAGE}、{'、'.join(PAGES)}）")


if __name__ == "__main__":
    asyncio.run(main())
