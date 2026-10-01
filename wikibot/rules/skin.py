"""内置规则：prts.wiki 迁移到新版皮肤时反复出现的旧写法。

规则不是拍脑袋定的，是拿本地沙箱库（``wikibot scan --source db``）跑出来的：
模板 / 微件 / 模块 / MediaWiki 四个名字空间共约 1900 个页面里，
行内 style、写死颜色、写死像素宽度、``!important`` 是数量级最大的四类，
``.nomobile`` / ``.nodesktop`` 双份渲染与硬编码皮肤名则是改起来最麻烦的两类。

绝大多数规则是 ``detect_only``：新皮肤（mediawiki-skins-Arknights）的类名与
CSS 变量还在定，先用 scan 摸清现状，等约定敲定再逐条把 detect 换成 rewrite，
或者直接在 config.toml 里写声明式 ``[[regex_rules]]``。
"""

import json
import re
from collections.abc import Iterator
from pathlib import Path

from pydantic import PrivateAttr

from wikibot.rules.base import RegexRule, Rule

# --------------------------------------------------------------------------
# 一、响应式：旧站靠「渲染两份 + CSS 按皮肤藏一份」，新皮肤应当只渲染一份
# --------------------------------------------------------------------------

DUAL_RENDER = RegexRule(
    id="dual-render",
    description=(
        ".nomobile / .nodesktop 双份渲染：同一块内容输出桌面版和移动版两套 DOM，"
        "靠 CSS 按皮肤隐藏一套。新皮肤是单一响应式皮肤，应合并成一份"
    ),
    detect_only=True,
    pattern=r"\bno(?:mobile|desktop)\b",
)

DEVICE_ONLY_CLASS = RegexRule(
    id="device-only-class",
    description="mobileonly / desktoponly 等按设备显隐的类名，同上",
    detect_only=True,
    pattern=r"\b(?:mobileonly|desktoponly)\b",
)

HARDCODED_SKIN_NAME = RegexRule(
    id="hardcoded-skin-name",
    description="硬编码皮肤名（skin-vector-2022 / skin-minerva…），换皮肤后整段失效",
    detect_only=True,
    pattern=r"\bskin-(?:vector(?:-2022)?|minerva|monobook|timeless)\b",
)

LEGACY_SKIN_SELECTOR = RegexRule(
    id="legacy-skin-selector",
    description="依赖旧皮肤 DOM 结构的选择器，新皮肤下选不中",
    detect_only=True,
    pattern=(
        r"(?:#content\b|#bodyContent\b|#mw-content-text\b|#p-[a-z-]+\b"
        r"|\.mw-body(?:-content)?\b|\.vector-[a-z-]+)"
    ),
)

# --------------------------------------------------------------------------
# 二、样式：写死的颜色 / 尺寸挡住暗色模式与自适应
# --------------------------------------------------------------------------

HARDCODED_COLOR = RegexRule(
    id="hardcoded-color",
    description="写死的颜色值，暗色模式下会瞎，应改用皮肤的 CSS 变量",
    detect_only=True,
    pattern=(
        r"(?:color|background(?:-color)?|border(?:-[a-z]+)?-color)\s*:\s*"
        r"(?:#[0-9a-f]{3,8}|rgba?\([^)]*\)|hsla?\([^)]*\))"
    ),
    flags="i",
)

FIXED_PX_WIDTH = RegexRule(
    id="fixed-px-width",
    description="写死的像素宽度，窄屏 / 新皮肤内容区宽度变化后会溢出",
    detect_only=True,
    pattern=r"\b(?:max-|min-)?width\s*:\s*\d{3,}px",
    flags="i",
)

PX_FONT_SIZE = RegexRule(
    id="px-font-size",
    description="px 字号，不跟随用户字体设置，建议改 em / rem",
    detect_only=True,
    pattern=r"font-size\s*:\s*\d+px",
    flags="i",
)

RAW_STYLE_ATTR = RegexRule(
    id="raw-style-attr",
    description="较长的行内 style，建议抽到 TemplateStyles 子页面",
    detect_only=True,
    pattern=r"style\s*=\s*(?:\"[^\"]{40,}\"|'[^']{40,}')",
    flags="i",
)

IMPORTANT_FLAG = RegexRule(
    id="css-important",
    description="!important，通常是在跟旧皮肤样式打架，换皮肤后大概率要重来",
    detect_only=True,
    pattern=r"!\s*important",
    flags="i",
)

