"""本地页面快照。

抓一次存一份，之后 scan / plan 都能离线跑，也方便和下一次抓取做对比。
文件名用 URL 编码后的完整标题，可逆且不会踩到 ``/`` 之类的字符。
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote, unquote

from wikibot.models import Page

if TYPE_CHECKING:
    from collections.abc import Iterator

INDEX_NAME = "index.json"


class PageCache:
    """``cache/`` 目录的读写封装。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.pages_dir = root / "pages"
        self._index: dict[str, dict[str, object]] | None = None

    # ------------------------------------------------------------------ 索引

    @property
    def index(self) -> dict[str, dict[str, object]]:
        if self._index is None:
            path = self.root / INDEX_NAME
            self._index = (
                json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
            )
        return self._index

    def save_index(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / INDEX_NAME).write_text(
            json.dumps(self.index, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------ 读写

    def path_for(self, title: str) -> Path:
        return self.pages_dir / f"{quote(title, safe='')}.txt"

    def store(self, page: Page) -> None:
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.path_for(page.title).write_text(page.content, encoding="utf-8")
        self.index[page.title] = {
            "pageid": page.pageid,
            "ns": page.ns,
            "revid": page.revid,
            "content_model": page.content_model,
        }

    def load(self, title: str) -> Page | None:
        path = self.path_for(title)
        if not path.is_file():
            return None
        meta = self.index.get(title, {})
        return Page(
            pageid=int(meta.get("pageid", 0) or 0),
            ns=int(meta.get("ns", 0) or 0),
            title=title,
            revid=int(meta.get("revid", 0) or 0),
            content=path.read_text(encoding="utf-8"),
            content_model=str(meta.get("content_model", "wikitext")),
        )

    def iter_pages(self, namespaces: "list[int] | None" = None) -> "Iterator[Page]":
        """遍历缓存里的页面；索引缺失时退化成扫目录。"""
        if self.index:
            titles = sorted(self.index)
        elif self.pages_dir.is_dir():
            titles = sorted(unquote(p.stem) for p in self.pages_dir.glob("*.txt"))
        else:
            titles = []
        for title in titles:
            page = self.load(title)
            if page and (namespaces is None or page.ns in namespaces):
                yield page

    def __len__(self) -> int:
        return len(self.index)
