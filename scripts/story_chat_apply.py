"""黍的试验田/剧情：对话表手机上改聊天版式。见 migration/mobile-table/README.md「第七步」。

- 新建 模板:黍的试验田/剧情/styles.css（源文件 migration/mobile-table/模板_黍的试验田_剧情_styles.css）：
  表宽 800px → min(800px, 100%)，暗色主题下链接色固定用浅色主题的；<640 把每行排成聊天气泡，桌面版式不变；
- 黍的试验田/剧情：在页内已有的 {{#widget:style}} 前引入它。

先写样式页再改页面：页面引用了不存在的样式页时，TemplateStyles 会在正文里输出报错。
幂等：已是目标状态就跳过。

    uv run python scripts/story_chat_apply.py --dry-run               # 只打印 diff
    uv run python scripts/story_chat_apply.py -c config.sandbox.toml  # 沙箱演练
    uv run python scripts/story_chat_apply.py                         # 线上落地
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
CSS = ROOT / "migration" / "mobile-table" / "模板_黍的试验田_剧情_styles.css"
PAGE = "黍的试验田/剧情"
STYLES = "模板:黍的试验田/剧情/styles.css"
SUMMARY = {
    STYLES: "黍的试验田/剧情 的对话表：表宽不再写死 800px；<640 改聊天版式（头像靠说话人一侧，台词成气泡），"
    "不用横滑。见 prts-skin-migration/migration/mobile-table/README.md",
    PAGE: "对话表引入 黍的试验田/剧情/styles.css：手机上改聊天版式，桌面版式不变。"
    "见 prts-skin-migration/migration/mobile-table/README.md",
}

TS_TAG = '<templatestyles src="黍的试验田/剧情/styles.css" />'
# 页内给 table.story 写底色、边框的那个 widget，样式标签放在它前面
ANCHOR = "{{#widget:style|style=table.story {"
PAGE_EDITS = [(ANCHOR, TS_TAG + ANCHOR)]


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
        styles, page = await wiki.read(STYLES), await wiki.read(PAGE)
        if page.missing:
            raise SystemExit(f"{PAGE} 不存在")

        css = CSS.read_text(encoding="utf-8").strip() + "\n"
        targets = (
            (styles, css, SUMMARY[STYLES]),
            (page, rewrite(PAGE, page.content, PAGE_EDITS), SUMMARY[PAGE]),
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
