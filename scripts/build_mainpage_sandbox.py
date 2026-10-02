"""把 prts-design 的首页设计稿转成现网可用的 wikitext + 微件。

设计稿是一份静态 HTML，搬进 MediaWiki 要过几道坎：

1. **CSS 不能走 TemplateStyles**——TemplateStyles 的净化器不认自定义属性定义，``var()`` 进了
   简写 / ``calc()`` 也不认：设计稿 37 KB 灌进去被拒 122 处、只剩 21 KB，被丢的正是 hero
   局部重映射令牌那套核心手法。所以样式走微件（原始 ``<style>``，无净化器），
   和现网 ``微件:Mpstyle`` 同一条路。
2. **``<a>`` 不在 wikitext 白名单里**，写不出 ``<a class>``——设计稿已经照
   wikitext 的样子写：整块可点的格子是「带类名的容器（``.mp-a``）+ 里面一条
   不带类名的 ``<a>``」，这里只把 ``<a>`` 换成 wikitext 真链接。链接怎么铺满容器、
   为什么不能用 ``display: contents``（拖不出链接），见设计稿 ``.mp-a`` 那段样式。
3. **内联 ``<svg><use>`` 会被转义**——图标转成 CSS ``mask-image`` 类，
   与皮肤自己的 ``.ak-icon``（OOUI 图标包）同一机制，颜色照样跟 ``currentColor``。
4. **``<input>`` 会被转义**——设计稿那个「演示：特别开放周」开关只在预览里有，去掉。

页面上的内容全部由 ``/sandbox`` 模板产出（见 ``SLOTS``）；手写的模板在
``migration/mainpage/templates/``，这里只生成页面、微件和 ``模板:行动日历/sandbox``。

用法::

    uv run python scripts/build_mainpage_sandbox.py --design ../prts-design --out build/
    uv run python scripts/mainpage_sandbox_apply.py -c config.sandbox.toml   # 再推到沙箱
"""

import argparse
import json
import re
import urllib.parse
from pathlib import Path

import click

# 设计稿的本地素材 → 现网已有的文件。已核对存在性；未列出的沿用同类替身，
# 属于 stage B 要收尾的部分（稀有度 / 家具 / 时装头像的命名还没对上）。
ASSET_MAP = {
    "assets/profession/icon_warrior.png": "图标 职业 近卫.png",
    "assets/profession/icon_tank.png": "图标 职业 重装.png",
    "assets/profession/icon_special.png": "图标 职业 特种.png",
    "assets/profession/icon_caster.png": "图标 职业 术师.png",
    "assets/profession/icon_pioneer.png": "图标 职业 先锋.png",
    "assets/profession/icon_sniper.png": "图标 职业 狙击.png",
    "assets/mainpage/avatar/haimo.png": "头像 海沫.png",
    "assets/mainpage/avatar/shanbi.png": "头像 珊比.png",
    "assets/mainpage/avatar/shanbi-2.png": "头像 珊比.png",
    "assets/mainpage/avatar/shixi.png": "头像 时隙.png",
    "assets/mainpage/avatar/shixi-2.png": "头像 时隙.png",
    "assets/mainpage/avatar/jiaxinta.png": "头像 嘉辛塔.png",
    "assets/mainpage/avatar/jiaxinta-2.png": "头像 嘉辛塔.png",
    "assets/mainpage/avatar/logos.png": "头像 逻各斯.png",
    "assets/mainpage/avatar/xiaoge.png": "头像 晓歌.png",
    "assets/mainpage/avatar/angelina-wish.png": "头像 予愿安洁莉娜.png",
    "assets/mainpage/avatar/fiammetta-2.png": "头像 菲亚梅塔.png",
    "assets/mainpage/avatar/gavial-alter-2.png": "头像 百炼嘉维尔.png",
    "assets/mainpage/avatar/songtong-skin1.png": "头像 松桐.png",
    "assets/item/2004.png": "道具 高级作战记录.png",
    "assets/item/3303.png": "道具 技巧概要·卷3.png",
    "assets/item/4001.png": "道具 龙门币.png",
    "assets/item/4006.png": "道具 采购凭证.png",
    "assets/item/3223.png": "道具 近卫芯片.png",
    "assets/item/3233.png": "道具 重装芯片.png",
    "assets/item/3213.png": "道具 先锋芯片.png",
    "assets/item/3243.png": "道具 狙击芯片.png",
    "assets/mainpage/item-3113.png": "道具 碳素.png",
    "assets/mainpage/module/prp-x.png": "模组类型 PRP-X 小图.png",
    "assets/mainpage/module/bea-x.png": "模组类型 BEA-X 小图.png",
    "assets/mainpage/module/fun-x.png": "模组类型 FUN-X 小图.png",
    "assets/mainpage/module/isw-a.png": "模组类型 ISW-A 小图.png",
    "assets/mainpage/module/ra-a.png": "模组类型 RA-A 小图.png",
    "assets/rarity/rarity_yellow_2.png": "稀有度 黄 2.png",
    "assets/rarity/rarity_yellow_3.png": "稀有度 黄 3.png",
    "assets/rarity/rarity_yellow_4.png": "稀有度 黄 4.png",
    "assets/rarity/rarity_yellow_5.png": "稀有度 黄 5.png",
    "assets/mainpage/avatar/yunji-skin1.png": "头像 云迹.png",
    "assets/mainpage/banner-is6.jpg": "主题图 沉沦者的黑流树海.png",
    "assets/mainpage/banner-gacha-rotate191.jpg": "干员轮换卡池191.png",
}
# 现网还没有对应文件的素材（活动横幅 / 家具图），直接引设计稿的 GitHub Pages。
# 这样还原度是满的，也不用往现网塞一堆临时文件；stage B 换成正式的 File: 页。
DESIGN_SITE = "https://mooncellwiki.github.io/prts-design/"

