"""移动端表格：撑破页面的正文表格包横滑外壳。见 migration/mobile-table/README.md「第四步」。

不改皮肤：只在页面 wikitext 里给撑破正文栏的表格包一层
``<div class="ak-table-scroll">``（皮肤 base/tables.css 已有：overflow-x:auto; max-width:100%）。
旧皮肤（Vector / Minerva）不认这个类，外壳就是一个普通块，渲染不变。

哪张表要包不靠猜：先给源码里每张表打 ``data-mt`` 记号、用 parse API 渲染，换进现网页面
（``?useskin=arknights``，390 宽）量出真正伸出正文栏的那几张，再只包它们，包完再量一遍。

    uv run python scripts/mobile_table_scroll_apply.py prepare   # 取 wikitext、打记号渲染 → build/mts/prep/
    node scripts/mobile_table_scroll_measure.mjs detect          # 量哪些表伸出正文栏 → build/mts/detect.jsonl
    uv run python scripts/mobile_table_scroll_apply.py fix       # 生成包好外壳的 wikitext 并渲染 → build/mts/fix/
    node scripts/mobile_table_scroll_measure.mjs verify          # 360 / 390 / 1280 前后比对 → build/mts/verify.jsonl
    uv run python scripts/mobile_table_scroll_apply.py apply --dry-run
    uv run python scripts/mobile_table_scroll_apply.py apply     # 只写 verify 通过的页面，带 baserevid

幂等：已经在 ak-table-scroll 里的表不会再包。
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wikibot.config import get_settings, load_config
from wikibot.wiki import Wiki, gather_limited

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "migration" / "mobile-table" / "scroll-pages.txt"
WORK = ROOT / "build" / "mts"
SUMMARY = (
    "手机上撑破页面的表格包横滑外壳（ak-table-scroll），表格本身不动。"
    "见 prts-skin-migration/migration/mobile-table/README.md"
)
MANUAL_SUMMARY = (
    "模板调用里的定长宽度改成 min(Npx, 100%)：iOS 上不再撑破页面，桌面不变。"
    "见 prts-skin-migration/migration/mobile-table/README.md"
)
WRAP_OPEN = '<div class="ak-table-scroll">'
# 外壳自带上下外边距（--ak-space-4），并把里面 .wikitable 的外边距清零：对普通 wikitable 正好抵消。
# 表格自己的外边距不是这个值时（不是 wikitable、行内写了 margin）外壳不再加边距，留表格自己的。
WRAP_OPEN_FLAT = '<div class="ak-table-scroll" style="margin:0">'
WRAP_MARGIN = "16px"
WRAP_CLOSE = "</div>"
# 量出来外边距是默认值、但包上默认外壳后桌面高度仍会变的表（verify 报出来的），逐张指定不加边距
FLAT: dict[str, tuple[int, ...]] = {}
# detect 量不出来的：表里的内容靠脚本生成（音频播放器、拼图样片），换进去的静态 HTML 不够宽。
# 在真实页面上量过（build/mts/real.mjs），这些页的顶层表格都在页面源码里，序号一一对应
EXTRA: dict[str, tuple[int, ...]] = {
    "音乐鉴赏/游戏内音乐一览": (0,),
    "模板:音乐一览/doc": (0,),
    "揭幕者们/筹委会委托": tuple(range(0, 41, 2)),
}
# 表格由模板调用生成、宽度是调用处传的定长参数：同 table-fixed-width 的写法改成 min(Npx, 100%)。
# 定长宽度 Blink 压得住（皮肤 <640 的 max-width:100%），WebKit 当成最小宽度，只在 iOS 上撑破
MANUAL: dict[str, list[tuple[str, str]]] = {
    "保全派驻": [("|宽度=850px|", "|宽度=min(850px, 100%)|")],
}
# verify 没全过、但确认可以接受的：外壳是独立的格式化上下文，表格自己的外边距不再和相邻段落折叠
ACCEPT = {
    "月行水上/今日答案！": "桌面正文高 +8px",
    "黍的试验田/剧情": "桌面正文高 +24px",
    "保全派驻": "桌面上历史任务那张表 852 → 850px：里面嵌套的定宽表不再把它顶宽 2px",
}

# 这些区段里的 {| 不是表格：等长遮掉，偏移不变
_MASK = re.compile(
    r"<!--.*?-->|<(nowiki|pre|syntaxhighlight|source)\b[^>]*>.*?</\1\s*>",
    re.S | re.I,
)
_TOKEN = re.compile(
    r"^(?P<indent>[ \t:]*)(?P<wopen>\{\||\{\{\{!\}\})"
    r"|^[ \t]*(?P<wclose>\|\}|\{\{!\}\}\})"
    r"|(?P<hopen><table\b)"
    r"|(?P<hclose></table\s*>)",
    re.M | re.I,
)


@dataclass
class Table:
    mt: int
    start: int  # 开头记号的偏移（{| 或 <table）
    mark_at: int  # data-mt 插在这里
    end: int = -1  # 结尾记号之后
    kind: str = "wiki"
    top: bool = True
    notes: list[str] = field(default_factory=list)


def _mask(text: str) -> str:
    return _MASK.sub(lambda m: re.sub(r"[^\n]", "\0", m.group(0)), text)


def find_tables(text: str) -> list[Table]:
    """源码里的全部表格（含嵌套的），按开头出现的顺序。"""
    masked = _mask(text)
    tables: list[Table] = []
    stack: list[Table] = []
    for m in _TOKEN.finditer(masked):
        if m["wopen"] or m["hopen"]:
            tok = m["wopen"] or m["hopen"]
            start = m.start("wopen") if m["wopen"] else m.start("hopen")
            t = Table(
                mt=len(tables),
                start=start,
                mark_at=start + len(tok),
                kind="wiki" if m["wopen"] else "html",
                top=not stack,
            )
            line_start = masked.rfind("\n", 0, start) + 1
            if text[line_start:start].strip(" \t"):
                t.notes.append("开头不在行首")
            tables.append(t)
            stack.append(t)
        elif m["wclose"]:
            if not stack or stack[-1].kind != "wiki":
                continue
            t = stack.pop()
            t.end = m.end("wclose")
            if masked[t.end : t.end + 1] == "}":
                t.notes.append("结尾是 |}}")
        elif m["hclose"]:
            if not stack or stack[-1].kind != "html":
                continue
            t = stack.pop()
            t.end = m.end("hclose")
    for t in stack:
        t.notes.append("没找到结尾")
    return tables


def mark(text: str, tables: list[Table]) -> str:
    out, pos = [], 0
    for t in sorted(tables, key=lambda t: t.mark_at):
        out.append(text[pos : t.mark_at])
        out.append(f' data-mt="{t.mt}"')
        pos = t.mark_at
    out.append(text[pos:])
    return "".join(out)


def already_wrapped(text: str, t: Table) -> bool:
    before = text[: t.start].rstrip()
    return before.endswith((WRAP_OPEN, WRAP_OPEN_FLAT))


def wrap(
    text: str,
    tables: list[Table],
    ids: set[int],
    marked: bool,
    flat: frozenset[int] = frozenset(),
) -> str:
    """把 ids 里的顶层表格包进外壳。marked=True 时同时保留 data-mt 记号（只用于渲染比对）。"""
    inserts: list[tuple[int, int, str]] = []  # (偏移, 次序, 文本)
    for t in tables:
        if marked:
            inserts.append((t.mark_at, 1, f' data-mt="{t.mt}"'))
        if t.mt not in ids:
            continue
        line_end = text.find("\n", t.end)
        if line_end == -1:
            line_end = len(text)
        tail = text[t.end : line_end]
        inserts.append(
            (t.start, 0, (WRAP_OPEN_FLAT if t.mt in flat else WRAP_OPEN) + "\n")
        )
        if tail.strip():
            # |} 后面同一行还有东西：外壳收在 |} 之后，剩下的接在外壳后面
            inserts.append((t.end, 0, "\n" + WRAP_CLOSE))
        else:
            inserts.append((line_end, 0, "\n" + WRAP_CLOSE))
    out, pos = [], 0
    for at, _, s in sorted(inserts):
        out.append(text[pos:at])
        out.append(s)
        pos = at
    out.append(text[pos:])
    return "".join(out)


def blockers(text: str, t: Table) -> list[str]:
    """这张表不能自动包的理由。"""
    why = list(t.notes)
    if not t.top:
        why.append("嵌在别的表里")
    if t.end < 0:
        return why
    head_end = text.find("\n", t.start)
    head = text[t.start : head_end if head_end != -1 else len(text)]
    if re.search(r"float\s*:\s*(left|right)|\b(floatright|floatleft)\b", head, re.I):
        why.append("浮动表")
    if "ak-sticky-head" in head:
        why.append("吸顶表头")
    if already_wrapped(text, t):
        why.append("已在外壳里")
    return why


# 表格由模板生成的：外壳写进模板。每条是（原文, 改后），原文必须恰好出现一次
_OPEN = ("<includeonly>{|", f"<includeonly>{WRAP_OPEN}\n{{|")
_CLOSE = ("|}</includeonly>", f"|}}\n{WRAP_CLOSE}</includeonly>")
TEMPLATES: dict[str, list[tuple[str, str]]] = {
    # 卫戍协议敌人一览 5 页
    "模板:敌方情报/pure": [_OPEN, _CLOSE],
    # 沙洲遗闻 / 沙中之火的敌袭记录
    "模板:敌方情报/敌袭": [_OPEN, _CLOSE],
    "模板:特殊敌方情报": [
        _OPEN,
        (
            "|}{{#widget:style|style=#EnemyCE",
            f"|}}\n{WRAP_CLOSE}{{{{#widget:style|style=#EnemyCE",
        ),
    ],
    # 家具主题页的「总览」：两张定高大图并排，手机上 730px 宽
    "模板:家具主题总览": [
        _OPEN,
        (
            '| colspan="2"|{{{2}}}\n|}\n{{#switch:',
            f'| colspan="2"|{{{{{{2}}}}}}\n|}}\n{WRAP_CLOSE}\n{{{{#switch:',
        ),
    ],
    "模板:推荐间隔/yostar": [_OPEN, _CLOSE],
}
TEMPLATE_SUMMARY = (
    "表格包横滑外壳（ak-table-scroll）：手机上不再撑破页面，表格本身不动。"
    "见 prts-skin-migration/migration/mobile-table/README.md"
)


def rewrite(title: str, text: str, edits: list[tuple[str, str]]) -> str:
    for old, new in edits:
        if new in text:
            continue
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"{title}: 期望出现 1 次，实际 {n} 次：{old}")
        text = text.replace(old, new)
    return text


async def cmd_templates(ns: argparse.Namespace) -> None:
    wiki = await open_wiki(ns, login=True)
    async with wiki:
        for title, edits in TEMPLATES.items():
            if ns.only and title not in ns.only:
                continue
            page = await wiki.read(title)
            if page.missing:
                raise SystemExit(f"{title} 不存在")
            new = rewrite(title, page.content, edits)
            if new == page.content:
                print(f"  = {title}: 已是目标状态，跳过")
                continue
            diff = difflib.unified_diff(
                page.content.split("\n"),
                new.split("\n"),
                f"{title} (old)",
                f"{title} (new)",
                lineterm="",
                n=0,
            )
            print("\n".join(line[:200] for line in diff))
            if ns.dry_run:
                print(f"  [dry-run] {title}（r{page.revid}）")
                continue
            await wiki.edit(
                title, new, TEMPLATE_SUMMARY, baserevid=page.revid, nocreate=True
            )
            print(f"  ✔ {title} 已写入")


def safe(title: str) -> str:
    return quote(title.replace(" ", "_"), safe="")


def titles() -> list[str]:
    return [
        ln.strip()
        for ln in PAGES.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    ]


async def open_wiki(ns: argparse.Namespace, login: bool) -> Wiki:
    cfg = load_config(ns.config)
    print(f"目标站点：{cfg.api_url}")
    wiki = Wiki(
        cfg.api_url, cfg.user_agent, cfg.client, dry_run=getattr(ns, "dry_run", False)
    )
    if login:
        await wiki.login(*get_settings().require_credentials())
    return wiki


async def cmd_prepare(ns: argparse.Namespace) -> None:
    out = WORK / "prep"
    out.mkdir(parents=True, exist_ok=True)
    wiki = await open_wiki(ns, login=False)
    async with wiki:

        async def one(title: str) -> None:
            page = await wiki.read(title)
            if page.missing:
                print(f"  ! {title} 不存在")
                return
            tables = find_tables(page.content)
            html = await wiki.parse(mark(page.content, tables), page.title)
            rec = {
                "title": page.title,
                "revid": page.revid,
                "text": page.content,
                "tables": [asdict(t) for t in tables],
                "html": html,
            }
            (out / f"{safe(title)}.json").write_text(
                json.dumps(rec, ensure_ascii=False), encoding="utf-8"
            )
            print(f"  {page.title}: r{page.revid}，{len(tables)} 张表")

        todo = titles() if not ns.only else ns.only
        await gather_limited(4, [lambda t=t: one(t) for t in todo])


def load_detect() -> dict[str, dict]:
    path = WORK / "detect.jsonl"
    recs = {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln:
            r = json.loads(ln)
            recs[r["title"]] = r
    return recs


async def cmd_fix(ns: argparse.Namespace) -> None:
    out = WORK / "fix"
    out.mkdir(parents=True, exist_ok=True)
    detect = load_detect()
    wiki = await open_wiki(ns, login=False)
    report: list[str] = []
    async with wiki:

        async def one(path: Path) -> None:
            rec = json.loads(path.read_text(encoding="utf-8"))
            det = detect.get(rec["title"])
            if not det or det.get("error"):
                return
            text = rec["text"]
            tables = [Table(**t) for t in rec["tables"]]
            by_id = {t.mt: t for t in tables}
            ids, skipped = set(), []
            for mt in sorted({*det["offenders"], *EXTRA.get(rec["title"], ())}):
                why = blockers(text, by_id[mt])
                if why:
                    skipped.append(f"#{mt}：{'、'.join(why)}")
                else:
                    ids.add(mt)
            other = det.get("unmarked", [])
            line = f"{rec['title']}: 包 {len(ids)} 张"
            if MANUAL.get(rec["title"]):
                line += "；另有手工改写"
            if skipped:
                line += f"；跳过 {'；'.join(skipped)}"
            if other:
                line += f"；不在页面源码里的 {len(other)} 处：" + "；".join(
                    o["desc"] for o in other[:4]
                )
            report.append(line)
            manual = MANUAL.get(rec["title"], [])
            if not ids and not any(old in text for old, _ in manual):
                (out / path.name).unlink(missing_ok=True)
                return
            flat = frozenset(
                mt
                for mt in ids
                if (m := det.get("margins", {}).get(str(mt)))
                and not (m[2] and m[0] == m[1] == WRAP_MARGIN)
            ) | frozenset(FLAT.get(rec["title"], ()))
            new = wrap(text, tables, ids, marked=False, flat=flat)
            marked = wrap(text, tables, ids, marked=True, flat=flat)
            for old, repl in manual:
                new, marked = new.replace(old, repl), marked.replace(old, repl)
            html = await wiki.parse(marked, rec["title"])
            (out / path.name).write_text(
                json.dumps(
                    {
                        "title": rec["title"],
                        "revid": rec["revid"],
                        "ids": sorted(ids),
                        "flat": sorted(flat),
                        "text": new,
                        "html": html,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

        await gather_limited(
            4, [lambda p=p: one(p) for p in sorted((WORK / "prep").glob("*.json"))]
        )
    (WORK / "fix-report.txt").write_text("\n".join(sorted(report)) + "\n", "utf-8")
    print("\n".join(sorted(report)))


def load_verified() -> set[str]:
    ok = set()
    for ln in (WORK / "verify.jsonl").read_text(encoding="utf-8").splitlines():
        if ln:
            r = json.loads(ln)
            if r.get("ok") or r["title"] in ACCEPT:
                ok.add(r["title"])
    return ok


async def cmd_apply(ns: argparse.Namespace) -> None:
    verified = load_verified()
    wiki = await open_wiki(ns, login=True)
    done, failed = [], []
    async with wiki:
        for path in sorted((WORK / "fix").glob("*.json")):
            rec = json.loads(path.read_text(encoding="utf-8"))
            title = rec["title"]
            if ns.only and title not in ns.only:
                continue
            if title not in verified:
                print(f"  - {title}: verify 没过，跳过")
                continue
            page = await wiki.read(title)
            if page.content == rec["text"]:
                print(f"  = {title}: 已是目标状态，跳过")
                continue
            if page.revid != rec["revid"] and not ns.config:
                print(
                    f"  ! {title}: 取稿后被改过（r{rec['revid']} → r{page.revid}），跳过"
                )
                failed.append(title)
                continue
            if ns.verbose:
                diff = difflib.unified_diff(
                    page.content.split("\n"),
                    rec["text"].split("\n"),
                    f"{title} (old)",
                    f"{title} (new)",
                    lineterm="",
                    n=0,
                )
                print("\n".join(line[:200] for line in diff))
            if ns.dry_run:
                print(f"  [dry-run] {title}（r{page.revid}）包 {len(rec['ids'])} 张")
                continue
            try:
                await wiki.edit(
                    title,
                    rec["text"],
                    SUMMARY if rec["ids"] else MANUAL_SUMMARY,
                    baserevid=page.revid,
                    nocreate=True,
                )
            except Exception as e:
                print(f"  ! {title}: {e}")
                failed.append(title)
                continue
            done.append(title)
            print(f"  ✔ {title} 已写入（{len(rec['ids'])} 张）")
        if done:
            for i in range(0, len(done), 20):
                await wiki.purge(done[i : i + 20], forcelinkupdate=False)
    print(f"写入 {len(done)} 页，失败 / 跳过 {len(failed)} 页：{'、'.join(failed)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prepare", "fix", "apply", "templates"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true", help="apply 时打印 diff")
    ap.add_argument("--only", nargs="*", help="只处理这些页面")
    ap.add_argument(
        "-c", "--config", type=Path, help="换配置文件，如 config.sandbox.toml"
    )
    ns = ap.parse_args()
    cmds = {
        "prepare": cmd_prepare,
        "fix": cmd_fix,
        "apply": cmd_apply,
        "templates": cmd_templates,
    }
    asyncio.run(cmds[ns.cmd](ns))


if __name__ == "__main__":
    main()
