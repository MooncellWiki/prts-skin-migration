"""规则基类。

一条规则做两件事：**检测**（scan 时报告哪里有旧写法）和**改写**（plan/apply 时重写）。
把两者放在同一个对象里，保证「扫描到的」和「会被改的」永远是同一批位置。

``detect_only=True`` 的规则只报告不改写——新皮肤的写法还没定死之前，
先用它把现状摸清楚，比贸然批量替换安全得多。
"""

import re
from abc import ABC, abstractmethod
from collections.abc import Iterator

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

from wikibot.config import compile_pattern, parse_flags
from wikibot.models import ScanHit

# 逐字显示 / 不被解析的区段：里面的「旧写法」是给人看的文本，既不该改也不该报
LITERAL_SPAN = re.compile(
    r"<!--.*?-->|<(nowiki|pre|syntaxhighlight|source)\b[^>]*>.*?</\1\s*>",
    re.DOTALL | re.IGNORECASE,
)
# 代码区段：wikitext 规则改进去必然改坏（微件里大量 <script>），但扫描仍应报告
CODE_SPAN = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.DOTALL | re.IGNORECASE)


def spans_of(text: str, *patterns: re.Pattern[str]) -> list[tuple[int, int]]:
    """求出若干正则命中的区间，按起点排序。"""
    spans = [m.span() for pattern in patterns for m in pattern.finditer(text)]
    return sorted(spans)


def in_spans(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in spans)


class Rule(BaseModel, ABC):
    """一条迁移规则。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    """规则标识，CLI 用 ``-r/--rule`` 选取。"""
    description: str = ""
    """人话说明这条规则在解决什么问题。"""
    detect_only: bool = False
    """只报告不改写。"""
    respect_protected: bool = True
    """改写时避开 <nowiki>/<pre>/<script>/<style> 等区段。

    专门处理这些区段内容的规则（比如只改 <style> 里的 CSS）才需要关掉。
    """

    @abstractmethod
    def matches(self, text: str) -> Iterator[re.Match[str]]:
        """产出全部命中位置，供 scan 定位行号。"""

    def rewrite(self, text: str) -> tuple[str, int]:
        """返回 (改写后文本, 替换次数)。detect_only 规则不必实现。"""
        raise NotImplementedError(f"规则 {self.id} 没有实现改写")

    def apply(self, text: str) -> tuple[str, int]:
        """detect_only 时原样返回，否则在非保护区段上执行改写。"""
        if self.detect_only:
            return text, 0
        if not self.respect_protected:
            return self.rewrite(text)
        return self._rewrite_outside(text, spans_of(text, LITERAL_SPAN, CODE_SPAN))

    def apply_to(self, title: str, text: str) -> tuple[str, int]:
        """带页面标题的改写入口。需要按页面区别对待的规则（比如有跳过名单）覆写它。"""
        return self.apply(text)

    def _rewrite_outside(
        self, text: str, protected: list[tuple[int, int]]
    ) -> tuple[str, int]:
        """把文本按保护区切开，只改保护区之外的片段。"""
        if not protected:
            return self.rewrite(text)
        pieces: list[str] = []
        total = 0
        cursor = 0
        for start, end in protected:
            if start < cursor:  # 区间重叠（比如注释套在 pre 里），跳过
                continue
            chunk, count = self.rewrite(text[cursor:start])
            pieces += [chunk, text[start:end]]
            total += count
            cursor = end
        chunk, count = self.rewrite(text[cursor:])
        pieces.append(chunk)
        return "".join(pieces), total + count

    def scan(self, title: str, text: str) -> list[ScanHit]:
        """把命中位置翻译成带行号的 ScanHit。"""
        if not text:
            return []
        # 预先算好每行起始偏移，二分查行号比逐次 count("\n") 快得多
        line_starts = [0]
        for line in text.splitlines(keepends=True):
            line_starts.append(line_starts[-1] + len(line))
        lines = text.splitlines()

        # <nowiki>/<pre> 里的旧写法只是被逐字显示的示例，报出来全是噪音
        literal = spans_of(text, LITERAL_SPAN) if self.respect_protected else []

        hits: list[ScanHit] = []
        for match in self.matches(text):
            if in_spans(match.start(), literal):
                continue
            line_no = _line_of(line_starts, match.start())
            hits.append(
                ScanHit(
                    title=title,
                    rule_id=self.id,
                    line_no=line_no,
                    line=lines[line_no - 1].strip() if line_no <= len(lines) else "",
                    match=match.group(0),
                )
            )
        return hits


class RegexRule(Rule):
    """正则查找 / 替换。config.toml 里的声明式规则也会变成它。"""

    pattern: str
    replacement: str = ""
    flags: str = ""

    _compiled: re.Pattern[str] = PrivateAttr()

    @field_validator("pattern")
    @classmethod
    def _check_pattern(cls, value: str) -> str:
        compile_pattern(value)
        return value

    @field_validator("flags")
    @classmethod
    def _check_flags(cls, value: str) -> str:
        parse_flags(value)
        return value

    def model_post_init(self, context: object, /) -> None:
        self._compiled = re.compile(self.pattern, parse_flags(self.flags))

    @property
    def compiled(self) -> re.Pattern[str]:
        return self._compiled

    def matches(self, text: str) -> Iterator[re.Match[str]]:
        return self._compiled.finditer(text)

    def rewrite(self, text: str) -> tuple[str, int]:
        return self._compiled.subn(self.replacement, text)


def _line_of(line_starts: list[int], offset: int) -> int:
    """由字符偏移求 1 起始的行号。"""
    lo, hi = 0, len(line_starts) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if line_starts[mid] <= offset:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1