ANCHOR = re.compile(r"<a\s+([^>]*?)>(.*?)</a>", re.DOTALL)
BUTTON_OPEN = re.compile(r"<button\s+([^>]*?)>")
BUTTON_CLOSE = re.compile(r"</button>")
TYPE_ATTR = re.compile(r'\s*\btype="[^"]*"')
NAV_TILE = re.compile(
    r'<div class="mp-nav__tile mp-a"><a href="[^"]*"><img class="mp-nav__icon" '
    r'src="assets/mainpage/nav/([a-z]+)\.png"[^>]*>'
    r'<span class="mp-nav__zh">([^<]*)</span><span class="mp-nav__en">([^<]*)</span>'
    r"</a></div>"
)
# wikitext 的 HTML 白名单里没有 <nav>，换成 <div> 保留类名
NAV_TAG = re.compile(r"<(/?)nav\b")
# <section> 在白名单里，但装了 Labeled Section Transclusion 的站点上它是 LST 的标签：
# 沙箱实测整段连内容一起被吞掉。换成 <div role="region">，语义不丢。
SECTION_OPEN = re.compile(r"<section\b")
SECTION_CLOSE = re.compile(r"</section>")
# 正文里残留的 sprite 定义块与 <script>：图标已转 CSS mask，脚本已在微件里
SPRITE_BLOCK = re.compile(r"<svg[^>]*>\s*(?:<symbol.*?</symbol>\s*)+</svg>", re.DOTALL)
SCRIPT_BLOCK = re.compile(r"<script\b.*?</script>", re.DOTALL)
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
# 页尾那条「首页设计稿——信息结构 1:1 取自…」是给看设计稿的人的说明，不是首页的内容
DESIGN_NOTE = re.compile(
    r'<div class="ak-message[^"]*"[^>]*><div class="ak-message__body"><b>首页设计稿</b>'
    r".*?</div></div>",
    re.DOTALL,
)
HREF = re.compile(r'\s*\bhref="([^"]*)"')
# 链接所在的格子：设计稿里 .mp-a 容器的开标签后面紧跟着 <a>
CONTAINER = re.compile(r'<(?:div|span)\s[^>]*\bclass="([^"]*)"[^>]*>$')
TAGS = re.compile(r"<[^>]+>")
LABEL = re.compile(r'mp-label">([^<]+)<')
# 行首是这些就不会被 MediaWiki 当成段落；其余的行并到上一行去（见 convert_body）
BLOCK_LINE = re.compile(r"</?(?:div|ul|ol|li|h[1-6]|table|p)\b|\{\{|<!--")

