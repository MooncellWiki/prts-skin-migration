"""把规则跑到页面上，以及把结果写成报告。

这一层是纯函数、不碰网络也不碰磁盘之外的东西，方便单测。
"""

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from wikibot.models import PageChange, RuleHit, ScanHit

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from wikibot.models import Page
    from wikibot.rules import Rule


def scan_page(page: "Page", rules: "Sequence[Rule]") -> list[ScanHit]:
    """列出一个页面里所有命中的旧写法。"""
    hits: list[ScanHit] = []
    for rule in rules:
        hits.extend(rule.scan(page.title, page.content))
    return hits


def apply_rules(page: "Page", rules: "Sequence[Rule]") -> PageChange:
    """依次跑规则，返回改写结果（detect_only 的规则不产生改动）。"""
    text = page.content
    hits: list[RuleHit] = []
    for rule in rules:
        try:
            text, count = rule.apply_to(page.title, text)
        except Exception as exc:  # 单条规则炸掉不该拖垮整页
            return PageChange(
                title=page.title,
                revid=page.revid,
                before=page.content,
                after=page.content,
                hits=hits,
                error=f"规则 {rule.id} 执行失败：{exc}",
            )
        if count:
            hits.append(RuleHit(rule_id=rule.id, count=count))
    return PageChange(
        title=page.title,
        revid=page.revid,
        before=page.content,
        after=text,
        hits=hits,
    )


def summarize_hits(hits: "Iterable[ScanHit]") -> dict[str, Counter[str]]:
    """按规则统计：命中次数与涉及页面数。"""
    per_rule: Counter[str] = Counter()
    pages_per_rule: dict[str, set[str]] = {}
    for hit in hits:
        per_rule[hit.rule_id] += 1
        pages_per_rule.setdefault(hit.rule_id, set()).add(hit.title)
    return {
        "hits": per_rule,
        "pages": Counter({k: len(v) for k, v in pages_per_rule.items()}),
    }


# --------------------------------------------------------------------------
# 报告
# --------------------------------------------------------------------------


def _stamp() -> str:
    return datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def write_scan_report(
    hits: "Sequence[ScanHit]", report_dir: Path, target: str
) -> tuple[Path, Path]:
    """写出 Markdown 汇总 + JSONL 明细，返回两个文件路径。"""
    report_dir.mkdir(parents=True, exist_ok=True)
    jsonl = report_dir / f"scan-{target}.jsonl"
    with jsonl.open("w", encoding="utf-8") as f:
        for hit in hits:
            f.write(hit.model_dump_json() + "\n")

    stats = summarize_hits(hits)
    lines = [
        f"# 扫描报告：{target}",
        "",
        f"生成于 {_stamp()}，共 {len(hits)} 处命中，"
        f"涉及 {len({h.title for h in hits})} 个页面。",
        "",
        "| 规则 | 命中次数 | 涉及页面 |",
        "| --- | ---: | ---: |",
    ]
    for rule_id, count in stats["hits"].most_common():
        lines.append(f"| `{rule_id}` | {count} | {stats['pages'][rule_id]} |")

    lines += ["", "## 页面明细", "", "| 页面 | 命中规则 |", "| --- | --- |"]
    per_page: dict[str, Counter[str]] = {}
    for hit in hits:
        per_page.setdefault(hit.title, Counter())[hit.rule_id] += 1
    for title, counter in sorted(per_page.items(), key=lambda kv: -sum(kv[1].values())):
        detail = ", ".join(f"`{r}`×{c}" for r, c in counter.most_common())
        lines.append(f"| [{title}](https://prts.wiki/w/{title}) | {detail} |")

    md = report_dir / f"scan-{target}.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md, jsonl


def write_plan_report(
    changes: "Sequence[PageChange]", report_dir: Path, target: str
) -> tuple[Path, Path]:
    """写出改动预览：Markdown 汇总 + 全量 diff 文本。"""
    report_dir.mkdir(parents=True, exist_ok=True)
    changed = [c for c in changes if c.changed]
    failed = [c for c in changes if c.error]

    diff_path = report_dir / f"plan-{target}.diff"
    diff_path.write_text(
        "".join(c.diff() for c in changed) or "（无改动）\n", encoding="utf-8"
    )

    rule_counter: Counter[str] = Counter()
    for change in changed:
        for hit in change.hits:
            rule_counter[hit.rule_id] += hit.count

    lines = [
        f"# 改动预览：{target}",
        "",
        f"生成于 {_stamp()}，检查 {len(changes)} 个页面，"
        f"其中 {len(changed)} 个会被改动，{len(failed)} 个出错。",
        "",
        "| 规则 | 替换次数 |",
        "| --- | ---: |",
    ]
    lines += [f"| `{r}` | {c} |" for r, c in rule_counter.most_common()]
    lines += ["", "## 会被改动的页面", "", "| 页面 | 规则 |", "| --- | --- |"]
    lines += [f"| {c.title} | {c.summary_line()} |" for c in changed]
    if failed:
        lines += ["", "## 出错的页面", "", "| 页面 | 原因 |", "| --- | --- |"]
        lines += [f"| {c.title} | {c.error} |" for c in failed]
    lines += ["", f"完整 diff 见 `{diff_path.name}`。"]

    md = report_dir / f"plan-{target}.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md, diff_path


def dump_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
