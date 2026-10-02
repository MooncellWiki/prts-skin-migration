"""Cbox2 换成 .ak-cbox 之后，清掉站内还写着旧类名的样式，并适配一处页面级样式。

旧 模板:Cbox2/core 输出的 .cbox2 / .cbox2-lv-N / .cbox2-custom-color / .cbox2-icon / .cbox2-content /
.cbox2-mobile / .cbox-autonarrow 已经不存在（见 migration/cbox2/README.md），下面这些规则全都匹配不到任何元素：

- MediaWiki:Common.css、Gadget-Vector2022Fixes.css、Gadget-Vector2022LayoutFixes.css：
  Vector 2022 窄屏下 `.nodesktop.cbox2-mobile` 显示成 flex（Cbox2 的移动版那一份）
- MediaWiki:Vector.css：`div.cbox-autonarrow` 1500px 以下收窄到 640px
- MediaWiki:Gadget-darkModeFix.css：编辑页系统消息里 Cbox2 的暗色，同一段复制了 5 份，共 30 条
- 模板:孤星2024/styles.css：专项调查说明框的暗色（现在由 Cbox2/styles.css 的复刻参阅紫色框统一给）

只删「每个选择器都只针对旧类名」的规则，连同只为它们写的注释、删空的 @media；其余规则逐条比对不变，
旧类名删不干净就停。孤星2024 的自动偏好（os）分支按剩下的 night 规则重新生成。

适配：岁的界园志异/事件一览 用 `{{#widget:style}}` 把「如岁：进入传说」这类切换框限宽到 35rem，
选择器从 `.legend_switch .nomobile.cbox-autonarrow` 换成 `.legend_switch .ak-cbox`。

    uv run python scripts/cbox2_legacy_cleanup_apply.py --dry-run                   # 只打印 diff
    uv run python scripts/cbox2_legacy_cleanup_apply.py -c config.sandbox.toml      # 先在沙箱演练
    uv run python scripts/cbox2_legacy_cleanup_apply.py                             # 线上落地
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import re
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wikibot.config import get_settings, load_config
from wikibot.theme_os import add_os_branch, parse_rules, strip_generated
from wikibot.wiki import Wiki

DOC = "prts-skin-migration/migration/cbox2/README.md"
SUMMARY = "Cbox2 已换成设计系统 .ak-cbox，{}。见 " + DOC

DEAD = re.compile(r"\bcbox2\b|\bcbox2-[\w-]+|\bcbox-autonarrow\b")
# 只为旧规则写的注释（删规则时一起删）
DEAD_COMMENT = re.compile(
    r"/\*\s*(?:Edit page head copy warning[^*]*|为cbox2设置自动宽度\s*)\*/"
)


def _split_lead(prelude: str) -> tuple[str, str]:
    """把规则前面的空白与注释（lead）和选择器分开。"""
    pos = 0
    while True:
        rest = prelude[pos:]
        stripped = rest.lstrip()
        pos += len(rest) - len(stripped)
        if not stripped.startswith("/*"):
            return prelude[:pos], prelude[pos:]
        end = prelude.find("*/", pos)
        if end < 0:
            return prelude[:pos], prelude[pos:]
        pos = end + 2


def _is_dead(selector: str) -> bool:
    parts = [s for s in re.sub(r"/\*.*?\*/", "", selector, flags=re.S).split(",")]
    parts = [s.strip() for s in parts if s.strip()]
    return bool(parts) and all(DEAD.search(s) for s in parts)


def drop_dead_rules(css: str) -> str:
    out: list[str] = []
    pos = 0
    for m in re.finditer(r"([^{}]*)\{[^{}]*\}", css):
        lead, selector = _split_lead(m.group(1))
        if selector.lstrip().startswith("@") or not _is_dead(selector):
            continue
        out.append(css[pos : m.start()])
        kept = DEAD_COMMENT.sub("", lead)
        if kept.strip():  # 规则前面别的注释留着
            out.append(kept.rstrip())
        pos = m.end()
    out.append(css[pos:])
    css = "".join(out)
    # 删空的 @media，连同它前面只为旧规则写的注释
    empty_media = re.compile(
        r"(?:\s*" + DEAD_COMMENT.pattern + r")?\s*@media[^{}]*\{\s*\}"
    )
    return empty_media.sub("", css)


def live_rules(css: str) -> list:
    return [
        r
        for r in parse_rules(strip_generated(css))
        if not all(DEAD.search(s) for s in r.selectors)
    ]


def cleanup(stylesheet: bool = False) -> Callable[[str], str]:
    def tf(text: str) -> str:
        base = strip_generated(text) if stylesheet else text
        new = drop_dead_rules(base)
        if stylesheet:  # os 分支总是按剩下的 night 规则重新生成
            new, _ = add_os_branch(new)
        if new.rstrip() == text.rstrip():
            return text
        if DEAD.search(re.sub(r"/\*.*?\*/", "", new, flags=re.S)):
            raise SystemExit(f"删完还有旧类名：{DEAD.search(new)[0]!r}，没有动")
        if live_rules(new) != live_rules(text):
            raise SystemExit("删除波及了别的规则，没有动")
        return new

    return tf


LEGEND_OLD = (
    "{{#widget:style|style=.legend_switch .nomobile.cbox-autonarrow "
    "{max-width: 35rem !important;} }}"
)
LEGEND_NEW = "{{#widget:style|style=.legend_switch .ak-cbox {max-width: 35rem;} }}"


def legend_switch(text: str) -> str:
    if LEGEND_NEW in text:
        return text
    if text.count(LEGEND_OLD) != 1:
        raise SystemExit("岁的界园志异/事件一览：找不到唯一的那条限宽样式，页面和预期的不一样，没有动")
    return text.replace(LEGEND_OLD, LEGEND_NEW)


# (标题, 改写, 摘要里的说明)
PAGES: list[tuple[str, Callable[[str], str], str]] = [
    ("MediaWiki:Common.css", cleanup(), "删掉 .nodesktop.cbox2-mobile 的 Vector 2022 窄屏例外"),
    (
        "MediaWiki:Gadget-Vector2022Fixes.css",
        cleanup(),
        "删掉 .nodesktop.cbox2-mobile 的窄屏例外",
    ),
    (
        "MediaWiki:Gadget-Vector2022LayoutFixes.css",
        cleanup(),
        "删掉 .nodesktop.cbox2-mobile 的窄屏例外",
    ),
    ("MediaWiki:Vector.css", cleanup(), "删掉 .cbox-autonarrow 自动收窄"),
    (
        "MediaWiki:Gadget-darkModeFix.css",
        cleanup(),
        "删掉编辑页系统消息里 .cbox2 的暗色规则（5 份重复，共 30 条），组件自带暗色",
    ),
    (
        "模板:孤星2024/styles.css",
        cleanup(stylesheet=True),
        "删掉专项调查说明框的暗色规则，改由 Cbox2/styles.css 的复刻参阅紫色框统一给",
    ),
    (
        "岁的界园志异/事件一览",
        legend_switch,
        "传说切换框的限宽选择器换成 .legend_switch .ak-cbox",
    ),
]


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
        for title, transform, what in PAGES:
            page = await wiki.read(title)
            if page.missing:
                print(f"  ! {title}: 目标站点没有这一页，跳过")
                continue
            old = page.content
            new = transform(old)
            if old.rstrip() == new.rstrip():
                print(f"  = {title}: 已是目标内容，跳过")
                continue
            diff = difflib.unified_diff(
                old.split("\n"),
                new.split("\n"),
                f"{title} (old)",
                f"{title} (new)",
                lineterm="",
                n=1,
            )
            print("\n".join(diff))
            if ns.dry_run:
                print(f"  [dry-run] {title}（r{page.revid}）")
                continue
            await wiki.edit(title, new, SUMMARY.format(what), baserevid=page.revid)
            print(f"  ✔ {title} 已写入")


if __name__ == "__main__":
    asyncio.run(main())