# 设计稿里的 href 全是 "#"。留在页面上的静态链接按文字对回现网的目标
# （取自现网 首页 的 wikitext）；其余链接都在模板里，由数据决定。
LINKS = {
    "干员一览": "干员一览",
    "最近更改": "特殊:最近更改",
    "B站充电": "PRTS:如何帮助我们完善网站#B站充电计划",
    "微信打赏": "PRTS:如何帮助我们完善网站#直接的经济资助",
    "支付宝打赏": "PRTS:如何帮助我们完善网站#直接的经济资助",
    "PRTS:交流群组": "PRTS:交流群组",
    "PRTS:收支一览": "PRTS:收支一览",
    "PRTS:如何帮助我们完善网站": "PRTS:如何帮助我们完善网站",
    "PRTS:授权一览": "PRTS:授权一览",
}
# 资源收集的卡按所在分组（.mp-label）链到 关卡一览/资源收集 的对应章节，同现网 模板:行动日历
RES_PAGE = "关卡一览/资源收集"

SVG_USE = re.compile(
    r'<svg class="([^"]*)"[^>]*>\s*<use href="#(i-[a-z0-9-]+)"\s*/?>\s*</svg>'
)
SWITCH = re.compile(r'<label class="ak-switch[^"]*"[^>]*>.*?</label>', re.DOTALL)
IMG_SRC = re.compile(r'src="(assets/[^"]+)"')


# 页面里这些容器的内容改由模板产出：容器保留（样式挂在它身上），内容换成模板调用。
# 键是容器开标签的正则，值是 (标签名, 换进去的 wikitext)。
INLINE_SLOTS = {
    r'<div class="swiper-wrapper">': ("div", "{{首页轮播/sandbox|mode=slide}}"),
    r'<ol class="mp-hero__list"[^>]*>': ("ol", "{{首页轮播/sandbox|mode=item}}"),
    r'<ul class="mp-events">': ("ul", "{{:首页/网页活动}}"),
    r'<ul class="mp-notes">': ("ul", "{{当前信息/sandbox}}"),
    r'<div class="mp-ops">': ("div", "{{:首页/亮点干员/sandbox}}"),
    # 近期新增的三个数据页由 BotPtilopsis 直接按新格式写，sandbox 与真首页读同一份
    r'<div class="ak-panel__body mp-stages">': ("div", "{{:首页/新增关卡}}"),
    # 标签用 <div>：单独成行的 <span> 会被 MediaWiki 套进 <p>
    r'<div class="ak-panel__body">': (
        "div",
        '<div class="ak-overline mp-label">主题</div>\n'
        "{{:首页/新增主题}}\n"
        '<div class="ak-overline mp-label ak-mt-4">单件</div>\n'
        "{{:首页/新增单件}}",
    ),
}
# 这些容器**连自己带内容**整块搬进模板，页面上只留一句调用。
EXTRACT_SLOTS = {
    r'<div class="mp-today__res"[^>]*>': (
        "div",
        "行动日历/sandbox",
        "模板_行动日历_sandbox.wiki",
    ),
}
# 没有内容时整块不输出的容器：(容器开标签的正则, 标签名, 判空用的 wikitext)。
# 设计稿：没有网页活动 / 补充说明时不留空壳，也不显示「暂无」。
OPTIONAL_BLOCKS = [
    (r'<div class="mp-hero__events">', "div", "{{:首页/网页活动}}"),
    (r'<div class="mp-today__notes">', "div", "{{当前信息/sandbox}}"),
]

# 12 个入口：雪碧图坐标与链接取自现网 首页 的 {{mpbutton|posx=|posy=|link=}}。
# 雪碧图 5 列 × 3 行；设计稿里的图标文件名 → (posx, posy, 链接)。
NAV = {
    "operators": (1, 1, "干员一览"),
    "enemies": (2, 1, "敌人一览"),
    "operations": (3, 1, "关卡一览"),
    "events": (4, 1, "活动一览"),
    "depot": (5, 1, "道具一览"),
    "recruit": (1, 2, "公招计算"),
    "headhunts": (2, 2, "卡池一览"),
    "logistics": (4, 2, "后勤技能一览"),
    "store": (5, 2, "采购中心"),
    "outfits": (1, 3, "时装回廊"),
    "stories": (2, 3, "剧情一览"),
    "furniture": (3, 3, "家具一览"),
}


