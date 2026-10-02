"""干员获得方式表格手机上不再缩成一条：宽度从行内 width:40% 挪进
模板:干员获得方式/styles.css（<640 拉满、其余宽度保底 320px），
源文件 migration/char-obtain/模板_干员获得方式_styles.css。
见 migration/char-obtain/README.md。

先写样式页再改模板：模板引用了不存在的样式页时，TemplateStyles 会在正文里输出报错。
幂等：两页都已是目标状态就跳过。

    uv run python scripts/char_obtain_apply.py --dry-run               # 只打印 diff
    uv run python scripts/char_obtain_apply.py -c config.sandbox.toml  # 沙箱演练
    uv run python scripts/char_obtain_apply.py                         # 线上落地
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
CSS = ROOT / "migration" / "char-obtain" / "模板_干员获得方式_styles.css"
TEMPLATE = "模板:干员获得方式"
STYLES = "模板:干员获得方式/styles.css"
SUMMARY = (
    "获得方式表格手机上不再缩成 40% 的窄条：宽度挪进 styles.css，"
    "<640 拉满、其余保底 320px。见 prts-skin-migration/migration/char-obtain/README.md"
)
# 代表页：普通 / 限定（多一行解限时间）/ 联动（带合作方式图标）
PURGE = ["阿米娅", "重岳", "埃癸斯"]

TS_TAG = '<templatestyles src="干员获得方式/styles.css" />'
EDITS = [
    ("<includeonly>{{参阅|", f"<includeonly>{TS_TAG}{{{{参阅|"),
    (
        '{|class="wikitable prts-table-dark" style="width:40%; display:table;',
        '{|class="wikitable prts-table-dark char-obtain" style="display:table;',
    ),
]


def rewrite_template(text: str) -> str:
    for old, new in EDITS:
        if new in text:
            continue
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"{TEMPLATE}: 期望出现 1 次，实际 {n} 次：{old}")
        text = text.replace(old, new)
    return text


def show_diff(title: str, old: str, new: str) -> None:
    diff = difflib.unified_diff(
        old.split("\n"),
        new.split("\n"),
        f"{title} (old)",
        f"{title} (new)",
        lineterm="",
        n=1,
    )
    print("\n".join(diff))


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
        styles, template = await wiki.read(STYLES), await wiki.read(TEMPLATE)
        if template.missing:
            raise SystemExit(f"{TEMPLATE} 不存在")

        css = CSS.read_text(encoding="utf-8").strip() + "\n"
        new_tpl = rewrite_template(template.content)
        changed = False
        for page, new in ((styles, css), (template, new_tpl)):
            if not page.missing and page.content.strip() == new.strip():
                print(f"  = {page.title}: 已是目标状态，跳过")
                continue
            show_diff(page.title, "" if page.missing else page.content, new)
            changed = True
            if ns.dry_run:
                print(f"  [dry-run] {page.title}（r{page.revid}）")
                continue
            await wiki.edit(
                page.title,
                new,
                SUMMARY,
                baserevid=None if page.missing else page.revid,
                nocreate=not page.missing,
            )
            print(f"  ✔ {page.title} 已写入")

        if changed and not ns.dry_run:
            # 其余嵌入页靠任务队列重新解析
            await wiki.purge(PURGE)
            print(f"  purge：{'、'.join(PURGE)}")


if __name__ == "__main__":
    asyncio.run(main())