FLOAT_LAYOUT = RegexRule(
    id="float-layout",
    description="float 布局，建议改 flex / grid",
    detect_only=True,
    pattern=r"float\s*:\s*(?:left|right)",
    flags="i",
)

# --------------------------------------------------------------------------
# 三、HTML4 遗留：数量不多，但转换规则明确，适合自动改写
# --------------------------------------------------------------------------

DEPRECATED_HTML_ATTR = RegexRule(
    id="deprecated-html-attr",
    description="HTML4 表现属性（bgcolor / cellpadding / valign…），HTML5 已废弃",
    detect_only=True,
    pattern=(
        r"\b(?:bgcolor|cellpadding|cellspacing|valign|hspace|vspace|frame|rules)"
        r"\s*=\s*[\"']?[^\s\"'|>]+"
    ),
    flags="i",
)

CENTER_TAG = RegexRule(
    id="center-tag",
    description="<center> 标签，HTML5 已废弃（块级 / 行内语义不同，需人工判断怎么换）",
    detect_only=True,
    pattern=r"</?center\s*>",
    flags="i",
)


_FONT_OPEN = re.compile(r"<font\b([^>]*)>", re.IGNORECASE)
_FONT_CLOSE = re.compile(r"</font\s*>", re.IGNORECASE)
# 成对匹配：只有开闭齐全、内部不再嵌套 font 的才敢动
_FONT_PAIR = re.compile(
    r"<font\b([^>]*)>((?:(?!</?font\b).)*?)</font\s*>", re.IGNORECASE | re.DOTALL
)
_FONT_ATTR = re.compile(
    r"\b(color|size|face)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>{|]+))", re.IGNORECASE
)
# 属性里出现这些说明值是模板 / 解析器函数拼出来的，机器改不动，留给人
_WIKI_MARKUP = re.compile(r"\{\{|\}\}|\[\[|\|")
# <font size> 是 1-7 的老式档位，换算成相对字号
_FONT_SIZE_SCALE = {
    "1": "x-small",
    "2": "small",
    "3": "medium",
    "4": "large",
    "5": "x-large",
    "6": "xx-large",
    "7": "xxx-large",
}


class FontTagRule(Rule):
    """``<font>`` → ``<span style=...>``。

    HTML5 已移除 ``<font>``，各皮肤对它的兜底样式并不一致。
    转换是语义等价的：color / size / face 一一映射到 CSS 属性。

    只改**成对出现、内部不嵌套 font、属性里没有 wiki 标记**的标签。
    prts.wiki 上大量存在 ``<font color={{#switch:…}}>`` 这种属性值由解析器函数
    拼出来的写法，正则改它必然改坏（实测会把 ``{{#switch:`` 拆到引号里去），
    这类一律原样留下，交给人处理——扫描仍会报告它们。
    """

    id: str = "font-tag"
    description: str = "<font> 标签 → <span style=...>（含 wiki 标记的跳过）"

    def matches(self, text: str) -> Iterator[re.Match[str]]:
        """扫描时报告所有 font 标签，包括不会自动改的那些。"""
        yield from _FONT_OPEN.finditer(text)
        yield from _FONT_CLOSE.finditer(text)

    def rewrite(self, text: str) -> tuple[str, int]:
        converted = 0

        def replace(match: re.Match[str]) -> str:
            nonlocal converted
            attrs, body = match.group(1) or "", match.group(2)
            if _WIKI_MARKUP.search(attrs):
                return match.group(0)  # 属性是模板拼的，不碰
            converted += 1
            return f"{self._convert_open(attrs)}{body}</span>"

        # 只数真正换掉的，跳过的不计入命中次数
        return _FONT_PAIR.sub(replace, text), converted

    @staticmethod
    def _convert_open(attrs: str) -> str:
        styles: list[str] = []
        rest = attrs
        for attr in _FONT_ATTR.finditer(attrs):
            name = attr.group(1).lower()
            value = next(g for g in attr.groups()[1:] if g is not None)
            if name == "color":
                styles.append(f"color:{value}")
            elif name == "size":
                styles.append(f"font-size:{_FONT_SIZE_SCALE.get(value, 'medium')}")
            else:
                styles.append(f"font-family:{value}")
            rest = rest.replace(attr.group(0), "", 1)
        rest = rest.strip()
        parts = ["span"]
        if rest:
            parts.append(rest)
        if styles:
            parts.append(f'style="{";".join(styles)}"')
        return f"<{' '.join(parts)}>"


