"""采购中心/可露希尔推荐：四张台词表手机上两格上下排。见 migration/mobile-table/README.md「第六步」。

- 新建 模板:采购中心/可露希尔推荐/styles.css（源文件 migration/mobile-table/模板_采购中心_可露希尔推荐_styles.css）：
  <640 把 .closure-lines 的每一行拆成上下两格，桌面不变；
- 采购中心/可露希尔推荐：页首引入它，四张表加 closure-lines 类。

先写样式页再改页面：页面引用了不存在的样式页时，TemplateStyles 会在正文里输出报错。
幂等：已是目标状态就跳过。

    uv run python scripts/closure_lines_stack_apply.py --dry-run               # 只打印 diff
    uv run python scripts/closure_lines_stack_apply.py -c config.sandbox.toml  # 沙箱演练
    uv run python scripts/closure_lines_stack_apply.py                         # 线上落地
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
CSS = ROOT / "migration" / "mobile-table" / "模板_采购中心_可露希尔推荐_styles.css"
PAGE = "采购中心/可露希尔推荐"
STYLES = "模板:采购中心/可露希尔推荐/styles.css"
SUMMARY = {
    STYLES: "可露希尔推荐的台词表：<640 两格上下排（商品名一条在上，台词占满下一行），"
    "台词列不再被挤成竖条。见 prts-skin-migration/migration/mobile-table/README.md",
    PAGE: "台词表引入 采购中心/可露希尔推荐/styles.css：手机上两格上下排，桌面不变。"
    "见 prts-skin-migration/migration/mobile-table/README.md",
}

TS_TAG = '<templatestyles src="采购中心/可露希尔推荐/styles.css" />'
# 页首的提示框，样式标签放在它前面
ANCHOR = "{{cbox2|mdi=true|icon=magnify|"
# 四张表的开头一模一样
TABLE_OLD = '{| class="wikitable" style="width:'
TABLE_NEW = '{| class="wikitable closure-lines" style="width:'
TABLES = 4


def rewrite(title: str, text: str) -> str:
    if TS_TAG not in text:
        if not text.startswith(ANCHOR):
            raise SystemExit(f"{title}: 页首不是 {ANCHOR}")
        text = TS_TAG + text
    done, todo = text.count(TABLE_NEW), text.count(TABLE_OLD)
    if done + todo != TABLES or text.count("{|") != TABLES:
        raise SystemExit(
            f"{title}: 期望 {TABLES} 张表，实际已加类 {done}、未加类 {todo}、"
            f"共 {text.count('{|')} 张"
        )
    return text.replace(TABLE_OLD, TABLE_NEW)


def show_diff(title: str, old: str, new: str) -> None:
    diff = difflib.unified_diff(
        old.split("\n"),
        new.split("\n"),
        f"{title} (old)",
        f"{title} (new)",
        lineterm="",
        n=0,
    )
    print("\n".join(line[:300] for line in diff))


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
        styles, page = await wiki.read(STYLES), await wiki.read(PAGE)
        if page.missing:
            raise SystemExit(f"{PAGE} 不存在")

        css = CSS.read_text(encoding="utf-8").strip() + "\n"
        targets = (
            (styles, css, SUMMARY[STYLES]),
            (page, rewrite(PAGE, page.content), SUMMARY[PAGE]),
        )
        changed = False
        for target, new, summary in targets:
            if not target.missing and target.content.strip() == new.strip():
                print(f"  = {target.title}: 已是目标状态，跳过")
                continue
            show_diff(target.title, "" if target.missing else target.content, new)
            changed = True
            if ns.dry_run:
                print(f"  [dry-run] {target.title}（r{target.revid}）")
                continue
            await wiki.edit(
                target.title,
                new,
                summary,
                baserevid=None if target.missing else target.revid,
                nocreate=not target.missing,
            )
            print(f"  ✔ {target.title} 已写入")

        if changed and not ns.dry_run:
            await wiki.purge([PAGE])
            print(f"  purge：{PAGE}")


if __name__ == "__main__":
    asyncio.run(main())
