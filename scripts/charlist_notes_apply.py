"""干员一览顶部两条提示（公招计算 / 专属干员）在 Skin:Arknights 下改用设计系统的 `.ak-cbox--tip`，
不再走 `{{参阅}}` → `{{Cbox2}}`。对齐设计稿 prts-design `preview/_src/pages/operators.html` 的 `.ol-notes`：
两条并排、窄了折行。

- `模板:干员筛选`：两条提示都收进来，输出两份——
  `.ol-notes`（`.ak-cbox--tip` ×2，只在 Skin:Arknights 下显示）和
  `.ol-notes-legacy`（原来的 `{{参阅}}` ×2，Skin:Arknights 下藏掉）。
  旧皮肤没有 `.ak-cbox` 的样式，过渡期照旧看 Cbox2，渲染不变；旧皮肤退役时删掉 legacy 那份即可。
- `模板:干员筛选/styles.css`：追加 `.ol-notes` 的排布、两份的显隐、图标。
- `干员一览`：去掉页面上那条 `{{参阅|公招计算|公招计算}}`（已收进模板）。

图标：`<svg><use>` 在 wikitext 里会被转义，TemplateStyles 又不放行 `data:`（见 migration/patches 0001），
所以设计稿的 `#i-arrow-ne`（`M7 17 17 7M9 7h8v8`，线宽 2.5）按轮廓换算成 `clip-path: polygon()`，
盒子与颜色仍是皮肤的 `.ak-icon`（20px、currentColor）。

三种语言的文案照抄 `模板:参阅`（`#tsl` zh / ja / nozhja）。

    uv run python scripts/charlist_notes_apply.py --dry-run                   # 只打印 diff
    uv run python scripts/charlist_notes_apply.py -c config.sandbox.toml      # 先在沙箱演练
    uv run python scripts/charlist_notes_apply.py                             # 线上落地
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

SCRIPT = "prts-skin-migration/scripts/charlist_notes_apply.py"
SUMMARY = "干员一览顶部提示：Skin:Arknights 下改用 .ak-cbox--tip（旧皮肤照旧 Cbox2）。见 " + SCRIPT

LIST_PAGE = "干员一览"
TEMPLATE_PAGE = "模板:干员筛选"
STYLES_PAGE = "模板:干员筛选/styles.css"
MARKER = "ol-notes"

# (目标页面, 要查阅的事)；文案与 模板:参阅 一致
NOTES: list[tuple[str, str]] = [
    ("公招计算", "公招计算"),
    ("干员一览/专属干员", "仅在特殊模式中可选用的专属干员"),
]


def cbox(target: str, about: str) -> str:
    text = (
        f"{{{{#tsl:zh|如需了解'''{about}'''，您也可以查阅[[{target}]]页面。}}}}"
        f"{{{{#tsl:ja|'''{about}'''については、「[[{target}]]」 も参照してください。}}}}"
        f"{{{{#tsl:nozhja|If you want to learn more about '''{about}''', you can refer to [[{target}]].}}}}"
    )
    return (
        '<div class="ak-cbox ak-cbox--tip">'
        '<div class="ak-cbox__icon"><span class="ak-icon ol-i-arrow-ne"></span></div>'
        f'<div class="ak-cbox__body">{text}</div>'
        "</div>"
    )


LEGACY = "".join(f"{{{{参阅|{target}|{about}}}}}" for target, about in NOTES)
NOTES_HTML = (
    f'<div class="ol-notes-legacy">{LEGACY}</div>'
    f'<div class="ol-notes">{"".join(cbox(*note) for note in NOTES)}</div>'
)

STYLES_BLOCK = f"""

/* ── 顶部两条提示（公招计算 / 专属干员） ──
   .ol-notes = 设计系统的 .ak-cbox--tip ×2 并排，窄了折行（prts-design 的干员一览设计稿）。组件样式随 Skin:Arknights
   加载，旧皮肤没有，所以过渡期输出两份：旧皮肤看 .ol-notes-legacy（原来的 {{{{参阅}}}}），Skin:Arknights 看 .ol-notes。
   旧皮肤退役时删掉模板里 legacy 那份和这里的显隐。间距 8px / 16px = --ak-space-2 / --ak-space-4（站点的 TemplateStyles
   不认 var()，只能写数值）。由 {SCRIPT} 写入。 */
