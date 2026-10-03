"""模板:Cbox2 整体换成设计系统的正文提示框（.ak-cbox）：
把 migration/cbox2/ 下的源文件写进 模板:Cbox2/styles.css、模板:Cbox2/core、模板:Cbox2、
模板:Cbox2/doc、模板:复刻参阅，再把 孤星2024 里直接调 /core 的那处改成复刻参阅的写法。

源文件整页覆盖（源文件是唯一来源）；styles.css 的自动偏好（os）分支由 night 规则机械生成，
与 theme_apply.py 的 os_branch 一步结果相同。先写样式表和 /core 再写入口模板：
旧版 模板:Cbox2 传给新 /core 的参数（content、按等级展开好的颜色）也能正常渲染。
见 migration/cbox2/README.md。

    uv run python scripts/cbox2_apply.py --dry-run               # 只打印 diff
    uv run python scripts/cbox2_apply.py -c config.sandbox.toml  # 沙箱演练
    uv run python scripts/cbox2_apply.py                         # 线上落地
    uv run python scripts/cbox2_apply.py --summary "…"           # 追加改动，换编辑摘要
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wikibot.config import get_settings, load_config
from wikibot.theme_os import add_os_branch
from wikibot.wiki import Wiki

SRC_DIR = Path(__file__).resolve().parents[1] / "migration" / "cbox2"
DOC = "prts-skin-migration/migration/cbox2/README.md"


def source(name: str) -> Callable[[str], str]:
    text = (SRC_DIR / name).read_text(encoding="utf-8").rstrip("\n")
    return lambda _: text


def stylesheet(name: str) -> Callable[[str], str]:
    css, _ = add_os_branch((SRC_DIR / name).read_text(encoding="utf-8"))
    return lambda _: css.rstrip("\n")


# 孤星2024 的专项调查说明和 复刻参阅 是同一个紫色渐变框，改用同一个 boxclass
LONETRAIL_OLD = (
    "{{cbox2/core|lv=0|bgleft=#7051DB|iconcolor=white"
    "|bg=linear-gradient(90deg,#defcff,#e2dbff)|mdi=true|icon=clipboard-edit"
    "|boxclass=lonetrail-2024-rerun-survey-note|"
)
LONETRAIL_NEW = (
    "{{cbox2/core|lv=0|mdi=true|icon=clipboard-edit"
    "|boxclass=rerun-reference-box lonetrail-2024-rerun-survey-note|"
)


def lonetrail(text: str) -> str:
    if LONETRAIL_NEW in text:
        return text
    if text.count(LONETRAIL_OLD) != 1:
        raise SystemExit("孤星2024：找不到唯一的那处 {{cbox2/core|…}}，页面和预期的不一样，没有动")
    return text.replace(LONETRAIL_OLD, LONETRAIL_NEW)


# (标题, 改写, 编辑摘要)
PAGES: list[tuple[str, Callable[[str], str], str]] = [
    (
        "模板:Cbox2/styles.css",
        stylesheet("模板_Cbox2_styles.css"),
        "Cbox2 改用设计系统 .ak-cbox：等级配色与明暗主题交给组件，"
        f"这里只留复刻参阅的紫色框和暗色下正文里的深色字。见 {DOC}",
    ),
    (
        "模板:Cbox2/core",
        source("模板_Cbox2_core.wiki"),
        "改为输出设计系统正文提示框 .ak-cbox（Skin:Arknights 原生样式、跟随明暗主题；"
        "其他皮肤由 微件:AkComponents 加载样式）；去掉 nomobile / nodesktop 双份渲染；"
        f"自定义配色的框按浅色方案显示。参数不变。见 {DOC}",
    ),
    (
        "模板:Cbox2",
        source("模板_Cbox2.wiki"),
        f"参数原样交给 /core，等级配色与默认图标由 /core 决定。见 {DOC}",
    ),
    (
        "模板:Cbox2/doc",
        source("模板_Cbox2_doc.wiki"),
        f"文档跟随新外观：等级、窄版、默认图标、自定义配色的行为。见 {DOC}",
    ),
    (
        "模板:复刻参阅",
        source("模板_复刻参阅.wiki"),
        f"紫色渐变改由 模板:Cbox2/styles.css 给（暗色下有深色版），不再写行内配色。见 {DOC}",
    ),
    (
        "孤星2024",
        lonetrail,
        f"专项调查说明框改用复刻参阅的紫色框（boxclass=rerun-reference-box），暗色下有深色版。见 {DOC}",
    ),
]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "-c", "--config", type=Path, help="换配置文件，如 config.sandbox.toml"
    )
    ap.add_argument("--summary", help="覆盖各页的编辑摘要（上线后的追加改动用）")
    ns = ap.parse_args()

    cfg = load_config(ns.config)
    print(f"目标站点：{cfg.api_url}")
    async with Wiki(
        cfg.api_url, cfg.user_agent, cfg.client, dry_run=ns.dry_run
    ) as wiki:
        await wiki.login(*get_settings().require_credentials())
        for title, transform, summary in PAGES:
            page = await wiki.read(title)
            if page.missing:
                raise SystemExit(f"{title} 不存在")
            old = page.content
            new = transform(old)
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
                print(f"  [dry-run] {title}（r{page.revid}）")
                continue
            await wiki.edit(title, new, ns.summary or summary, baserevid=page.revid)
            print(f"  ✔ {title} 已写入")


if __name__ == "__main__":
    asyncio.run(main())
