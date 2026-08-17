#!/usr/bin/env python3
"""生成自定义 symbolic（程序员符号）+ specialSymbols（特殊符号）键盘布局。

生成文件 (light/dark x portrait/landscape):
  symbolicPortrait.yaml / symbolicLandscape.yaml        — 程序员常用英文符号 3 行
  specialSymbolsPortrait.yaml / specialSymbolsLandscape — 特殊符号(货币/数学/箭头) 3 行
config.yaml 加 symbolic + specialSymbols 映射。
symbolic 底部行含「更多」按钮 (keyboardType: specialSymbols) 进特殊符号页；
specialSymbols 底部行「返回」回 symbolic。

本脚本只负责生成布局文件 + config.yaml patch，不做打包。

!!! 打包纪律（重要，2026-08-17 踩坑教训）!!!
cskin/ 源目录 = stroke_zh_pinyin（笔画拼音）的源。stroke_zh（笔画增强）在仓库无源，
它的 pinyin 4 个布局是特制版（与源目录不同）、且不含 t9pinyin、config.yaml name=笔画增强。
因此：
- stroke_zh_pinyin.cskin：可以从 cskin/ 源目录整体重建
- stroke_zh.cskin：必须先解包旧包，只覆盖/新增 symbolic 相关文件，
  config.yaml 在旧包版本上 patch（保留 name=笔画增强、不引入 t9pinyin 映射），
  pinyin/alphabetic/numeric/t9pinyin 布局一律不动
用 git 对比新旧包内部文件 md5 验证：除新增 symbolic + config.yaml 外必须零变化。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根 (scripts/ 的上级)
SKIN = os.path.join(ROOT, "cskin")

# 数字键盘特有、symbolic 键盘不需要的顶层键
DROP_KEYS = {
    "oneButton", "twoButton", "threeButton", "fourButton", "fiveButton",
    "sixButton", "sevenButton", "eightButton", "nineButton", "zeroButton",
    "oneButtonForegroundStyle", "twoButtonForegroundStyle", "threeButtonForegroundStyle",
    "fourButtonForegroundStyle", "fiveButtonForegroundStyle", "sixButtonForegroundStyle",
    "sevenButtonForegroundStyle", "eightButtonForegroundStyle", "nineButtonForegroundStyle",
    "zeroButtonForegroundStyle",
    "numericSymbolsCollection", "symbolicButton", "symbolicButtonForegroundStyle",
    "equalButton", "equalButtonForegroundStyle", "periodButton", "periodButtonForegroundStyle",
    "narrowVStackStyle", "wideVStackStyle", "keyboardLayout",
}

# ============ 符号表 ============
# symbolic 键盘 (程序员常用, 无中文标点 — 中文标点笔画键盘左列已有):
#   行1/行2 对齐 iOS 系统 #+= 页; 行2 的 € £ ¥ • (欧洲货币) 换成 @ $ & / (程序员高频)
#   每页行1 最右 = 退格键 (右上角, 用户要求 2026-08-17; 底部行不放退格)
#   行内元素: (键名, 符号) 或纯字符串 "backspaceButton" (引用模板已有定义, 不生成)
SYM_ROWS = [
    [("s01", "["), ("s02", "]"), ("s03", "{"), ("s04", "}"), ("s05", "#"),
     ("s06", "%"), ("s07", "^"), ("s08", "*"), ("s09", "+"), "backspaceButton"],
    [("s11", "_"), ("s12", "\\"), ("s13", "~"), ("s14", "<"), ("s15", ">"),
     ("s16", "@"), ("s17", "$"), ("s18", "&"), ("s19", "/"), ("s20", "=")],
    [("s21", "."), ("s22", ","), ("s23", "?"), ("s24", "!"), ("s25", "'"),
     ("s26", '"'), ("s27", "("), ("s28", ")"), ("s29", "-"), ("s30", ";")],
]

# specialSymbols 键盘 (3 行, 用户定制 2026-08-17):
#   行1: 货币 € \$ ¥ + 数学运算/比较 (用户去掉 ± 加减号) + 右上角退格
#   行2: 常用希腊字母 (保留)
#   行3: 箭头(流程/方向) + 排版符号(· — …) + Mac 修饰键 (⌘ ⌥ ⇧)
SPECIAL_ROWS = [
    [("t01", "€"), ("t02", "$"), ("t03", "¥"), ("t04", "×"), ("t05", "÷"),
     ("t06", "≠"), ("t07", "≤"), ("t08", "≥"), ("t09", "≈"), "backspaceButton"],
    [("t11", "α"), ("t12", "β"), ("t13", "γ"), ("t14", "δ"), ("t15", "ε"),
     ("t16", "θ"), ("t17", "λ"), ("t18", "μ"), ("t19", "π"), ("t20", "σ")],
    [("t21", "→"), ("t22", "←"), ("t23", "↑"), ("t24", "↓"), ("t25", "·"),
     ("t26", "…"), ("t27", "⌘"), ("t28", "⌥"), ("t29", "⌃"), ("t30", "⇧")],
]

BOTTOM_BASE = ["returnLastKeyboardButton", "numericButton", "spaceButton", "enterButton"]


def split_top_keys(text):
    """按顶层键（无缩进行）切分 yaml 为 {键名: 文本块(含键头行)}"""
    lines = text.split("\n")
    keys = []
    cur = None
    for ln in lines:
        if ln and not ln[0].isspace() and ":" in ln and not ln.startswith("- "):
            name = ln.split(":", 1)[0].strip()
            if cur is not None:
                keys.append(cur)
            cur = [name, [ln]]
        elif cur is not None:
            cur[1].append(ln)
    if cur is not None:
        keys.append(cur)
    return {k[0]: "\n".join(k[1]) for k in keys}


def gen_layout(rows, bottom_keys):
    """rows: 符号行列表 (元素为 (name, sym) 或字符串键名如 "backspaceButton");
    bottom_keys: 底部行键名列表"""
    out = []
    for row in rows:
        cells = "\n".join(
            "    - Cell: %s" % (item if isinstance(item, str) else item[0] + "Button")
            for item in row)
        out.append("- HStack:\n    subviews:\n" + cells)
    bottom = "\n".join("    - Cell: %s" % k for k in bottom_keys)
    out.append("- HStack:\n    subviews:\n" + bottom)
    return "\n".join(out)


def gen_symbol_keys(rows, fg_hl, fg_norm):
    """每个符号键生成独立 foregroundStyle (text=符号本身)。
    元书没有"自动显示 action 符号"的机制: 键面文本必须每个键单独写
    (numeric 模板的数字键就是各自 oneButtonForegroundStyle text:'1')。
    共用一个 text:'' 的样式 = 键面空白 (2026-08-17 真机空白 bug 根因)。
    字符串元素 (如 "backspaceButton") 引用模板已有定义, 不生成。
    """
    def yq(s):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    blocks = []
    for item in [k for row in rows for k in row]:
        if isinstance(item, str):
            continue
        name, sym = item
        fs = name + "ButtonForegroundStyle"
        blocks.append(
            f"{name}Button:\n"
            f"  action:\n"
            f"    symbol: {yq(sym)}\n"
            f"  backgroundStyle: alphabeticButtonBackgroundStyle\n"
            f"  foregroundStyle: {fs}\n"
            f"{fs}:\n"
            f"  buttonStyleType: text\n"
            f"  fontSize: 22.5\n"
            f"  highlightColor: '{fg_hl}'\n"
            f"  normalColor: '{fg_norm}'\n"
            f"  text: {yq(sym)}")
    return "\n".join(blocks)


NEW_BLOCKS_TEMPLATE = """numericButton:
  action:
    keyboardType: numeric
  backgroundStyle: systemButtonBackgroundStyle
  foregroundStyle: numericButtonForegroundStyle
  size:
    width:
      percentage: 0.132