def _match_close(text: str, start: int, tag: str) -> int:
    """从开标签结束处往后找配对的闭标签，返回闭标签的起始下标。"""
    depth = 1
    pos = start
    pattern = re.compile(rf"<(/?){tag}\b", re.IGNORECASE)
    while depth:
        m = pattern.search(text, pos)
        if not m:
            raise SystemExit(f"找不到 <{tag}> 的配对闭标签，设计稿结构可能变了")
        depth += -1 if m.group(1) else 1
        pos = m.end()
    return text.rfind("<", 0, pos)


def _find(pattern: str, body: str) -> re.Match[str]:
    m = re.search(pattern, body)
    if not m:
        raise SystemExit(f"设计稿里找不到容器 {pattern}")
    return m


def apply_slots(body: str) -> tuple[str, dict[str, str]]:
    """把静态内容换成模板调用；需要整块搬走的同时返回模板正文。"""
    extracted: dict[str, str] = {}
    for pattern, (tag, call) in INLINE_SLOTS.items():
        m = _find(pattern, body)
        close = _match_close(body, m.end(), tag)
        body = body[: m.end()] + "\n" + call + "\n" + body[close:]
    for pattern, (tag, call, filename) in EXTRACT_SLOTS.items():
        m = _find(pattern, body)
        close = _match_close(body, m.end(), tag)
        end = body.index(">", body.index(f"</{tag}", close)) + 1
        extracted[filename] = body[m.start() : end]
        body = body[: m.start()] + "{{" + call + "}}" + body[end:]
    return body, extracted


def apply_nav(body: str) -> str:
    """12 个入口换成 {{Mpbutton/sandbox}} 调用，参数与现网 {{mpbutton}} 一致。"""

    def call(m: re.Match[str]) -> str:
        icon, zh, en = m.groups()
        if icon not in NAV:
            raise SystemExit(f"入口图标 {icon} 没有对应的雪碧图坐标 / 链接")
        x, y, link = NAV[icon]
        return (
            f"{{{{Mpbutton/sandbox|posx={x}|posy={y}"
            f"|label={zh}|enlabel={en}|link={link}}}}}"
        )

    body, n = NAV_TILE.subn(call, body)
    if n != len(NAV):
        raise SystemExit(f"入口应有 {len(NAV)} 个，设计稿里认出 {n} 个")
    return body


def wrap_optional(body: str) -> str:
    """内容为空就整块不输出：{{#if:判空|整块}}。"""
    for pattern, tag, probe in OPTIONAL_BLOCKS:
        m = _find(pattern, body)
        close = _match_close(body, m.end(), tag)
        end = body.index(">", close) + 1
        block = body[m.start() : end]
        if "|" in TAGS.sub("", block.replace(probe, "")):
            raise SystemExit(f"{pattern} 里有竖线，包进 #if 会被切开")
        body = body[: m.start()] + "{{#if:" + probe + "|" + block + "}}" + body[end:]
    return body


def extract(design: Path) -> tuple[str, str, str]:
    """从设计稿里取出 <style> / 正文 / 内联 <script>。"""
    src = (design / "preview/_src/pages/home.html").read_text(encoding="utf-8")
    style = src.split("<style>", 1)[1].split("</style>", 1)[0]
    body = src.split("</style>", 1)[1]
    body = body.split("-->", 1)[1] if body.lstrip().startswith("-->") else body
    built = (design / "preview/home.html").read_text(encoding="utf-8")
    script = re.findall(
        r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", built, re.DOTALL
    )[-1]
    return style, body.strip(), script


def strip_preview_patch(style: str) -> str:
    """去掉「0. 页面级」那段。

    它是预览骨架的补丁，真皮肤已在 .ak-layout--mainpage 里做过。
    """
    start = style.find("/* ── 0. 页面级")
    end = style.find("/* ── 1. 通用 ──")
    if start == -1 or end == -1:
        raise SystemExit("设计稿结构变了：找不到「0. 页面级」段，请检查后再跑")
    return style[:start] + style[end:]


