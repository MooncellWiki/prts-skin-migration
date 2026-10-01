"""贯穿抓取 → 扫描 → 改写 → 提交各环节的数据模型。"""

import difflib
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PageRef(BaseModel):
    """页面的轻量标识，列举名字空间时用。"""

    model_config = ConfigDict(frozen=True)

    pageid: int
    ns: int
    title: str


class Page(BaseModel):
    """带正文的页面快照。``revid`` 用于提交时防编辑冲突。"""

    pageid: int = 0
    ns: int = 0
    title: str
    revid: int = 0
    timestamp: datetime | None = None
    """最新修订的时间戳，作为 edit 的 basetimestamp。"""
    content: str = ""
    missing: bool = False
    content_model: str = "wikitext"

    @property
    def ref(self) -> PageRef:
        return PageRef(pageid=self.pageid, ns=self.ns, title=self.title)


class RuleHit(BaseModel):
    """某条规则在一个页面上的命中情况。"""

    rule_id: str
    count: int
    """替换发生的次数；扫描模式下为匹配次数。"""


class ScanHit(BaseModel):
    """扫描到的一处待迁移写法，带行号方便人工核对。"""

    title: str
    rule_id: str
    line_no: int
    line: str
    match: str


class PageChange(BaseModel):
    """一个页面跑完全部规则后的结果。"""

    title: str
    revid: int = 0
    before: str = ""
    after: str = ""
    hits: list[RuleHit] = Field(default_factory=list)
    error: str | None = None

    @property
    def changed(self) -> bool:
        return self.error is None and self.before != self.after

    @property
    def rule_ids(self) -> list[str]:
        return [hit.rule_id for hit in self.hits]

    def summary_line(self) -> str:
        """形如 ``legacy-class×3, inline-style×1`` 的规则命中摘要。"""
        return ", ".join(f"{hit.rule_id}×{hit.count}" for hit in self.hits)

    def diff(self, context: int = 3) -> str:
        """统一 diff 文本，用于 plan 预览与报告。"""
        return "".join(
            difflib.unified_diff(
                self.before.splitlines(keepends=True),
                self.after.splitlines(keepends=True),
                fromfile=f"a/{self.title}",
                tofile=f"b/{self.title}",
                n=context,
            )
        )