.ol-notes {{
	display: none;
}}

body.skin-arknights .ol-notes-legacy {{
	display: none;
}}

body.skin-arknights .ol-notes {{
	display: flex;
	flex-wrap: wrap;
	gap: 8px;
	margin: 0 0 16px;
}}

body.skin-arknights .ol-notes > .ak-cbox {{
	flex: 1 1 320px;
	margin: 0;
}}

/* 设计稿的 #i-arrow-ne：wikitext 里写不了 <svg>，TemplateStyles 不放行 data:，按轮廓裁出来；盒子与颜色是皮肤的 .ak-icon */
.ol-notes .ol-i-arrow-ne {{
	clip-path: polygon( 37.5% 23.96%, 76.04% 23.96%, 76.04% 62.5%, 65.63% 62.5%, 65.63% 41.74%, 32.85% 74.52%, 25.48% 67.15%, 58.26% 34.38%, 37.5% 34.38% );
}}"""

# (页面, 旧片段, 新片段)；旧片段必须恰好出现一次，对不上就停，不猜。
# 先模板后页面：中间态是旧皮肤下多一条公招计算提示，反过来则会少一条。
EDITS: list[tuple[str, str, str]] = [
    (TEMPLATE_PAGE, "{{参阅|干员一览/专属干员|仅在特殊模式中可选用的专属干员}}", NOTES_HTML),
    (LIST_PAGE, "{{参阅|公招计算|公招计算}}\n", ""),
]


def show_diff(title: str, old: str, new: str) -> None:
    diff = difflib.unified_diff(
        old.split("\n"), new.split("\n"), f"{title} (old)", f"{title} (new)", lineterm="", n=1
    )
    print("\n".join(diff))


async def write(wiki: Wiki, title: str, old: str, new: str, revid: int | None, dry_run: bool) -> None:
    show_diff(title, old, new)
    if dry_run:
        print(f"  [dry-run] {title}")
        return
    await wiki.edit(title, new, SUMMARY, baserevid=revid)
    print(f"  ✔ {title} 已写入")


async def apply_styles(wiki: Wiki, dry_run: bool) -> None:
    page = await wiki.read(STYLES_PAGE)
    if page.missing:
        raise SystemExit(f"  ✘ {STYLES_PAGE} 不存在")
    if MARKER in page.content:
        print(f"  = {STYLES_PAGE}: 已是目标内容，跳过")
        return
    await write(wiki, STYLES_PAGE, page.content, page.content.rstrip() + STYLES_BLOCK, page.revid, dry_run)


async def apply_page(wiki: Wiki, title: str, old_part: str, new_part: str, dry_run: bool) -> None:
    page = await wiki.read(title)
    if page.missing:
        raise SystemExit(f"  ✘ {title} 不存在")
    old = page.content
    # 模板改完后仍含旧片段（在 legacy 那份里），所以模板看标记；页面上没有标记，看旧片段还在不在
    if MARKER in old or (title == LIST_PAGE and old.count(old_part) == 0):
        print(f"  = {title}: 已是目标内容，跳过")
        return
    if old.count(old_part) != 1:
        raise SystemExit(f"  ✘ {title}: 旧片段出现 {old.count(old_part)} 次，页面和预期的不一样，没有动")
    await write(wiki, title, old, old.replace(old_part, new_part), page.revid, dry_run)


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

        # 样式先落：模板先改的话，两份提示会在样式到位前同时显示
        print(f"\n=== {STYLES_PAGE}")
        await apply_styles(wiki, ns.dry_run)
        for title, old_part, new_part in EDITS:
            print(f"\n=== {title}")
            await apply_page(wiki, title, old_part, new_part, ns.dry_run)
        if not ns.dry_run:
            purged = await wiki.purge([LIST_PAGE])
            print(f"\n已清缓存 {purged} 页（{LIST_PAGE}）")


if __name__ == "__main__":
    asyncio.run(main())
