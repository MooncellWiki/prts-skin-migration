"""行悬停审计：皮肤的 .wikitable 行悬停底色盖掉模板 / 页内给单元格上的底色。

皮肤有 ``.wikitable > tbody > tr:hover > td { background: var(--ak-bg-hover) }``
（特异性 0,2,3）。模板、页内样式给单元格上底色的选择器特异性比它低、又没写
!important 时，悬停那一行的单元格底色被整个换成半透明的悬停色，文字色照旧，
深底白字就成了浅底白字。单元格上的行内 style 不受影响（行内优先级最高）；
写在 ``|-`` 行上的底色只是被悬停色压暗一点，不算问题。

    uv run python scripts/hover_audit.py select           # 线上 + 沙箱库 → 待渲染页面
    uv run --with playwright python scripts/hover_audit.py run
    uv run python scripts/hover_audit.py report

页面在线上渲染（``?useskin=arknights``），每页量浅色 / 暗色两种外观，
结果在 reports/hover-audit/。
悬停态的模拟见 scripts/hover_audit.js。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "hover-audit"
AUDIT_JS = Path(__file__).with_name("hover_audit.js")
LIVE = "https://prts.wiki"
MODES = ("day", "night")

_SWITCH = """
(mode) => {
  const html = document.documentElement;
  for (const c of [...html.classList]) {
    if (c.startsWith('skin-theme-clientpref-')) html.classList.remove(c);
  }
  html.classList.add('skin-theme-clientpref-' + mode);
  if (!document.getElementById('theme-audit-freeze')) {
    const style = document.createElement('style');
    style.id = 'theme-audit-freeze';
    style.textContent = '*,*::before,*::after{transition:none!important;animation:none!important}';
    document.head.appendChild(style);
  }
}
"""


# --------------------------------------------------------------------------- select


def select(args: argparse.Namespace) -> None:
    """待渲染页面 = 主题审计的覆盖样本 ∪ 页面清单文件（--pages-file，一行一个）。"""
    pages: list[str] = []
    plan = ROOT / "reports" / "theme-audit" / "pages.json"
    if plan.exists():
        pages += [item["page"] for item in json.loads(plan.read_text("utf-8"))["pages"]]
    for path in args.pages_file or []:
        pages += [
            line.strip()
            for line in Path(path).read_text("utf-8").splitlines()
            if line.strip()
        ]
    pages = list(dict.fromkeys(pages))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pages.json").write_text(
        json.dumps(pages, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"待渲染 {len(pages)} 页")


# --------------------------------------------------------------------------- run

_EXPAND = """
() => {
  for (const el of document.querySelectorAll('.AKCollapse, .AKCollapse-content')) {
    el.style.display = 'block';
  }
}
"""


async def run(args: argparse.Namespace) -> None:
    from playwright.async_api import async_playwright

    pages = args.pages or json.loads((OUT / "pages.json").read_text("utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    result_path = OUT / args.results
    if args.fresh and result_path.exists():
        result_path.unlink()
    done: set[str] = set()
    if result_path.exists():
        for line in result_path.read_text("utf-8").splitlines():
            done.add(json.loads(line)["page"])
    todo = [p for p in pages if p not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"待渲染 {len(todo)} 页（已完成 {len(done)}）")

    audit_src = AUDIT_JS.read_text("utf-8")
    audit = f"(threshold) => {{{audit_src}\nreturn hoverAudit({{threshold}});}}"
    queue: asyncio.Queue[str] = asyncio.Queue()
    for title in todo:
        queue.put_nowait(title)
    lock = asyncio.Lock()
    finished = 0

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel="chrome", headless=True)

        async def worker() -> None:
            nonlocal finished
            context = await browser.new_context(viewport={"width": 1400, "height": 900})
            page = await context.new_page()
            while not queue.empty():
                title = queue.get_nowait()
                record: dict[str, Any] = {"page": title, "modes": {}}
                try:
                    bust = f"&_={int(time.time())}" if args.bust else ""
                    url = f"{args.base}/w/{quote(title.replace(' ', '_'))}"
                    await page.goto(
                        f"{url}?useskin=arknights{bust}",
                        wait_until="load",
                        timeout=args.timeout * 1000,
                    )
                    await page.wait_for_timeout(800)
                    if args.css:
                        await page.add_style_tag(path=args.css)
                    await page.evaluate(_EXPAND)
                    for mode in MODES:
                        await page.emulate_media(
                            color_scheme="light" if mode == "day" else "dark"
                        )
                        await page.evaluate(_SWITCH, mode)
                        await page.wait_for_timeout(150)
                        record["modes"][mode] = await page.evaluate(
                            audit, args.threshold
                        )
                except Exception as exc:
                    record["error"] = f"{type(exc).__name__}: {exc}"[:300]
                async with lock:
                    with result_path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                    finished += 1
                    if finished % 20 == 0 or "error" in record:
                        state = record.get("error", "ok")
                        print(
                            f"  [{finished}/{len(todo)}] {title}: {state}", flush=True
                        )
            await context.close()

        await asyncio.gather(*(worker() for _ in range(args.workers)))
        await browser.close()
    print("完成")


# --------------------------------------------------------------------------- report


def _source(issue: dict[str, Any]) -> str:
    """底色出处：样式块（TemplateStyles 修订号、WidgetStyle、站点样式）+ 选择器。"""
    rules = [r for r in issue["rules"] if not r["important"]]
    return " ; ".join(f"{r['src']} {r['sel']}" for r in rules[-3:]) or "?"


def report(args: argparse.Namespace) -> None:
    rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    errors: list[str] = []
    rendered = 0
    for line in (OUT / args.results).read_text("utf-8").splitlines():
        record = json.loads(line)
        if "error" in record:
            errors.append(f"{record['page']}: {record['error']}")
            continue
        rendered += 1
        for mode, result in record["modes"].items():
            for issue in result["issues"]:
                key = (issue["kind"], issue["cell"], _source(issue))
                slot = rows.setdefault(
                    key,
                    {
                        **issue,
                        "modes": set(),
                        "pages": set(),
                        "cells": 0,
                    },
                )
                slot["modes"].add(mode)
                slot["pages"].add(record["page"])
                slot["cells"] += issue["count"]

    order = {"unreadable": 0, "image": 1, "recolor": 2}
    lines = [
        "# 行悬停审计（Arknights 皮肤）",
        "",
        f"线上渲染 {rendered} 页，模拟 `.wikitable` 行悬停，"
        "比对单元格悬停前后的底色与文字对比度。",
        "",
        f"- **unreadable**：悬停后文字对比度低于 {args.threshold}:1（悬停前够）",
        "- **image**：单元格的渐变 / 图片底被换成纯色",
        "- **recolor**：作者写的底色被换掉，文字仍读得清",
        "",
        "| 类 | 单元格 | 悬停前 → 后 | 对比度 | 外观 | 格数 | 页数 | 出处 | 样例页 | 样例文字 |",
        "| --- | --- | --- | --- | --- | ---: | ---: | --- | --- | --- |",
    ]
    for key, item in sorted(
        rows.items(), key=lambda kv: (order[kv[0][0]], -len(kv[1]["pages"]))
    ):
        sample = item["sample"].replace("|", "¦")
        src = key[2].replace("|", "¦")
        lines.append(
            f"| {key[0]} | `{key[1]}` | `{item['effBefore']}` → `{item['effAfter']}` "
            f"| {item['ratioBefore']} → {item['ratioAfter']} | {'/'.join(sorted(item['modes']))} "
            f"| {item['cells']} | {len(item['pages'])} | {src} "
            f"| {sorted(item['pages'])[0]} | {sample} |"
        )
    if errors:
        lines += ["", "## 渲染失败", ""] + [f"- {e}" for e in errors]
    path = OUT / args.output
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(rows)} 条，失败 {len(errors)} 页。报告：{path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_select = sub.add_parser("select")
    p_select.add_argument("--pages-file", action="append")

    p_run = sub.add_parser("run")
    p_run.add_argument("--base", default=LIVE)
    p_run.add_argument("--workers", type=int, default=4)
    p_run.add_argument("--timeout", type=int, default=120)
    p_run.add_argument("--threshold", type=float, default=3.0)
    p_run.add_argument("--limit", type=int, default=0)
    p_run.add_argument("--fresh", action="store_true")
    p_run.add_argument("--results", default="results.jsonl")
    p_run.add_argument("--bust", action="store_true", help="URL 加随机参数绕过 CDN")
    p_run.add_argument("--css", help="渲染后追加这份样式表再量（预演站点级修复）")
    p_run.add_argument("pages", nargs="*")

    p_report = sub.add_parser("report")
    p_report.add_argument("--threshold", type=float, default=3.0)
    p_report.add_argument("--results", default="results.jsonl")
    p_report.add_argument("--output", default="hover-audit.md")

    args = parser.parse_args()
    if args.cmd == "run":
        asyncio.run(run(args))
    else:
        {"select": select, "report": report}[args.cmd](args)


if __name__ == "__main__":
    main()