def icon_css(design: Path, needed: set[str]) -> str:
    """描边图标 → mask-image 类。

    currentColor 换成实色，可见颜色由 background-color 提供。
    """
    built = (design / "preview/home.html").read_text(encoding="utf-8")
    syms = dict(
        re.findall(r'<symbol id="(i-[a-z0-9-]+)"[^>]*>(.*?)</symbol>', built, re.DOTALL)
    )
    boxes = dict(
        re.findall(r'<symbol id="(i-[a-z0-9-]+)"[^>]*viewBox="([^"]+)"', built)
    )
    missing = needed - syms.keys()
    if missing:
        raise SystemExit(f"设计稿里找不到这些图标：{sorted(missing)}")
    lines = [
        "",
        "/* ── 图标：设计稿的 <svg><use> 在 wikitext 里会被转义，改成 mask-image；",
        " *    与皮肤 .ak-icon（OOUI 图标包）同一机制，颜色仍走 currentColor ── */",
        ".mp-i{display:inline-block;-webkit-mask-repeat:no-repeat;mask-repeat:no-repeat;"
        "-webkit-mask-position:center;mask-position:center;"
        "-webkit-mask-size:contain;mask-size:contain;background-color:currentColor}",
    ]
    for name in sorted(needed):
        inner = re.sub(r"\s+", " ", syms[name]).strip().replace("currentColor", "#000")
        box = boxes.get(name, "0 0 24 24")
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{box}">{inner}</svg>'
        lines.append(
            f'.mp-i--{name[2:]}{{-webkit-mask-image:url("data:image/svg+xml,{urllib.parse.quote(svg)}");'
            f'mask-image:url("data:image/svg+xml,{urllib.parse.quote(svg)}")}}'
        )
    return "\n".join(lines) + "\n"


def convert_body(body: str) -> tuple[str, set[str], list[str], int]:
    """正文 HTML → wikitext 能活下来的形式。"""
    icons: set[str] = set()

    def swap_icon(m: re.Match[str]) -> str:
        icons.add(m.group(2))
        return f'<span class="{m.group(1)} mp-i mp-i--{m.group(2)[2:]}"></span>'

    body = SPRITE_BLOCK.sub("", body)  # 图标已转 CSS mask，sprite 不需要了
    body = SCRIPT_BLOCK.sub("", body)  # 脚本归微件
    body = COMMENT.sub("", body)  # 设计稿的说明留在设计稿里，不进页面
    body = DESIGN_NOTE.sub("", body)
    body = SVG_USE.sub(swap_icon, body)
    body = NAV_TAG.sub(r"<\1div", body)
    body = SECTION_OPEN.sub('<div role="region"', body)
    body = SECTION_CLOSE.sub("</div>", body)
    body = SWITCH.sub("", body)  # <input> 会被转义，且这开关只在预览里有

    # <button> 不在 wikitext 白名单里，转 span（脚本按 id 绑定，不受影响）
    body = BUTTON_OPEN.sub(
        lambda m: (
            f'<span role="button" tabindex="0" {TYPE_ATTR.sub("", m.group(1)).strip()}>'
        ),
        body,
    )
    body = BUTTON_CLOSE.sub("</span>", body)

    # wikitext 不放行裸 <a>：一律换成 [[目标|内容]]。整块可点的格子设计稿已经写成
    # 「.mp-a 容器 + 不带类名的 <a>」，容器原样留着（样式、脚本都按类名找它）。
    anchors = 0

    def swap_anchor(m: re.Match[str]) -> str:
        nonlocal anchors
        anchors += 1
        attrs, inner = m.group(1), m.group(2)
        if HREF.sub("", " " + attrs).strip():
            raise SystemExit(
                f"设计稿里的 <a {attrs}> 带了 href 以外的属性，wikitext 写不出来："
                "类名 / data-* 挂到外面的 .mp-a 容器上"
            )
        box = CONTAINER.search(body, 0, m.start())
        names = box.group(1).split() if box else []
        text = TAGS.sub("", inner).strip()
        if "mp-res" in names:
            label = LABEL.findall(body[: m.start()])
            target = f"{RES_PAGE}#{label[-1]}" if label else RES_PAGE
        elif text in LINKS:
            target = LINKS[text]
        else:
            raise SystemExit(f"链接「{text}」没有对应的目标页面，请补进 LINKS")
        return f"[[{target}|{inner}]]"

    body = ANCHOR.sub(swap_anchor, body)

    unmapped: list[str] = []

    def swap_img(m: re.Match[str]) -> str:
        asset = m.group(1)
        target = ASSET_MAP.get(asset)
        if target is None:
            unmapped.append(asset)
            return f'src="{DESIGN_SITE}{asset}"'
        return 'src="{{filepath:' + target + '}}"'

    body = IMG_SRC.sub(swap_img, body)

    # wikitext 里行首空格 = 预格式化块，空行 = 空 <p>。设计稿的 HTML 是带缩进的漂亮排版，
    # 逐行去掉行首缩进与空行。行首不是块级标签的行（单独成行的 <span> 之类）会被套进 <p>，
    # 并到上一行去——上一行有块级标签，MediaWiki 就不再给这一行起段落。
    lines: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if lines and not BLOCK_LINE.match(line):
            lines[-1] += line
        else:
            lines.append(line)
    return "\n".join(lines), icons, sorted(set(unmapped)), anchors


