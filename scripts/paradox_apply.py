"""悖论模拟改用设计系统的档案类卡片（.ak-archive）：
把 migration/paradox/ 下的三个源文件写进
微件:AkComponents、模板:悖论模拟/styles.css（不存在时新建）和 模板:悖论模拟。

整页覆盖（源文件是唯一来源）。先写微件和样式表再写模板，模板用到的页面总是先就位。
描述里的黑字走 模板:Color 的语义变量，由 theme_apply.py 的 dark_mode_fix 一步改。
见 migration/paradox/README.md。

    uv run python scripts/paradox_apply.py --dry-run               # 只打印 diff
    uv run python scripts/paradox_apply.py -c config.sandbox.toml  # 沙箱演练
    uv run python scripts/paradox_apply.py                         # 线上落地
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

SRC_DIR = Path(__file__).resolve().parents[1] / "migration" / "paradox"
DOC = "prts-skin-migration/migration/paradox/README.md"
# (标题, 源文件, 允许新建, 编辑摘要)
PAGES = [
    (
        "微件:AkComponents",
        "微件_AkComponents.wiki",
        True,
        "模板直接输出设计系统组件时用："
        "非 Arknights 皮肤上用 JS 加载皮肤的组件样式与字体，"
        f"做法同新首页。见 {DOC}",
    ),
    (
        "模板:悖论模拟/styles.css",
        "模板_悖论模拟_styles.css",
        True,
        "悖论模拟卡片里模板特有的样式：关卡卡片整块可点。"
        "链接从 display: contents 改成真盒子，修复拖不出链接；"
        "术语加粗改由模板输出 <b>。"
        f"见 {DOC}",
    ),
    (
        "模板:悖论模拟",
        "模板_悖论模拟.wiki",
        False,
        "照设计稿改用档案类卡片 .ak-archive + 关卡卡片 .ak-stage + 道具 .ak-item"
        "（Skin:Arknights 原生样式、跟随明暗主题；"
        "其他皮肤由 微件:AkComponents 加载样式），"
        "描述里 {{color|#000000|…}} 的术语输出为 <b>（同设计稿）；"
        f"去掉 nomobile / nodesktop 双份渲染与首页死类名；参数不变。见 {DOC}",
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
        for title, src, create, summary in PAGES:
            page = await wiki.read(title)
            if page.missing and not create:
                raise SystemExit(f"{title} 不存在")
            new = (SRC_DIR / src).read_text(encoding="utf-8").rstrip("\n")
            old = "" if page.missing else page.content
            if old == new:
                print(f"  = {title}: 已是目标内容，跳过")
                continue
            diff = difflib.unified_diff(
                old.split("\n"),
                new.split("\n"),
                f"{title} (old)",
                f"{title} (new)",
                lineterm="",
                n=2,
            )
            print("\n".join(diff))
            if ns.dry_run:
                base = "新建" if page.missing else f"r{page.revid}"
                print(f"  [dry-run] {title}（{base}）")
                continue
            await wiki.edit(
                title,
                new,
                summary,
                baserevid=None if page.missing else page.revid,
                nocreate=not page.missing,
            )
            print(f"  ✔ {title} 已写入")


if __name__ == "__main__":
    asyncio.run(main())
