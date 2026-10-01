"""首页 sandbox 数据页转换（scripts/mainpage_sandbox_apply.py）的单测。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from mainpage_sandbox_apply import (
    PAGES,
    convert_furniture,
    convert_stages,
    prod_title,
    to_prod,
)

STAGES = """'''SideStory 「直到大地变成一颗酸橙」'''

'''踏上归家长途'''
* [[TO-EX-1 电影防沉迷]]
* [[TO-EX-2 邮包流水线]]

'''眺望待行之路'''
* [[TO-S-1 邮箱保卫战]]

'''奇象巡展'''
* [[EE-01 奇象收录时间！]]
* [[ECB-S01 奇象拟合对战场]]

'''保全派驻#12「废都安保派驻」'''
* [[LT-1 铁锈闸口]]
"""


def stage(name: str) -> str:
    return "{{首页/新增关卡/关卡|" + name + "}}"


def test_stages_split_events_by_code_prefix() -> None:
    out = convert_stages(STAGES)
    assert out.count("{{首页/新增关卡\n") == 3
    # 活动名后面紧跟加粗行：底下两个加粗行是它的分组；写法同 BotPtilopsis，关卡逐个一个调用
    assert (
        "|1=SideStory 「直到大地变成一颗酸橙」\n|en=TO\n"
        f"|2=踏上归家长途\n|3={stage('TO-EX-1 电影防沉迷')}{stage('TO-EX-2 邮包流水线')}\n"
        f"|4=眺望待行之路\n|5={stage('TO-S-1 邮箱保卫战')}\n}}}}"
    ) in out
    # 关卡码换了一批前缀：不分组的新活动，英文小标列出全部前缀
    assert (
        "|1=奇象巡展\n|en=EE · ECB\n|2=\n"
        f"|3={stage('EE-01 奇象收录时间！')}{stage('ECB-S01 奇象拟合对战场')}\n}}}}"
    ) in out
    assert (
        f"|1=保全派驻#12「废都安保派驻」\n|en=LT\n|2=\n|3={stage('LT-1 铁锈闸口')}"
        in out
    )


def test_stages_same_prefix_stays_in_one_event() -> None:
    text = "'''矢量突破'''\n\n'''核心突破'''\n* [[VEC-01 寂静螺旋]]\n\n'''全力以赴'''\n* [[VEC-A 卓绝之巅]]\n"
    out = convert_stages(text)
    assert out.count("{{首页/新增关卡\n") == 1
    assert (
        f"|2=核心突破\n|3={stage('VEC-01 寂静螺旋')}\n"
        f"|4=全力以赴\n|5={stage('VEC-A 卓绝之巅')}"
    ) in out


def test_stages_without_heading_and_comma_in_name() -> None:
    # 机器人刚写、编辑还没补标题；关卡名里的半角逗号原样保留
    out = convert_stages("* [[6-13 没有火,没有光]]\n")
    assert (
        out
        == f"{{{{首页/新增关卡\n|1=\n|en=6\n|2=\n|3={stage('6-13 没有火,没有光')}\n}}}}"
    )


def test_stages_rejects_unknown_lines() -> None:
    with pytest.raises(SystemExit):
        convert_stages("'''活动'''\n随手写的一句话\n")


def test_furniture() -> None:
    assert (
        convert_furniture("{{家具主题|圣芭菲甜点店}} {{家具主题|蓝丝绒房间}}")
        == "{{首页/家具卡|1=圣芭菲甜点店|theme=1}}{{首页/家具卡|1=蓝丝绒房间|theme=1}}"
    )
    assert (
        convert_furniture("{{家具|饰牌《拟生》}}") == "{{首页/家具卡|1=饰牌《拟生》}}"
    )
    assert convert_furniture("") == ""
    with pytest.raises(SystemExit):
        convert_furniture("{{家具|饰牌《拟生》}} 多出来的字")


STAGED = [*PAGES, "模板:行动日历/sandbox"]


def test_prod_title() -> None:
    assert prod_title("模板:首页轮播/项/sandbox") == "模板:首页轮播/项"
    assert prod_title("首页/亮点干员/sandbox") == "首页/亮点干员"
    # 模板:行动日历 还被 新人入门 用着，新版另起名
    assert prod_title("模板:行动日历/sandbox") == "模板:首页/行动日历"


def test_to_prod_rewrites_every_reference() -> None:
    text = (
        "{{首页轮播/sandbox|mode=slide}}{{行动日历/sandbox}}{{:首页/亮点干员/sandbox}}"
        "|template=首页轮播/项/sandbox|{{tl|当前信息/条/sandbox}} 模板:当前信息/sandbox"
    )
    assert to_prod(text, STAGED) == (
        "{{首页轮播|mode=slide}}{{首页/行动日历}}{{:首页/亮点干员}}"
        "|template=首页轮播/项|{{tl|当前信息/条}} 模板:当前信息"
    )


def test_to_prod_refuses_leftover_sandbox_refs() -> None:
    with pytest.raises(SystemExit, match="/sandbox"):
        to_prod("{{别的模板/sandbox}}", STAGED)


def test_to_prod_on_real_sources() -> None:
    # 手写模板的源文件发布成正式版后，不能再引用任何 /sandbox 页
    src = Path(__file__).resolve().parents[1] / "migration/mainpage/templates"
    for f in PAGES.values():
        assert "/sandbox" not in to_prod((src / f).read_text(encoding="utf-8"), STAGED)