def nav_sprite_css() -> str:
    """12 个入口图标：现网雪碧图，坐标由 {{Mpbutton/sandbox}} 按百分比写在行内。"""
    return """
/* ── 入口图标：沿用现网那张 5 列 × 3 行的雪碧图。background-size / -position 都用百分比，
 *    图标多大都对得上（手机上是 40px），不需要现网 微件:Mpbutton 那段缩放脚本 ── */
.mp-nav__icon{display:block;background:url(https://static.prts.wiki/Mpbuttons.4DCFB205.png) no-repeat;background-size:500% 300%}
@media (max-width:639px){.mp-nav__tile .mp-nav__icon{width:40px;height:40px}}
"""


# 设计稿的补充说明栏只有一种样式（G7）：「服务器维护中」和「资质凭证刷新」长得一模一样。
# 这里补出 danger / warning 两档，作为 G7 那条建议的可运行示例。
# MediaWiki 把模板输出的 <h4> 包进 <div class="mw-heading">，那层自带正文标题的外边距与
# flex 布局。让它不出盒子，标题就还是按设计稿的规则排（选择器另由 patch_heading_selectors 补）。
HEADING_SHIM = """
/* ── MediaWiki 给标题套的 .mw-heading：不出盒子，标题按设计稿自己的规则排 ── */
.mp .mw-heading{display:contents}
"""

NOTES_SHIM = """
/* ── 补充说明的轻重分档（设计稿缺，见迁移盘点 G7） ── */
.mp-notes li.is-danger .ak-icon{background-color:var(--ak-red-500)}
.mp-notes li.is-danger b{color:var(--ak-red-500)}
.mp-notes li.is-warning .ak-icon{background-color:var(--ak-yellow-500)}
"""

# 设计稿的模组图标是剥掉光晕、裁到字形外接框的素材（~38×38），
# 现网 模组类型_*_小图.png 是 68×50 原图，字形只占中间 ~32×31（各型号同一画布），
# 照设计稿的 max-width 缩下去字形只剩 ~9px。这里把原图放大到字形 ~22px，
# 居中压进 .mp-mod，四周的光晕由它的 overflow: hidden 裁掉。
MOD_SHIM = """
/* ── 模组图标：现网是带光晕的 68×50 原图（设计稿用的是裁好的），
 *    放大居中，光晕裁在框外 ── */
.mp-mod img{position:absolute;left:50%;top:50%;width:48px;height:auto;
max-width:none;max-height:none;transform:translate(-50%,-50%)}
"""

# Swiper 在 static.prts.wiki 的 npm 镜像上（prts-static 桶 npm/swiper@版本/，与 npm 包根目录同构）。
# 升级时先用 ossutil 传新版本的 swiper-bundle.min.{js,css,js.map}，再改这里。
SWIPER = "https://static.prts.wiki/npm/swiper@11.2.10/"

