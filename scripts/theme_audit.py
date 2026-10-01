"""主题适配审计：在沙箱站点上实际渲染页面，找出三种外观下文字看不清的模板。

静态扫描只能发现「写了 night 没写 os」这类选择器问题；行内写死颜色、依赖 Vector 变量的
模板得真渲染出来量对比度才查得到。分三步，中间结果都落在 reports/theme-audit/：

    uv run python scripts/theme_audit.py select     # 沙箱库 → 选一批能覆盖所有模板的页面
    uv run --with playwright python scripts/theme_audit.py run   # 逐页渲染 + 量对比度
    uv run python scripts/theme_audit.py report     # 归因到模板，出 markdown 报告

每个页面只加载一次，然后在页面里切 html 上的 skin-theme-clientpref-* 类和系统配色，
依次量三种外观：day（浅色）、night（暗色）、os-dark（自动 + 系统暗色）。
折叠 / 标签页里没显示出来的内容量不到。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wikibot.config import load_config

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "theme-audit"
AUDIT_JS = Path(__file__).with_name("contrast_audit.js")
SANDBOX_CONFIG = ROOT / "config.sandbox.toml"

TEMPLATE_NS = (10, 274, 828)
SKIP_TITLE = re.compile(
    r"(/doc$|/testcases$|sandbox|Sandbox|沙盒|/styles?\.css$|\.css$)"
)
MODES = ("day", "night", "os-dark")
BASELINE = "vector-day"  # Vector 浅色：白天模式的参照，那里就有的低对比度算设计如此


# --------------------------------------------------------------------------- select


async def _query(cfg: Any, sql: str, args: tuple = ()) -> list[tuple]:
    import aiomysql

    sb = cfg.sandbox
    conn = await aiomysql.connect(
        host=sb.host,
        port=sb.port,
        user=sb.user,
        password=sb.password,
        db=sb.database,
        charset="utf8mb4",
    )
    try:
        async with conn.cursor() as cur:
            await cur.execute(sql.format(p=sb.table_prefix), args)
            return list(await cur.fetchall())
    finally:
        conn.close()


def _text(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes | bytearray) else str(value)


async def select(args: argparse.Namespace) -> None:
    cfg = load_config(SANDBOX_CONFIG)
    rows = await _query(
        cfg,
        """
        SELECT src.page_title, lt.lt_namespace, lt.lt_title
        FROM {p}templatelinks tl
        JOIN {p}linktarget lt ON lt.lt_id = tl.tl_target_id
        JOIN {p}page src ON src.page_id = tl.tl_from
        JOIN {p}page dst ON dst.page_namespace = lt.lt_namespace
                        AND dst.page_title = lt.lt_title
        WHERE src.page_namespace = 0 AND src.page_is_redirect = 0
          AND lt.lt_namespace IN (10, 274, 828)
        """,
    )
    uses: dict[str, set[str]] = defaultdict(set)  # 页面 → 用到的模板
    usage: Counter[str] = Counter()  # 模板 → 被多少页面用
    for page, ns, title in rows:
        full = cfg.full_title(int(ns), _text(title).replace("_", " "))
        if SKIP_TITLE.search(full):
            continue
        uses[_text(page).replace("_", " ")].add(full)
        usage[full] += 1

    # 贪心集合覆盖：每次挑能新覆盖最多模板的页面
    remaining = set(usage)
    chosen: list[dict[str, Any]] = []
    candidates = dict(uses)
    while remaining and candidates:
        page, gain = max(
            ((p, len(t & remaining)) for p, t in candidates.items()),
            key=lambda item: (item[1], -len(item[0])),
        )
        if gain == 0:
            break
        chosen.append({"page": page, "new": sorted(candidates[page] & remaining)})
        remaining -= candidates.pop(page)
        if args.limit and len(chosen) >= args.limit:
            break

    # 再给用量最大的模板各补两个页面，避免单个样本碰巧没触发问题分支
    picked = {item["page"] for item in chosen}
    by_template: dict[str, list[str]] = defaultdict(list)
    for page, templates in uses.items():
        for template in templates:
            if len(by_template[template]) < 40:
                by_template[template].append(page)
    extra = 0
    for template, _ in usage.most_common(args.top):
        for page in sorted(by_template[template], key=len)[:2]:
            if page not in picked:
                picked.add(page)
                chosen.append({"page": page, "new": []})
                extra += 1

    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "pages": chosen,
        "uses": {item["page"]: sorted(uses[item["page"]]) for item in chosen},
        "usage": dict(usage),
        "uncovered": sorted(remaining),
    }
    (OUT / "pages.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(
        f"模板/微件/模块 {len(usage)} 个（主名字空间有引用），"
        f"选中 {len(chosen)} 个页面（覆盖 {len(chosen) - extra} + 补样 {extra}），"
        f"未覆盖 {len(remaining)}"
    )


# --------------------------------------------------------------------------- run

_SWITCH = """
(mode) => {
  const html = document.documentElement;
  for (const c of [...html.classList]) {
    if (c.startsWith('skin-theme-clientpref-')) html.classList.remove(c);
  }
  html.classList.add('skin-theme-clientpref-' + (mode === 'os-dark' ? 'os' : mode));
  // 皮肤给链接等加了颜色过渡，不关掉的话刚切完外观读到的还是上一个外观的颜色
  if (!document.getElementById('theme-audit-freeze')) {
    const style = document.createElement('style');
    style.id = 'theme-audit-freeze';
    style.textContent = '*,*::before,*::after{transition:none!important;animation:none!important}';
    document.head.appendChild(style);
  }
}
"""

# --expand：展开 AKCollapse（微件脚本 hide()，直接改 display）和 mw-collapsible，
# 折叠里的内容默认量不到，集成战略这类长页大半内容都在折叠里
_EXPAND = """
() => {
  for (const el of document.querySelectorAll('.AKCollapse, .AKCollapse-content')) {
    el.style.display = 'block';
  }
  if (window.jQuery) {
    jQuery('.mw-collapsible.mw-collapsed').each(function () {
      const api = jQuery(this).data('mw-collapsible');
      if (api) api.expand();
    });
  }
}
"""


# --preview：正文换成 parse API 渲染的改后版本（theme_apply --dump 的产物），
# 不用先写进站点。换完重新触发 wikipage.content，折叠表格 / 标签页照常初始化；
# 微件里的 <script> 不会执行
_INJECT = """
(html) => {
  const target = document.querySelector('.mw-parser-output');
  const holder = document.createElement('div');
  holder.innerHTML = html;
  target.innerHTML = (holder.querySelector('.mw-parser-output') || holder).innerHTML;
  if (window.mw && window.jQuery) mw.hook('wikipage.content').fire(jQuery(target));
}
"""


async def _preview_html(base: str, title: str, text: str) -> str:
    import httpx

    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            f"{base}/api.php",
            data={
                "action": "parse",
                "title": title,
                "text": text,
                "contentmodel": "wikitext",
                "prop": "text",
                "disablelimitreport": 1,
                "formatversion": 2,
                "format": "json",
            },
            headers={"User-Agent": "prts-skin-migration theme_audit"},
        )
        resp.raise_for_status()
        return resp.json()["parse"]["text"]


async def run(args: argparse.Namespace) -> None:
    from playwright.async_api import async_playwright

    plan = json.loads((OUT / "pages.json").read_text(encoding="utf-8"))
    pages = [item["page"] for item in plan["pages"]]
    if args.pages:
        pages = args.pages
    result_path = OUT / args.results
    if args.fresh and result_path.exists():
        result_path.unlink()
    done: set[str] = set()
    if result_path.exists():
        for line in result_path.read_text(encoding="utf-8").splitlines():
            done.add(json.loads(line)["page"])
    todo = [p for p in pages if p not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"待渲染 {len(todo)} 页（已完成 {len(done)}）")

    audit_src = AUDIT_JS.read_text(encoding="utf-8")
    queue: asyncio.Queue[str] = asyncio.Queue()
    for title in todo:
        queue.put_nowait(title)
    lock = asyncio.Lock()
    finished = 0

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel="chrome", headless=True)

        async def worker() -> None:
            nonlocal finished
            context = await browser.new_context(
                viewport={"width": 1400, "height": 900}, color_scheme="dark"
            )
            page = await context.new_page()
            while not queue.empty():
                title = queue.get_nowait()
                record: dict[str, Any] = {"page": title, "modes": {}}
                try:
                    preview = None
                    if args.preview:
                        dumped = Path(args.preview) / (
                            title.replace("/", "__") + ".wiki"
                        )
                        if dumped.exists():
                            text = dumped.read_text(encoding="utf-8")
                            preview = await _preview_html(args.base, title, text)
                            record["preview"] = True
                    url = f"{args.base}/w/{quote(title.replace(' ', '_'))}"
                    audit = "(threshold) => {%s\nreturn contrastAudit({threshold});}"
                    audit %= audit_src
                    for skin, modes in (
                        ("arknights", MODES),
                        ("vector-2022", ("day",)),
                    ):
                        bust = f"&_={int(time.time())}" if args.bust else ""
                        await page.goto(
                            f"{url}?useskin={skin}{bust}",
                            wait_until="load",
                            timeout=args.timeout * 1000,
                        )
                        await page.wait_for_timeout(800)  # 微件 / 懒加载脚本收尾
                        if preview is not None:
                            await page.evaluate(_INJECT, preview)
                            await page.wait_for_timeout(1500)
                        if args.css:  # 站点级样式（Common.css 等）的改动
                            await page.add_style_tag(path=args.css)
                        if args.expand:
                            await page.evaluate(_EXPAND)
                            await page.wait_for_timeout(500)
                        for mode in modes:
                            scheme = "light" if mode == "day" else "dark"
                            await page.emulate_media(color_scheme=scheme)
                            await page.evaluate(_SWITCH, mode)
                            await page.wait_for_timeout(150)
                            key = mode if skin == "arknights" else BASELINE
                            record["modes"][key] = await page.evaluate(
                                audit, args.threshold
                            )
                except Exception as exc:
                    record["error"] = f"{type(exc).__name__}: {exc}"[:300]
                async with lock:
                    with result_path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                    finished += 1
                    if finished % 10 == 0 or "error" in record:
                        state = record.get("error", "ok")
                        print(
                            f"  [{finished}/{len(todo)}] {title}: {state}", flush=True
                        )
            await context.close()

        await asyncio.gather(*(worker() for _ in range(args.workers)))
        await browser.close()
    print("完成")


# --------------------------------------------------------------------------- report


async def _sources(cfg: Any) -> dict[str, str]:
    rows = await _query(
        cfg,
        """
        SELECT pg.page_namespace, pg.page_title, tx.old_text
        FROM {p}page pg
        JOIN {p}slots sl ON sl.slot_revision_id = pg.page_latest AND sl.slot_role_id = 1
        JOIN {p}content ct ON ct.content_id = sl.slot_content_id
        JOIN {p}text tx ON tx.old_id = CAST(SUBSTRING(ct.content_address, 4) AS UNSIGNED)
        WHERE pg.page_namespace IN (8, 10, 274, 828) AND pg.page_is_redirect = 0
        """,
    )
    return {
        cfg.full_title(int(ns), _text(title).replace("_", " ")): _text(text)
        for ns, title, text in rows
    }


_GENERIC_CLASS = re.compile(
    r"^(wikitable|mw-|nomobile|nodesktop|logo|sortable|jquery-|plainlinks|hlist|"
    r"mc-tooltips|mdi|external|text|new|image|thumb|center|left|right|floatright|"
    r"floatleft|noresize|smw|poem)"
)


def _signature(issue: dict[str, Any]) -> tuple[str, str, str, str]:
    return (issue["anchor"], issue["element"], issue["fg"], issue["bg"])


def _attribute(
    issue: dict[str, Any], templates: list[str], src: dict[str, str]
) -> list[str]:
    """把一条问题归到模板上：看页面用到的模板里谁的源码出现了问题元素的类名或底色。"""
    classes = [
        c
        for part in (issue["anchor"], issue["element"])
        for c in part.split(".")[1:]
        if not _GENERIC_CLASS.match(c)
    ]
    needles = [re.compile(r"(?<![\w-])" + re.escape(c) + r"(?![\w-])") for c in classes]
    hits: list[str] = []
    for template in templates:
        bodies = [src.get(template, "")]
        bodies += [
            text
            for title, text in src.items()
            if title.startswith(template + "/") and title.endswith(".css")
        ]
        body = "\n".join(bodies)
        if any(n.search(body) for n in needles):
            hits.append(template)
    if hits or classes:
        return hits
    # 没有可用类名：退而看行内底色字面量
    literals = set(re.findall(r"#[0-9a-fA-F]{3,8}\b", issue.get("bgStyle", "")))
    if issue["bgFrom"] == "inline":
        literals.add(issue["bg"])
    for template in templates:
        body = src.get(template, "").lower()
        if any(lit.lower() in body for lit in literals):
            hits.append(template)
    return hits


async def report(args: argparse.Namespace) -> None:
    cfg = load_config(SANDBOX_CONFIG)
    plan = json.loads((OUT / "pages.json").read_text(encoding="utf-8"))
    usage: dict[str, int] = plan["usage"]
    src = await _sources(cfg)
    uses_rows = await _query(
        cfg,
        """
        SELECT src.page_title, lt.lt_namespace, lt.lt_title
        FROM {p}templatelinks tl
        JOIN {p}linktarget lt ON lt.lt_id = tl.tl_target_id
        JOIN {p}page src ON src.page_id = tl.tl_from
        WHERE src.page_namespace = 0 AND lt.lt_namespace IN (10, 274, 828)
        """,
    )
    uses: dict[str, list[str]] = defaultdict(list)
    for page, ns, title in uses_rows:
        full = cfg.full_title(int(ns), _text(title).replace("_", " "))
        if not SKIP_TITLE.search(full):
            uses[_text(page).replace("_", " ")].append(full)

    # (模板, 外观) → 问题签名 → 聚合
    found: dict[str, dict[str, dict[str, Any]]] = defaultdict(lambda: defaultdict(dict))
    unattributed: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    rendered = 0
    by_design = 0
    for line in (OUT / args.results).read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if "error" in record:
            errors.append(f"{record['page']}: {record['error']}")
            continue
        rendered += 1
        signatures = {
            mode: {_signature(issue) for issue in result["issues"]}
            for mode, result in record["modes"].items()
        }
        for mode in MODES:
            # 基线里原样存在的低对比度是设计如此（彩色徽章之类），不算适配问题
            baseline = signatures.get(BASELINE if mode == "day" else "day", set())
            for issue in record["modes"][mode]["issues"]:
                if issue["chars"] < args.min_chars:
                    continue
                if _signature(issue) in baseline:
                    by_design += 1
                    continue
                owners = _attribute(issue, uses.get(record["page"], []), src)
                sig = f"{issue['anchor']} {issue['fg']} on {issue['bg']}"
                entry = {**issue, "page": record["page"], "mode": mode}
                if not owners:
                    key = f"{mode} {sig}"
                    slot = unattributed.setdefault(key, {**entry, "pages": set()})
                    slot["pages"].add(record["page"])
                    continue
                for owner in owners:
                    slot = found[owner][mode].setdefault(sig, {**entry, "pages": set()})
                    slot["pages"].add(record["page"])

    def score(template: str) -> tuple[int, int]:
        return (-usage.get(template, 0), -len(found[template]))

    lines = [
        "# 主题适配审计（Arknights 皮肤）",
        "",
        f"沙箱站点实际渲染 {rendered} 个页面（覆盖主名字空间引用到的模板 / 微件 / 模块），"
        f"三种外观下量正文文字与实际背景的对比度，低于 {args.threshold}:1 记为问题。",
        "",
        "- **day**：浅色；**night**：暗色；**os-dark**：自动偏好 + 系统暗色",
        "- 只在 os-dark 出问题、night 正常 → 缺 `skin-theme-clientpref-os` 分支",
        "- night 和 os-dark 都出问题 → 模板没有暗色适配（以前靠 darkModeFix / Vector 兜底）",
        "- day 出问题 → 深色底配了继承来的文字色（依赖 `--color-base` 等 Vector 变量）",
        "",
        f"已滤掉 {by_design} 条「设计如此」：白天模式以 Vector 浅色为参照，"
        "暗色以本皮肤白天模式为参照，参照里原样存在的低对比度（彩色徽章等）不算。",
        "",
        "归因方式：问题元素的类名（或行内底色）出现在页面所用模板的源码 / styles.css 里。"
        "同一类名被多个模板共用时会各记一次。",
        "",
        "## 汇总",
        "",
        "| 模板 | 引用页面数 | day | night | os-dark | 判断 |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    ordered = sorted(found, key=score)
    for template in ordered:
        modes = found[template]
        counts = {m: len(modes.get(m, {})) for m in MODES}
        if counts["os-dark"] and not counts["night"]:
            verdict = "缺 os 分支"
        elif counts["night"] and counts["day"]:
            verdict = "浅色 / 暗色都有问题"
        elif counts["night"]:
            verdict = "无暗色适配"
        else:
            verdict = "浅色下深底深字"
        lines.append(
            f"| [[{template}]] | {usage.get(template, 0)} | {counts['day'] or ''} "
            f"| {counts['night'] or ''} | {counts['os-dark'] or ''} | {verdict} |"
        )

    lines += ["", "## 明细", ""]
    for template in ordered:
        lines += [f"### {template}（{usage.get(template, 0)} 页）", ""]
        lines += [
            "| 外观 | 元素 | 文字 | 背景 | 对比度 | 底色来源 | 样例页 | 样例文字 |"
        ]
        lines += ["| --- | --- | --- | --- | ---: | --- | --- | --- |"]
        for mode in MODES:
            items = sorted(
                found[template].get(mode, {}).values(), key=lambda i: -i["chars"]
            )
            for item in items[: args.max_rows]:
                sample = item["sample"].replace("|", "¦").replace("\n", " ")
                lines.append(
                    f"| {mode} | `{item['anchor'] or item['element']}` | `{item['fg']}` "
                    f"| `{item['bg']}` | {item['ratio']} | {item['bgFrom']} "
                    f"| {sorted(item['pages'])[0]} | {sample} |"
                )
        lines.append("")

    lines += [
        "## 未能归因到模板",
        "",
        "多半是页面正文自己写的行内样式，或皮肤 / 扩展输出。",
        "",
    ]
    lines += ["| 外观 | 元素 | 文字 | 背景 | 对比度 | 页面数 | 样例页 | 样例文字 |"]
    lines += ["| --- | --- | --- | --- | ---: | ---: | --- | --- |"]
    rest = sorted(unattributed.values(), key=lambda i: -len(i["pages"]))
    for item in rest[: args.max_unattributed]:
        sample = item["sample"].replace("|", "¦").replace("\n", " ")
        lines.append(
            f"| {item['mode']} | `{item['anchor'] or item['element']}` | `{item['fg']}` "
            f"| `{item['bg']}` | {item['ratio']} | {len(item['pages'])} "
            f"| {sorted(item['pages'])[0]} | {sample} |"
        )
    if errors:
        lines += ["", "## 渲染失败的页面", ""] + [f"- {e}" for e in errors]

    path = ROOT / "reports" / args.output
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"{len(found)} 个模板有问题，未归因 {len(unattributed)} 条，失败 {len(errors)} 页"
    )
    print(f"报告：{path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_select = sub.add_parser("select")
    p_select.add_argument("--limit", type=int, default=0)
    p_select.add_argument("--top", type=int, default=60, help="给用量前 N 的模板补样")

    p_run = sub.add_parser("run")
    p_run.add_argument("--base", default="http://localhost:8080")
    p_run.add_argument("--workers", type=int, default=3)
    p_run.add_argument("--timeout", type=int, default=120)
    p_run.add_argument("--threshold", type=float, default=3.0)
    p_run.add_argument("--limit", type=int, default=0)
    p_run.add_argument("--fresh", action="store_true", help="清空已有结果重跑")
    p_run.add_argument(
        "--results", default="results.jsonl", help="结果文件名（复测时另存）"
    )
    p_run.add_argument(
        "--bust", action="store_true", help="URL 加随机参数绕过 CDN（线上复测用）"
    )
    p_run.add_argument(
        "--expand", action="store_true", help="先展开 AKCollapse / mw-collapsible 再量"
    )
    p_run.add_argument(
        "--preview", help="目录：其中有 <标题>.wiki 的页面，正文换成它的渲染结果再量"
    )
    p_run.add_argument("--css", help="渲染后追加这份样式表再量")
    p_run.add_argument("pages", nargs="*")

    p_report = sub.add_parser("report")
    p_report.add_argument("--threshold", type=float, default=3.0)
    p_report.add_argument("--min-chars", type=int, default=2)
    p_report.add_argument("--max-rows", type=int, default=8)
    p_report.add_argument("--max-unattributed", type=int, default=80)
    p_report.add_argument("--results", default="results.jsonl")
    p_report.add_argument("--output", default="theme-audit.md", help="报告文件名")

    args = parser.parse_args()
    asyncio.run({"select": select, "run": run, "report": report}[args.cmd](args))


if __name__ == "__main__":
    main()