numericButtonForegroundStyle:
  buttonStyleType: text
  fontSize: 16
  highlightColor: 'FG_HIGHLIGHT'
  normalColor: 'FG_NORMAL'
  text: '123'
moreSymbolsButton:
  action:
    keyboardType: specialSymbols
  backgroundStyle: systemButtonBackgroundStyle
  foregroundStyle: moreSymbolsButtonForegroundStyle
  size:
    width:
      percentage: 0.132
moreSymbolsButtonForegroundStyle:
  buttonStyleType: text
  fontSize: 16
  highlightColor: 'FG_HIGHLIGHT'
  normalColor: 'FG_NORMAL'
  text: '更多'
"""


def add_size(block, width):
    """给按键块追加 size (块内无 size 时)"""
    if "  size:" in block:
        return block
    return block.rstrip("\n") + f"\n  size:\n    width:\n      percentage: {width}\n"


def build_one(mode, suffix, rows, bottom_keys, extra_blocks):
    tpl = open(os.path.join(SKIN, mode, "portraitNumeric.yaml"), encoding="utf-8").read()
    blocks = split_top_keys(tpl)
    keep = {k: v for k, v in blocks.items() if k not in DROP_KEYS}
    if "keyboardLayout" in keep:
        del keep["keyboardLayout"]

    fg_hl, fg_norm = ("#1C1C1E", "#1C1C1E") if mode == "light" else ("#FFFFFF", "#FFFFFF")
    nb = extra_blocks.replace("FG_HIGHLIGHT", fg_hl).replace("FG_NORMAL", fg_norm)

    # 底部行: 返回/回车宽度对齐其他模式 (0.17); numeric 模板继承的这两键无 size
    keep["returnLastKeyboardButton"] = add_size(keep["returnLastKeyboardButton"], "0.17")
    keep["enterButton"] = add_size(keep["enterButton"], "0.17")
    # 退格键不放底部行了 (在行1 右上角, 与其他键均分宽度), 不设 size

    body = "\n".join(keep.values()) + "\n" + nb + "\n" + gen_symbol_keys(rows, fg_hl, fg_norm) + "\n"
    # 回车文字大小对齐其他模式右下回车键 (英文/笔画 enterButton 字号 12;
    # numeric 模板是 16) — 用户要求 2026-08-17
    old_enter = "enterButtonForegroundStyle:\n  buttonStyleType: text\n  fontSize: 16\n"
    new_enter = "enterButtonForegroundStyle:\n  buttonStyleType: text\n  fontSize: 12\n"
    assert old_enter in body, f"{suffix}: enterButtonForegroundStyle fontSize 16 未找到"
    body = body.replace(old_enter, new_enter)
    layout = "keyboardLayout:\n" + "\n".join(
        "  " + ln for ln in gen_layout(rows, bottom_keys).split("\n")) + "\n"
    path = os.path.join(SKIN, mode, suffix + ".yaml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(body + layout)
    print("written", path, len(body + layout), "chars")


def build_all():
    # symbolic: 底部行 返回 | 123 | 空格 | 更多 | 回车 (退格在行1 右上角)
    sym_bottom = ["returnLastKeyboardButton", "numericButton", "spaceButton",
                  "moreSymbolsButton", "enterButton"]
    # specialSymbols: 底部行 返回 | 123 | 空格 | 回车 (返回回 symbolic)
    spec_bottom = ["returnLastKeyboardButton", "numericButton", "spaceButton",
                   "enterButton"]
    for mode in ("light", "dark"):
        build_one(mode, "symbolicPortrait", SYM_ROWS, sym_bottom, NEW_BLOCKS_TEMPLATE)
        build_one(mode, "symbolicLandscape", SYM_ROWS, sym_bottom, NEW_BLOCKS_TEMPLATE)
        build_one(mode, "specialSymbolsPortrait", SPECIAL_ROWS, spec_bottom, NEW_BLOCKS_TEMPLATE)
        build_one(mode, "specialSymbolsLandscape", SPECIAL_ROWS, spec_bottom, NEW_BLOCKS_TEMPLATE)


def patch_config():
    path = os.path.join(SKIN, "config.yaml")
    text = open(path, encoding="utf-8").read()
    if "symbolic:" not in text:
        add = ("symbolic:\n"
               "  iPhone:\n"
               "    portrait: symbolicPortrait\n"
               "    landscape: symbolicLandscape\n")
        marker = "numeric:\n  iPhone:\n    portrait: portraitNumeric\n    landscape: landscapeNumeric\n"
        assert marker in text, "config.yaml 结构不符预期 (numeric 节)"
        text = text.replace(marker, marker + add)
        print("config.yaml: symbolic 映射已加")
    if "specialSymbols:" not in text:
        add = ("specialSymbols:\n"
               "  iPhone:\n"
               "    portrait: specialSymbolsPortrait\n"
               "    landscape: specialSymbolsLandscape\n")
        marker = "symbolic:\n  iPhone:\n    portrait: symbolicPortrait\n    landscape: symbolicLandscape\n"
        assert marker in text, "config.yaml 结构不符预期 (symbolic 节)"
        text = text.replace(marker, marker + add)
        print("config.yaml: specialSymbols 映射已加")
    open(path, "w", encoding="utf-8").write(text)


if __name__ == "__main__":
    build_all()
    patch_config()