HOST_SHIM = """
/* ── 非 Arknights 皮肤（Vector / Minerva）：令牌与组件样式由脚本动态加载，到位前先藏住，免得闪一下没样式的版面。
 *    脚本没跑起来时 3 秒后照常显示；无 JS 的访客（没有 .client-js）不藏 ── */
.client-js body:not(.skin-arknights) .mp:not(.is-ready){visibility:hidden;animation:mp-host-reveal 0s 3s forwards}
@keyframes mp-host-reveal{to{visibility:visible}}
"""

# 非 Arknights 皮肤上，设计稿要的令牌 / 组件 / 字体由皮肤自己的 skins.arknights.components、
# skins.arknights.fonts 用 JS 加载，同 prts-widgets 的 CharList / VoiceTable（Arknights 皮肤已全套加载，
# 不用再要），.mp 加 .ak-scope 当作用域根。
# 走 RLQ 的数组形式：函数形式由 startup 立即执行，那时 mediawiki.base 还没就绪、没有 mw.loader.using；
# 数组形式由 mediawiki.base 就绪后 using 指定模块再回调。
HOST_SCRIPT = """
(function () {
  if (document.body.classList.contains('skin-arknights')) { return; }
  /* tokens.css 在 <html> 不带 skin-theme-clientpref-* 时跟随系统明暗。旧 Vector / Minerva 不输出这组类、页面恒为亮色，
     系统暗色下首页会变成亮页面里的一块黑，所以钉成亮色。hero 的黑白两版也是按 :root 判的，只能钉在 <html> 上 */
  var root = document.documentElement;
  if (!/(^|\\s)skin-theme-clientpref-/.test(root.className)) { root.setAttribute('data-theme', 'light'); }
  (window.RLQ = window.RLQ || []).push([['skins.arknights.components', 'skins.arknights.fonts'], function () {
    $(function () { $('.mp').addClass('ak-scope is-ready'); });
  }]);
})();
"""

KEY_SHIM = """
/* <button> 在 wikitext 里写不出来，转成了 span[role=button]，回车 / 空格要自己接。
   上一张 / 下一张由 Swiper 的 a11y 模块接，这里只管暂停键。 */
(function () {
  var btn = document.getElementById('mp-hero-pause');
  if (!btn) { return; }
  btn.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); btn.click(); }
  });
})();
"""


HEADING_CHILD = re.compile(r"(>\s*)(h[1-6])\b")