# 表格开头：wikitext 的 {| 整行，或 HTML 的 <table …>
_TABLE_OPEN = re.compile(
    r"\{\|(?P<wiki>[^\n]*)|<table\b(?P<html>[^>]*)>", re.IGNORECASE
)
_STYLE_ATTR = re.compile(
    r"""\bstyle\s*=\s*(?P<q>["'])(?P<css>.*?)(?P=q)""", re.IGNORECASE
)
# 定长 width 声明（不含 max-/min-width）；后面必须紧跟 ; 或样式结尾，
# 跟着 {{…}} 之类拼接出来的东西就不碰
_FIXED_WIDTH_DECL = re.compile(
    r"(?<![-\w])width\s*:\s*(?P<num>\d*\.?\d+)(?P<unit>px|em|rem)"
    r"\s*(?P<imp>!\s*important)?\s*(?=;|$)",
    re.IGNORECASE,
)
_ANY_WIDTH_DECL = re.compile(r"(?<![-\w])width\s*:", re.IGNORECASE)
_MIN_WIDTH_DECL = re.compile(r"(?<![-\w])width\s*:\s*min\(", re.IGNORECASE)
_WIDTH_ATTR = re.compile(
    r"""(?<![-\w])width\s*=\s*(?P<q>["']?)(?P<num>\d+)(?:px)?(?P=q)(?![\w%])""",
    re.IGNORECASE,
)
# 本规则第一版的输出「width:800px; width:min(800px, 100%)」：收成后一条
_MIGRATED_PAIR = re.compile(
    r"(?<![-\w])width\s*:\s*(?P<num>\d*\.?\d+)(?P<unit>px|em|rem)\s*(?:!\s*important)?"
    r"\s*;\s*(?P<min>width:min\((?P=num)(?P=unit), 100%\)(?: !important)?)",
    re.IGNORECASE,
)


