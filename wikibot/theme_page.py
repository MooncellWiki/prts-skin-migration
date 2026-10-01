"""条目页的暗色规则：从条目源码里写死的行内颜色推导。

集成战略这类大条目把配色直接写在正文里：浅色底的面板 / 表格行、深色的强调字
（``{{color|#8e2309|…}}``）、页内 ``{{#widget:style}}`` 定义的浅色块。暗色下它们
不会跟着变，于是浅底浅字、深底深字。这里扫一遍源码，按 ``theme_palette`` 的规则
推出暗色值，生成一组 night 规则（os 分支照例由 ``theme_os`` 机械生成）：

- **浅色底**：表格 / 行 / 单元格 / div 这类「面板」，或没写文字色的任何元素，换成
  ``dark_variant``。写了文字色的行内徽章（span）保持原样——深字配浅底本来就读得清
- **深色字**：没写底色的元素上、在暗色表面达不到 4.5:1 的文字色，换成 ``text_variant``
- **页内样式**：``{{#widget:style}}`` 里写了浅色底、没写文字色的类，同样换底色

行内样式只能用属性选择器去认（``!important`` 才压得过行内）。两处细节：

- 折叠表格展开 / 收起时，脚本改了行的 ``style.display``，浏览器会把整段 style
  重新序列化成 ``background: rgb(204, 237, 129); color: rgb(…)`` 这种写法，
  按源码字面匹配的选择器从此失效。行和 div 额外生成一份序列化后的写法
- 选择器带上声明两侧的分隔符（``;``、开头 ``^=``、结尾 ``$=``），
  避免 ``background:#fff`` 误中 ``background:#fff8e1``、
  ``color:`` 误中 ``background-color:``
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from wikibot.theme_os import NIGHT, parse_rules, strip_generated, style_spans
from wikibot.theme_palette import (
    DARK_LINK,
    DARK_TEXT,
    contrast,
    dark_variant,
    parse_hex,
    text_variant,
    to_oklch,
)

# CSS 具名颜色里站内实际出现过的那些（源码里写 lightgrey / darkred 之类）
NAMED_COLORS = {
    "white": "#ffffff",
    "black": "#000000",
    "red": "#ff0000",
    "darkred": "#8b0000",
    "maroon": "#800000",
    "brown": "#a52a2a",
    "firebrick": "#b22222",
    "crimson": "#dc143c",
    "blue": "#0000ff",
    "navy": "#000080",
    "darkblue": "#00008b",
    "mediumblue": "#0000cd",
    "green": "#008000",
    "darkgreen": "#006400",
    "darkolivegreen": "#556b2f",
    "teal": "#008080",
    "darkcyan": "#008b8b",
    "purple": "#800080",
    "indigo": "#4b0082",
    "darkmagenta": "#8b008b",
    "darkslategray": "#2f4f4f",
    "darkslategrey": "#2f4f4f",
    "dimgray": "#696969",
    "dimgrey": "#696969",
    "gray": "#808080",
    "grey": "#808080",
    "lightgray": "#d3d3d3",
    "lightgrey": "#d3d3d3",
    "gainsboro": "#dcdcdc",
    "whitesmoke": "#f5f5f5",
    "silver": "#c0c0c0",
    "pink": "#ffc0cb",
    "lightpink": "#ffb6c1",
    "mistyrose": "#ffe4e1",
    "lavender": "#e6e6fa",
    "lightyellow": "#ffffe0",
    "lightblue": "#add8e6",
    "lightcyan": "#e0ffff",
    "aliceblue": "#f0f8ff",
    "honeydew": "#f0fff0",
    "ivory": "#fffff0",
    "beige": "#f5f5dc",
    "linen": "#faf0e6",
    "snow": "#fffafa",
    "seashell": "#fff5ee",
    "lemonchiffon": "#fffacd",
    "cornsilk": "#fff8dc",
    "gold": "#ffd700",
    "orange": "#ffa500",
    "yellow": "#ffff00",
}

# 模板:Color 自己会把这几个值换成语义变量（Common.css 给了暗色值），不用再管。
# 正文里手写的同色值也用同一个变量，同一页不会出现两种红
COLOR_TEMPLATE_HANDLED = {
    *("red", "#f00", "#ff0000", "#c0392b"),
    *("black", "#000", "#000000"),
}
SEMANTIC_TEXT = {
    "#ff0000": "var(--prts-alert-text)",
    "#c0392b": "var(--prts-red-text)",
    "#000000": "var(--prts-page-text)",
}

_STYLE_ATTR = re.compile(r"""style(?:\{\{=\}\}|=)\s*(["'])(.*?)\1""", re.DOTALL)
_COLOR_TEMPLATE = re.compile(r"\{\{\s*[Cc]olor\s*\|\s*([^|{}]+?)\s*\|")
# {{Font|color=X|…}} → <span style="… color: X; …">（冒号后带空格，前面可能有字号）
_FONT_TEMPLATE = re.compile(
    r"\{\{\s*[Ff]ont\s*\|(?:[^|{}]*\|)*?\s*color\s*=\s*([^|{}]+?)\s*[|}]"
)
_DECL = re.compile(
    r"(?P<prop>(?<![\w-])(?:background-color|background|color))\s*:\s*(?P<value>[^;]*)"
)
_SOLID = re.compile(
    r"(#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?|[a-zA-Z]+)(\s*!important)?\s*"
)
_GRADIENT = re.compile(
    r"(?:repeating-)?(?:linear|radial)-gradient\((?:[^()]|\([^()]*\))*\)"
)
# 渐变里的颜色：#hex 或具名颜色（排除 to / deg 之类的关键字和函数名）
_STOP_COLOR = re.compile(
    r"#[0-9a-fA-F]{3,8}\b|(?<![\w#.-])[a-zA-Z]+\b(?![\w(-])(?!\s*\()"
)
_HTML_TAG = re.compile(r"<\s*([a-zA-Z][a-zA-Z0-9]*)[^<>]*$")

# 「面板」：浅色底配深字也要换暗色（里面的链接是皮肤暗色链接色，浅底上看不清）
PANEL_TAGS = ("table", "tr", "cell", "div")
NIGHT_SCOPE = f"html.{NIGHT} .mw-parser-output"


def to_hex(value: str) -> str | None:
    value = value.strip().lower()
    if value.startswith("#"):
        try:
            parse_hex(value)
        except ValueError:
            return None
        if len(value) == 4:
            value = "#" + "".join(c * 2 for c in value[1:])
        return value
    return NAMED_COLORS.get(value)


@dataclass(frozen=True)
class Decl:
    prop: str  # background / background-color / color
    value: str  # 声明值原文（去掉 !important）
    hex: str | None  # 纯色时的 #rrggbb
    stops: tuple[str, ...]  # 渐变时各色标的 #rrggbb（全是渐变、没有图片）
    text: str  # 源码里的声明原文（不含分隔符）
    start: bool  # 在 style 开头
    end: bool  # 在 style 结尾（后面只剩空白）
    after: str  # 紧跟着的分隔符（; 或空格），结尾时为空


@dataclass(frozen=True)
class InlineStyle:
    tag: str  # table / tr / cell / div / span / …
    value: str
    background: Decl | None
    color: Decl | None


def _tag_at(text: str, pos: int) -> str:
    """``style=`` 落在什么元素上：HTML 标签，或 wikitable 的表 / 行 / 单元格。"""
    line_start = text.rfind("\n", 0, pos) + 1
    before = text[line_start:pos]
    tag = _HTML_TAG.search(before)
    if tag:
        return tag.group(1).lower()
    head = before.lstrip(":* ")
    if head.startswith("{|"):
        return "table"
    if head.startswith("|-"):
        return "tr"
    if head.startswith(("|", "!")):
        return "cell"
    return "other"


def _parse_stop(token: str) -> tuple[str, float] | None:
    """色标 → (#rrggbb, 不透明度)；认不出返回 None。"""
    if token.lower() == "transparent":
        return "#000000", 0.0
    if token.startswith("#") and len(token) in (5, 9):
        alpha_hex = token[4:] if len(token) == 5 else token[7:]
        alpha = int(alpha_hex * (2 if len(alpha_hex) == 1 else 1), 16) / 255
        hex_ = to_hex(token[:4] if len(token) == 5 else token[:7])
        return (hex_, alpha) if hex_ else None
    hex_ = to_hex(token)
    return (hex_, 1.0) if hex_ else None


_STOP_WORDS = {
    *("to", "at", "circle", "ellipse", "closest", "farthest"),
    *("left", "right", "top", "bottom", "center", "side", "corner"),
    *("deg", "turn", "rad", "px", "em", "rem"),
}


def _gradient_stops(value: str) -> tuple[str, ...] | None:
    """纯渐变（可多层）里不透明色标的 #rrggbb；带图片、变量或认不出的颜色返回 None。"""
    if _GRADIENT.sub("", value).strip(" ,") or "var(" in value:
        return None
    stops = []
    for gradient in _GRADIENT.findall(value):
        inner = gradient.split("(", 1)[1]
        for token in _STOP_COLOR.findall(inner):
            if token.lower() in _STOP_WORDS:
                continue
            parsed = _parse_stop(token)
            if parsed is None:
                return None
            if parsed[1] > 0:
                stops.append(parsed[0])
    return tuple(stops) or None


def _decls(value: str) -> tuple[Decl | None, Decl | None]:
    background = color = None
    for match in _DECL.finditer(value):
        raw = match.group("value")
        body = re.sub(r"\s*!important\s*$", "", raw).strip()
        hex_ = None
        stops: tuple[str, ...] = ()
        if _SOLID.fullmatch(raw):
            hex_ = to_hex(body)
            if hex_ is None:
                continue
        elif match.group("prop") != "color" and (found := _gradient_stops(body)):
            stops = found
        else:
            continue  # 带图片的简写、变量、认不出的写法
        end = match.start("value") + raw.find(body) + len(body)
        tail = value[end:]
        decl = Decl(
            prop=match.group("prop"),
            value=body,
            hex=hex_,
            stops=stops,
            text=value[match.start() : end],
            start=not value[: match.start()].strip(),
            end=not tail.strip(),
            after=tail[:1] if tail.strip() else "",
        )
        if decl.prop == "color":
            color = decl
        else:
            background = decl
    return background, color


def inline_styles(wikitext: str) -> list[InlineStyle]:
    out = []
    for match in _STYLE_ATTR.finditer(wikitext):
        value = match.group(2)
        if "{{" in value or "}}" in value or "|" in value:
            continue  # 由参数 / 变量拼出来的，渲染结果不是这段原文
        background, color = _decls(value)
        if background or color:
            out.append(
                InlineStyle(_tag_at(wikitext, match.start()), value, background, color)
            )
    return out


def color_template_values(wikitext: str) -> list[str]:
    """``{{color|X|…}}`` 的 X（会输出 ``<span style="color:X;">``）。"""
    return [m.group(1) for m in _COLOR_TEMPLATE.finditer(wikitext)]


def font_template_values(wikitext: str) -> list[str]:
    """``{{Font|color=X|…}}`` 的 X。"""
    return [m.group(1) for m in _FONT_TEMPLATE.finditer(wikitext)]


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _match(decl: Decl, *, prefix: bool = True) -> list[str]:
    """匹配这条声明的属性选择器（带两侧分隔符）。"""
    body = decl.text
    if decl.start and decl.end:
        return [f"[style={_quote(body)} i]", f"[style={_quote(body + ';')} i]"]
    if decl.start:
        return [f"[style^={_quote(body + decl.after)} i]"]
    lead = [";", " ", "; "] if prefix else [""]
    if decl.end:
        return [f"[style$={_quote(p + body)} i]" for p in lead] + [
            f"[style*={_quote(p + body + ';')} i]" for p in lead
        ]
    return [f"[style*={_quote(p + body + decl.after)} i]" for p in lead]


def _serialized(decl: Decl) -> str | None:
    """脚本改过 style 之后浏览器序列化出来的写法（Chrome / Firefox 一致的那一段）。"""
    value = decl.value
    if re.search(r"#[0-9a-fA-F]{4}\b|#[0-9a-fA-F]{8}\b", value):
        return None  # 带透明度的写法序列化成 rgba(…)，小数位各浏览器不一
    value = re.sub(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b", _rgb, value)
    value = re.sub(r"\s*,\s*", ", ", value).lower()
    return f"[style*={_quote(f'{decl.prop}: {value}')}]"


def _rgb(match: re.Match[str]) -> str:
    red, green, blue = (round(c * 255) for c in parse_hex(match.group(0)))
    return f"rgb({red}, {green}, {blue})"


def _darken(decl: Decl) -> str:
    """底色声明值 → 暗色值。渐变逐个色标换，位置、角度、透明色标不动。"""
    if decl.hex:
        return dark_variant(decl.hex)

    def stop(match: re.Match[str]) -> str:
        parsed = _parse_stop(match.group(0))
        if parsed is None or parsed[1] == 0:
            return match.group(0)
        dark = dark_variant(parsed[0])
        token = match.group(0)
        if token.startswith("#") and len(token) in (5, 9):
            return dark + (token[-2:] if len(token) == 9 else token[-1] * 2)
        return dark

    out = []
    for gradient in _GRADIENT.findall(decl.value):
        name, inner = gradient.split("(", 1)
        out.append(name + "(" + _STOP_COLOR.sub(stop, inner))
    return ", ".join(out)


def _tag_selector(tag: str) -> str:
    return {"cell": ":is(td, th)", "other": ""}.get(tag, tag)


@dataclass
class PageRules:
    """推导结果：声明块 → 选择器，按声明块分组输出。"""

    blocks: dict[str, list[str]]

    def css(self) -> str:
        parts = []
        for body, selectors in self.blocks.items():
            unique = list(dict.fromkeys(selectors))
            parts.append(",\n".join(unique) + " {\n" + body + "\n}")
        return "\n".join(parts)


def _colors(decl: Decl) -> tuple[str, ...]:
    return (decl.hex,) if decl.hex else decl.stops


def _without_styles(text: str) -> str:
    """去掉页内样式正文（里面的属性选择器长得像 style="…"）。"""
    for start, end in reversed(style_spans(text)):
        text = text[:start] + text[end:]
    return text


def derive(sources: list[str], *, skip: frozenset[str] = frozenset()) -> PageRules:
    """从条目源码（含嵌入的子页面）推导 night 规则。

    ``skip`` 里的色值（小写 #rrggbb）不处理——页面里已经手写过暗色规则的。
    """
    blocks: dict[str, list[str]] = defaultdict(list)

    def add(body: str, selectors: list[str]) -> None:
        blocks[body].extend(f"{NIGHT_SCOPE} {s}" for s in selectors)

    bare = [_without_styles(text) for text in sources]
    styles = [s for text in bare for s in inline_styles(text)]

    # 浅色底：没写文字色的任何元素，或「面板」；面板换底色时，写了深色字的一并换成正文色
    seen: set[tuple[str, str, bool]] = set()
    for item in styles:
        bg = item.background
        if bg is None or skip.intersection(_colors(bg)):
            continue
        colors = _colors(bg)
        if bg.stops and min(to_oklch(c)[0] for c in bg.stops) < 0.75:
            # 渐变只换整体是浅色调的；有深色段的多是装饰或标题条，暗底上本来就成立
            continue
        if item.color is None:
            convert = all(contrast(DARK_TEXT, c) < 4.5 for c in colors)
        else:
            convert = item.tag in PANEL_TAGS and all(
                contrast(DARK_LINK, c) < 3 for c in colors
            )
        if not convert:
            continue
        recolor = item.color is not None and any(
            contrast(item.color.hex or DARK_TEXT, dark_variant(c)) < 4.5 for c in colors
        )
        key = (item.tag, bg.text + bg.after, recolor)
        if key in seen:
            continue
        seen.add(key)
        tag = _tag_selector(item.tag)
        selectors = [tag + m for m in _match(bg, prefix=False)]
        if item.tag in ("tr", "div") and (serialized := _serialized(bg)):
            selectors.append(tag + serialized)
        body = f"  background: {_darken(bg)} !important;"
        if recolor:
            body += f"\n  color: {DARK_TEXT} !important;"
        add(body, selectors)

    # 深色字：只认没写底色的元素（写了底色的是徽章，配色自洽）
    lifted: dict[str, list[str]] = defaultdict(list)
    for item in styles:
        fg = item.color
        if fg is None or fg.hex is None or item.background is not None:
            continue
        light = SEMANTIC_TEXT.get(fg.hex) or text_variant(fg.hex)
        if light == fg.hex or fg.hex in skip:
            continue
        tag = _tag_selector(item.tag)
        lifted[light] += [
            f'{tag}{m}:not([style*="background" i])' for m in _match(fg, prefix=True)
        ]
    for text in bare:
        for value in color_template_values(text):
            hex_ = to_hex(value)
            if hex_ is None or value.lower() in COLOR_TEMPLATE_HANDLED or hex_ in skip:
                continue
            light = text_variant(hex_)
            if light != hex_:
                lifted[light].append(f"span[style={_quote(f'color:{value};')} i]")
        for value in font_template_values(text):
            hex_ = to_hex(value)
            if hex_ is None or hex_ in skip:
                continue
            light = SEMANTIC_TEXT.get(hex_) or text_variant(hex_)
            if light == hex_:
                continue
            lifted[light] += [
                f"span[style^={_quote(f'color: {value};')} i]"
                ':not([style*="background" i])',
                f"span[style*={_quote(f' color: {value};')} i]"
                ':not([style*="background" i])',
            ]
    for light, selectors in lifted.items():
        add(f"  color: {light} !important;", selectors)

    # 页内 {{#widget:style}}：写了浅色底、没写文字色的类
    for text in sources:
        for start, end in style_spans(text):
            css = re.sub(
                r"/\* theme:begin.*?/\* theme:end [\w-]+ \*/",
                "",
                strip_generated(text[start:end]),
                flags=re.DOTALL,
            )
            for rule in parse_rules(css):
                if rule.context or any("skin-theme" in s for s in rule.selectors):
                    continue
                bg, fg = _decls(" ".join(rule.body.split()))
                if bg is None or bg.hex is None or fg is not None or bg.hex in skip:
                    continue  # 页内样式只管纯色底；渐变多是分隔线之类的装饰
                if contrast(DARK_TEXT, bg.hex) >= 4.5:
                    continue
                body = f"  background: {_darken(bg)};"
                blocks[body].extend(f"html.{NIGHT} {s}" for s in rule.selectors)
    return PageRules(dict(blocks))


_TABLE_START = re.compile(r"^([:*]*\s*\{\|)(.*)$", re.MULTILINE)
_COLOR_BASE_LIGHT = re.compile(
    r"--color-base\s*:\s*(?:white|#fff|#ffffff)\s*(?:;|$)", re.IGNORECASE
)


def mark_dark_tables(text: str) -> str | None:
    """深色底的 wikitable 挂上 ``prts-table-dark``（Common.css：白字、表头跟随）。

    Vector 下这些表格靠 ``--color-base:white`` 或表格上的 ``color:white`` 变白字；
    皮肤 tables.css 直接给 ``.wikitable`` 和表头上 ``var(--ak-fg)``，浅色下深底深字。
    认这几种：写了 ``--color-base:white``；深色底且没写文字色或写的是白字。
    """

    def fix(match: re.Match[str]) -> str:
        attrs = match.group(2)
        style = re.search(r'style\s*=\s*"([^"]*)"', attrs)
        cls = re.search(r'class\s*=\s*"([^"]*)"', attrs)
        if not style or not cls or "prts-table-dark" in cls.group(1).split():
            return match.group(0)
        if "wikitable" not in cls.group(1).split():
            return match.group(0)
        background, color = _decls(style.group(1))
        dark_bg = (
            background is not None
            and background.hex is not None
            and contrast("#1d1f20", background.hex) < 3
        )
        white_text = color is not None and color.hex in ("#ffffff", "#f8f9fa")
        base = _COLOR_BASE_LIGHT.search(style.group(1))
        if not (base or (dark_bg and (color is None or white_text))):
            return match.group(0)
        end = cls.end(1)
        return match.group(1) + attrs[:end] + " prts-table-dark" + attrs[end:]

    new = _TABLE_START.sub(fix, text)
    return None if new == text else new