def patch_heading_selectors(style: str) -> tuple[str, int]:
    """MediaWiki 会把 HTML 标题包进 <div class="mw-heading">，直接子选择器会失配。"""
    out, patched = [], 0
    for line in style.splitlines():
        head = line.split("{", 1)[0]
        if "{" in line and HEADING_CHILD.search(head):
            sels = [x.strip() for x in head.split(",")]
            extra = [
                HEADING_CHILD.sub(r"\1.mw-heading > \2", x)
                for x in sels
                if HEADING_CHILD.search(x)
            ]
            line = ", ".join(dict.fromkeys(sels + extra)) + "{" + line.split("{", 1)[1]
            patched += len(extra)
        out.append(line)
    return "\n".join(out), patched


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", type=Path, default=Path("../prts-design"))
    ap.add_argument("--out", type=Path, default=Path("build"))
    args = ap.parse_args()

    style, body, script = extract(args.design)
    # 图标要在切槽之前收集：内容搬进模板后，页面上找不到它们了，
    # 但模板仍然在用这些 mp-i--* 类，mask 必须照常生成。
    all_icons = {m.group(2) for m in SVG_USE.finditer(body)}
    body = apply_nav(body)
    body, extracted = apply_slots(body)
    body = wrap_optional(body)
    body, icons, unmapped, anchors = convert_body(body)
    style, headings = patch_heading_selectors(strip_preview_patch(style))
    style = (
        style
        + icon_css(args.design, all_icons | icons)
        + nav_sprite_css()
        + HEADING_SHIM
        + NOTES_SHIM
        + MOD_SHIM
        + HOST_SHIM
    )

    widget = (
        "<!-- 新皮肤首页（首页 与 首页/sandbox 共用）的样式与脚本。生成物，别手改——改 prts-design 后重跑\n"
        "     prts-skin-migration/scripts/build_mainpage_sandbox.py。\n"
        "     样式没走 TemplateStyles 是因为它的净化器不认自定义属性定义，\n"
        "     设计稿灌进去会被丢掉四成（含 hero 局部重映射令牌那套核心手法）。 -->\n"
        f"<style>\n{style}</style>\n"
        f'<link rel="stylesheet" href="{SWIPER}swiper-bundle.min.css">\n'
        # defer：不挡正文解析，且保证在 DOMContentLoaded 之前执行完，下面的脚本照样拿得到 Swiper
        f'<script defer src="{SWIPER}swiper-bundle.min.js"></script>\n'
        f"<script>{HOST_SCRIPT}</script>\n"
        "<script>\n"
        "/* 微件在页面最顶部，脚本跑时正文 DOM 还不存在\n"
        "   （设计稿预览里脚本在 body 末尾），推迟到 DOMContentLoaded。 */\n"
        "(function (run) {\n"
        "  if (document.readyState === 'loading') {\n"
        "    document.addEventListener('DOMContentLoaded', run);\n"
        "  } else { run(); }\n"
        "})(function () {\n"
        f"{script}\n{KEY_SHIM}\n"
        "});\n"
        "</script>\n"
    )

    page = (
        "{{#Widget:Mpstyle/newskin}}<!--\n"
        "  新皮肤首页 · 生成物，别手改\n"
        "  来源：prts-design preview/_src/pages/home.html\n"
        "  生成：prts-skin-migration/scripts/build_mainpage_sandbox.py\n"
        "  任何皮肤下都能看：非 Arknights 皮肤由微件脚本动态加载皮肤的组件样式\n"
        "-->__NOTOC__\n" + body + "\n"
    )

    # 整块搬走的容器：内容要过同一套 wikitext 转换，再写成模板
    tpl_dir = args.out / "templates"
    tpl_dir.mkdir(parents=True, exist_ok=True)
    for filename, html in extracted.items():
        converted, _, more, n = convert_body(html)
        unmapped = sorted(set(unmapped) | set(more))
        anchors += n
        # G8：「特别开放周」的起止本来就在 PRTS:Gameinfo/国服/基础 里人工维护
        # （现网 模板:行动日历 第一行就在读它），这里只是换个出口给脚本用。
        # 存的是北京时间墙钟值，#time 不带时区参数即原样格式化，末尾补 +08:00。
        opening = '<div class="mp-today__res" id="mp-res">'
        if converted.count(opening) != 1:
            raise SystemExit("设计稿结构变了：找不到资源收集的容器 #mp-res")
        converted = converted.replace(
            opening,
            '<div class="mp-today__res" id="mp-res"'
            ' data-force-open="'
            "{{#time:Y-m-d\\TH:i:s|{{#lst:PRTS:Gameinfo/国服/基础|cndlystart}}}}+08:00"
            "/"
            "{{#time:Y-m-d\\TH:i:s|{{#lst:PRTS:Gameinfo/国服/基础|cndlyend}}}}+08:00"
            '">',
        )
        (tpl_dir / filename).write_text(
            "<includeonly>" + converted + "</includeonly><noinclude>\n"
            "首页的「资源收集」区块。生成物，别手改——源在\n"
            "prts-skin-migration/scripts/build_mainpage_sandbox.py。\n"
            "</noinclude>\n",
            encoding="utf-8",
        )

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "widget-mpstyle-newskin.txt").write_text(widget, encoding="utf-8")
    (args.out / "page-mainpage-sandbox.wiki").write_text(page, encoding="utf-8")
    (args.out / "report.json").write_text(
        json.dumps(
            {"icons": sorted(all_icons | icons), "unmapped_assets": unmapped},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    click.echo(
        f"微件 {len(widget)} 字节 · 页面 {len(page)} 字节 · 图标 {len(all_icons | icons)} 个 · "
        f"<a> 转真链接 {anchors} 处 · 补 .mw-heading 的 CSS 规则 {headings} 条"
    )
    if unmapped:
        click.echo(f"未映射素材 {len(unmapped)} 个（直接引设计稿的 GitHub Pages）：")
        for a in unmapped:
            click.echo(f"   {a}")


if __name__ == "__main__":
    main()
