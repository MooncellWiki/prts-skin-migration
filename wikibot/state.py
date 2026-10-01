"""迁移进度。

批量改上千个页面必然要分批、会中断、会失败重跑，
所以每个页面改了什么、改到哪个修订，都记在 state.json 里。
"""

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class Status(StrEnum):
    DONE = "done"
    """已提交。"""
    SKIPPED = "skipped"
    """规则没命中或人工跳过。"""
    FAILED = "failed"
    """提交失败，可重跑。"""


class PageState(BaseModel):
    status: Status
    revid: int = 0
    """提交后的新修订号（dry-run 时为改前的修订号）。"""
    rules: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error: str | None = None


class MigrationState(BaseModel):
    """state.json 的整体结构。"""

    version: int = 1
    pages: dict[str, PageState] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "MigrationState":
        if not path.is_file():
            return cls()
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            self.model_dump_json(indent=2, exclude_none=False), encoding="utf-8"
        )

    def is_done(self, title: str) -> bool:
        entry = self.pages.get(title)
        return entry is not None and entry.status is Status.DONE

    def record(
        self,
        title: str,
        status: Status,
        revid: int = 0,
        rules: list[str] | None = None,
        error: str | None = None,
    ) -> None:
        self.pages[title] = PageState(
            status=status,
            revid=revid,
            rules=rules or [],
            error=error,
        )

    def counts(self) -> dict[str, int]:
        result = dict.fromkeys(Status, 0)
        for entry in self.pages.values():
            result[entry.status] += 1
        return {status.value: count for status, count in result.items()}
