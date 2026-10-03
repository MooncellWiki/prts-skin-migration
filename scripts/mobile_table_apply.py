"""移动端表格第一步：两个模板。见 migration/mobile-table/README.md。

- 模板:衍生作品导航：手机版那张表加 derivative-nav 类，新建 styles.css，<640 每行拆成「表头一条、内容一行」，
  源文件 migration/mobile-table/模板_衍生作品导航_styles.css；
- 模板:Code：min-width:600px → min(600px, 100% - 24px)，容器不到 624px 时不再撑破。

先写样式页再改模板：模板引用了不存在的样式页时，TemplateStyles 会在正文里输出报错。
幂等：已是目标状态就跳过。

    uv run python scripts/mobile_table_apply.py --dry-run               # 只打印 diff
    uv run python scripts/mobile_table_apply.py -c config.sandbox.toml  # 沙箱演练
    uv run python scripts/mobile_table_apply.py                         # 线上落地
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
CSS = ROOT / "migration" / "mobile-table" / "模板_衍生作品导航_styles.css"
NAV = "模板:衍生作品导航"
NAV_STYLES = "模板:衍生作品导航/styles.css"
CODE = "模板:Code"
SUMMARY = {
    NAV_STYLES: "衍生作品导航手机版：<640 每行拆成表头一条、内容一行，内容列不再被挤成 65px 的竖条。"
    "见 prts-skin-migration/migration/mobile-table/README.md",
    NAV: "衍生作品导航手机版加 derivative-nav 类并引入 styles.css：<640 内容列不再被挤成竖条。"
    "见 prts-skin-migration/migration/mobile-table/README.md",
    CODE: "代码框最小宽度 600px → min(600px, 100% - 24px)：手机上不再撑破页面，桌面不变。"
    "见 prts-skin-migration/migration/mobile-table/README.md",
}
# 代表页：音乐条目（展开）/ 衍生作品（默认折叠）/ 两个用 {{Code}} 的页面
PURGE = ["Runaway", "衍生作品", "模板:收藏品/common", "沉沦者的黑流树海/零件"]

TS_TAG = '<templatestyles src="衍生作品导航/styles.css" />'
NAV_EDITS = [
    (
        '{| class="wikitable nodesktop navigation-not-searchable ',
        '{| class="wikitable nodesktop derivative-nav navigation-not-searchable ',
    ),
    # 样式放进手机版第一格（标题），排在其余各行之前；模板第一行就是 {|，不能在它前面插东西
    (
        '! colspan="4" style="text-align:center;"|<big>',
        f'! colspan="4" style="text-align:center;"|{TS_TAG}<big>',
    ),
]
CODE_EDITS = [
    # 内边距 10px + 边框 2px 是 content-box 之外的 24px：减掉它，最窄时整个框正好贴满容器
    ("min-width:600px;", "min-width:min(600px, 100% - 24px);"),
]


def rewrite(title: str, text: str, edits: list[tuple[str, str]]) -> str:
    for old, new in edits:
        if new in text:
            continue
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"{title}: 期望出现 1 次，实际 {n} 次：{old}")
        text = text.replace(old, new)
    return text


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
        styles, nav, code = (
            await wiki.read(NAV_STYLES),
            await wiki.read(NAV),
            await wiki.read(CODE),
        )
        for page in (nav, code):
            if page.missing:
                raise SystemExit(f"{page.title} 不存在")

        css = CSS.read_text(encoding="utf-8").strip() + "\n"
        targets = (
            (styles, css, SUMMARY[NAV_STYLES]),
            (nav, rewrite(NAV, nav.content, NAV_EDITS), SUMMARY[NAV]),
            (code, rewrite(CODE, code.content, CODE_EDITS), SUMMARY[CODE]),
        )
        changed = False
        for page, new, summary in targets:
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
                summary,
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
