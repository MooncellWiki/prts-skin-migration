"""从浅色值推暗色值。

站内模板的配色都是按浅色画布设计的：navbox 的三级蓝、各种浅色底色条。
暗色下逐个拍脑袋定色值，做出来的东西彼此不成套
（Vector 时期的暗色规则就是这样：同一级蓝在不同模板里是三四种颜色）。
这里给一条统一的规则，在 OKLCH 空间里算：

- **色相不变**，一眼还能认出是「那一级蓝 / 那种红」
- **浅色调**（浅色下配深色字的底色，如 ``#85c1f7``）：按它离白有多远，
  映射到离皮肤暗色表面 ``#1a1b1c`` 多远。暗色下人眼对亮度差更不敏感，
  所以用幂函数放大小差距、压缩大差距——浅色下 ``#fdfdfd`` 与 ``#f7f7f7`` 只差 0.02，
  暗色下要差 0.04 才看得出来（皮肤自己的 surface / surface-2 就是这个间距）
- **深色调**（浅色下就配白字的底色，如 ``#4487df``）：亮度压到 0.46 以下，保证白字对比度
- **中性色**（几乎无彩度）直接吸附到皮肤的暗色表面令牌，和页面其余部分一致
- 彩度打八五折，暗底上高彩度的颜色会「发光」

结果都要过对比度校验：正文色 ``#f0f0f0`` 对底色至少 4.5:1。
"""

import math

# 皮肤（mediawiki-skins-Arknights tokens.css）暗色令牌
DARK_SURFACES = ("#1a1b1c", "#232425", "#2d2e30")  # surface / surface-2 / surface-3
DARK_TEXT = "#f0f0f0"
DARK_LINK = "#5ddcff"

_TINT_GAIN = 0.44
_TINT_GAMMA = 0.65
_STRONG_MAX_L = 0.46
_CHROMA_FACTOR = 0.85
_CHROMA_MAX = 0.13
_NEUTRAL_CHROMA = 0.005


def parse_hex(value: str) -> tuple[float, float, float]:
    """``#abc`` / ``#aabbcc`` → sRGB 0–1。"""
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(char * 2 for char in text)
    if len(text) != 6:
        raise ValueError(f"不是 #rgb / #rrggbb：{value!r}")
    red, green, blue = (int(text[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return red, green, blue


def to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(min(1.0, max(0.0, c)) * 255):02x}" for c in rgb)


def _linear(channel: float) -> float:
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def _gamma(channel: float) -> float:
    if channel <= 0.0031308:
        return 12.92 * channel
    return 1.055 * channel ** (1 / 2.4) - 0.055


def to_oklch(value: str) -> tuple[float, float, float]:
    """→ (L 0–1, C, h 角度)。"""
    red, green, blue = (_linear(c) for c in parse_hex(value))
    long_ = 0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue
    medium = 0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue
    short = 0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue
    long_, medium, short = (
        math.copysign(abs(x) ** (1 / 3), x) for x in (long_, medium, short)
    )
    lightness = 0.2104542553 * long_ + 0.7936177850 * medium - 0.0040720468 * short
    a = 1.9779984951 * long_ - 2.4285922050 * medium + 0.4505937099 * short
    b = 0.0259040371 * long_ + 0.7827717662 * medium - 0.8086757660 * short
    return lightness, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def from_oklch(lightness: float, chroma: float, hue: float) -> str:
    """超出 sRGB 色域时逐步降彩度，直到落回色域内。"""
    while True:
        a = chroma * math.cos(math.radians(hue))
        b = chroma * math.sin(math.radians(hue))
        long_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
        medium = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
        short = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
        rgb = (
            4.0767416621 * long_ - 3.3077115913 * medium + 0.2309699292 * short,
            -1.2684380046 * long_ + 2.6097574011 * medium - 0.3413193965 * short,
            -0.0041960863 * long_ - 0.7034186147 * medium + 1.7076147010 * short,
        )
        if all(-1e-4 <= c <= 1 + 1e-4 for c in rgb) or chroma < 1e-4:
            return to_hex(tuple(_gamma(max(0.0, c)) for c in rgb))  # type: ignore[arg-type]
        chroma *= 0.97


def luminance(value: str) -> float:
    red, green, blue = (_linear(c) for c in parse_hex(value))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(first: str, second: str) -> float:
    """WCAG 2 对比度。"""
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def dark_variant(light: str, *, strong: bool | None = None) -> str:
    """浅色底色 → 暗色底色。

    ``strong`` 表示浅色下这块底配的是白字（深色调）。
    不传时按亮度猜：OKLCH 亮度低于 0.7 算深色调。
    """
    lightness, chroma, hue = to_oklch(light)
    if strong is None:
        strong = lightness < 0.7
    new_chroma = min(chroma * _CHROMA_FACTOR, _CHROMA_MAX)
    if strong:
        return from_oklch(min(lightness, _STRONG_MAX_L), new_chroma, hue)
    surface = to_oklch(DARK_SURFACES[0])[0]
    new_lightness = surface + _TINT_GAIN * max(0.0, 1 - lightness) ** _TINT_GAMMA
    surfaces = {s: to_oklch(s)[0] for s in DARK_SURFACES}
    if chroma < _NEUTRAL_CHROMA and new_lightness <= max(surfaces.values()) + 0.02:
        return min(surfaces, key=lambda s: abs(surfaces[s] - new_lightness))
    return from_oklch(new_lightness, new_chroma, hue)