class TableFixedWidthRule(Rule):
    """表格的定宽 ``width:800px`` → ``width:min(800px, 100%)``。

    WebKit（iOS 上所有浏览器）把自动表格布局里的定长 width 当成表格的最小宽度，
    ``max-width:100%`` 压不住，手机上整页被撑宽；``min()`` 不是定长，不触发这条怪癖。

    选这个写法而不是 ``width:100%; max-width:800px``，是为了**现有渲染一像素不变**：

    - 桌面：容器不窄于 800px 时两者结果相同；
    - Minerva（m.prts.wiki，<640）：``.content table { width:100% !important }``
      照样把它盖掉，与改前一样；而 ``max-width`` 会把本该拉满的窄表封顶。

    ``width="800"`` 属性同理：去掉属性，换成 ``style`` 里的 ``width:min(…)``。
    第一版输出过 ``width:800px; width:min(800px, 100%)``（旧值留作不认 ``min()``
    的浏览器的回落），这里一并收成一条。
    只改宽于 ``min_px`` 的表格：更窄的在任何手机上都放得下，改了只是白白重渲染。

    **跳过名单**（``skip_path``，``{页面标题: [表格 style 原文, …]}``）：
    表格的父容器宽度由表格撑出来时（单元格里、浮动 / inline-block 容器里…），
    定宽换成带百分比的 ``min()`` 会让容器改按内容收缩、表格跟着变窄，
    桌面渲染就变了。浏览器按布局环境归类验证后，有变化的表格逐个列进名单，原样跳过。
    """

    id: str = "table-fixed-width"
    description: str = "表格定宽 width:Npx → width:min(Npx, 100%)，窄屏不再撑破页面"
    min_px: float = 300
    skip_path: str = "migration/table-fixed-width/skip.json"

    _skip: dict[str, set[str]] | None = PrivateAttr(default=None)
    _skip_now: frozenset[str] = PrivateAttr(default=frozenset())

    def _load_skip(self) -> dict[str, set[str]]:
        if self._skip is None:
            path = Path(self.skip_path)
            if not path.is_absolute():
                path = Path(__file__).resolve().parents[2] / path
            data = json.loads(path.read_text("utf-8")) if path.exists() else {}
            self._skip = {title: set(styles) for title, styles in data.items()}
        return self._skip

    def apply_to(self, title: str, text: str) -> tuple[str, int]:
        self._skip_now = frozenset(self._load_skip().get(title, ()))
        try:
            return self.apply(text)
        finally:
            self._skip_now = frozenset()

    def _too_narrow(self, num: str, unit: str) -> bool:
        px = float(num) * (1 if unit.lower() == "px" else 16)
        return px < self.min_px

    def matches(self, text: str) -> Iterator[re.Match[str]]:
        for table in _TABLE_OPEN.finditer(text):
            if self._rewrite_attrs(table.group("wiki") or table.group("html") or "")[1]:
                yield table

    def rewrite(self, text: str) -> tuple[str, int]:
        total = 0

        def replace(table: re.Match[str]) -> str:
            nonlocal total
            key = "wiki" if table.group("wiki") is not None else "html"
            attrs = table.group(key)
            new_attrs, count = self._rewrite_attrs(attrs)
            if not count:
                return table.group(0)
            total += count
            start, end = table.span(key)
            offset = table.start()
            whole = table.group(0)
            return whole[: start - offset] + new_attrs + whole[end - offset :]

        return _TABLE_OPEN.sub(replace, text), total

    @staticmethod
    def _set_css(attrs: str, css: str) -> str:
        """把 style 的值换成 css；没有 style 属性就在末尾补一个。"""
        style = _STYLE_ATTR.search(attrs)
        if style:
            start, end = style.span("css")
            return attrs[:start] + css + attrs[end:]
        return f'{attrs.rstrip()} style="{css}"'

    @staticmethod
    def _width_attr(attrs: str) -> re.Match[str] | None:
        """style 属性之外的 width= 属性。"""
        style = _STYLE_ATTR.search(attrs)
        for attr in _WIDTH_ATTR.finditer(attrs):
            if style and style.start() <= attr.start() < style.end():
                continue
            return attr
        return None

    @staticmethod
    def _drop(attrs: str, attr: re.Match[str]) -> str:
        left, right = attrs[: attr.start()].rstrip(), attrs[attr.end() :]
        if left and right and not right[:1].isspace():
            right = " " + right
        return left + right

    def _rewrite_attrs(self, attrs: str) -> tuple[str, int]:
        style = _STYLE_ATTR.search(attrs)
        css = style.group("css") if style else ""
        if css.strip() in self._skip_now:
            return attrs, 0

        # 第一版留下的两条：收成 min() 一条
        new_css, pairs = _MIGRATED_PAIR.subn(r"\g<min>", css)
        if pairs:
            return self._set_css(attrs, new_css), pairs
        if _MIN_WIDTH_DECL.search(css):
            # 已经是 min()：只剩第一版保留下来的 width 属性（数值相同）要去掉
            attr = self._width_attr(attrs)
            if attr and f"width:min({attr.group('num')}px, 100%)" in css:
                return self._drop(attrs, attr), 1
            return attrs, 0

        if style and _FIXED_WIDTH_DECL.search(css):
            count = 0

            def to_min(decl: re.Match[str]) -> str:
                nonlocal count
                if self._too_narrow(decl.group("num"), decl.group("unit")):
                    return decl.group(0)
                count += 1
                length = decl.group("num") + decl.group("unit")
                imp = " !important" if decl.group("imp") else ""
                return f"width:min({length}, 100%){imp}"

            new_css = _FIXED_WIDTH_DECL.sub(to_min, css)
            return (self._set_css(attrs, new_css), count) if count else (attrs, 0)

        # width 属性：样式里另有 width 声明时属性本来就不生效，不碰
        attr = self._width_attr(attrs)
        if not attr or _ANY_WIDTH_DECL.search(css):
            return attrs, 0
        if self._too_narrow(attr.group("num"), "px"):
            return attrs, 0
        decl = f"width:min({attr.group('num')}px, 100%)"
        sep = "" if not css.strip() or css.rstrip().endswith(";") else ";"
        new_css = f"{css.rstrip()}{sep} {decl}".lstrip()
        return self._set_css(self._drop(attrs, attr), new_css), 1


BUILTIN_RULES: list[Rule] = [
    DUAL_RENDER,
    DEVICE_ONLY_CLASS,
    HARDCODED_SKIN_NAME,
    LEGACY_SKIN_SELECTOR,
    HARDCODED_COLOR,
    FIXED_PX_WIDTH,
    PX_FONT_SIZE,
    RAW_STYLE_ATTR,
    IMPORTANT_FLAG,
    FLOAT_LAYOUT,
    DEPRECATED_HTML_ATTR,
    CENTER_TAG,
    FontTagRule(),
    TableFixedWidthRule(),
]
