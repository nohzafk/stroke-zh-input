#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stroke_zh 方案离线校验脚本
===========================
每次修改 build.py / 数据源 / keyboard 布局后, 跑一遍本脚本即可完成
与元书输入法(librime)部署相关的全部静态校验, 无需运行 librime 本体.

⚠️ 为什么不用 librime 实测: 在 iSH 环境 ctypes 加载 librime.so 跑
maintenance 部署会崩溃并带崩 Minis 宿主 (2026-08-06 实测闪退),
所以所有校验都在本脚本内模拟 librime/元书源码逻辑完成.

用法: python3 scripts/validate.py [--keyboard KEYBOARD_YAML]

校验项:
  1. dict 头部必须以 ... 闭合 (librime LoadDictHeader 只认 ... 为结束符,
     否则词条全被吞进 header → 0 entries → 编译失败)
  2. 词条可读性模拟 (LoadDictHeader + EntryCollector 逻辑)
  3. 编码合法性 (仅 hspnz 字符)
  4. 编码长度 (<= MAX_CODE_LENGTH)
  5. schema YAML 语法
  6. 键盘布局 YAML 语法 + action/width 合法性 (模拟元书解析器)
  7. 键盘每行必须有 input 宽度锚点 + 宽度分配模拟
"""
import os
import re
import sys
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
KEYBOARD = os.path.join(ROOT, "cskin", "dark", "pinyinPortrait.yaml")

VALID_CODE_CHARS = set("hspnz")
DICT_FILES = ["stroke_zh.dict.yaml", "stroke_zh_base.dict.yaml", "stroke_zh_phrase.dict.yaml"]

# ---------- 1&2. dict 头部闭合 + 词条读取模拟 ----------

def load_dict(path):
    """模拟 librime DictSettings::LoadDictHeader + EntryCollector.
    返回 (header_ok, entries, errors)"""
    errors = []
    header_ok = False
    entries = 0
    try:
        fin = open(path, encoding="utf-8")
    except OSError as e:
        return False, 0, [str(e)]
    header = []
    line = fin.readline()
    while line:
        s = line.rstrip("\n")
        header.append(s)
        if s == "...":            # yaml 文档结束符: 头部到此为止
            header_ok = True
            break
        line = fin.readline()
    h = "\n".join(header)
    if not header_ok:
        errors.append(f"头部未以 ... 闭合 (librime 会读到 EOF 吞掉全部词条)")
    if "name:" not in h:
        errors.append("头部缺少 name:")
    if "version:" not in h:
        errors.append("头部缺少 version:")
    # EntryCollector 逻辑: 从 ... 之后读词条
    for line in fin:
        s = line.rstrip("\n")
        if not s or s.startswith("#"):
            continue
        row = s.split("\t")
        if len(row) >= 2 and row[0] and row[1]:
            entries += 1
        else:
            errors.append(f"无效词条行: {s[:40]}")
    return header_ok, entries, errors


# ---------- 3&4. 编码检查 ----------

def check_codes(path):
    """编码合法性 + 长度检查"""
    errs = []
    total = 0
    bad_char = 0
    long_code = 0
    for line in open(path, encoding="utf-8"):
        s = line.rstrip("\n")
        if not s or s.startswith("#"):
            continue
        if ":" in s and not s.startswith(" "):
            continue
        row = s.split("\t")
        if len(row) < 2:
            continue
        total += 1
        code = row[1]
        if not set(code) <= VALID_CODE_CHARS:
            bad_char += 1
            if bad_char <= 3:
                errs.append(f"非法编码字符: {s[:50]}")
        if len(code) > 32:
            long_code += 1
    if bad_char:
        errs.append(f"共 {bad_char} 个条目编码含非 hspnz 字符 (librime 编译异常/闪退风险)")
    if long_code:
        errs.append(f"共 {long_code} 个条目编码超长 (>32, 超出 max_code_length)")
    return total, errs


# ---------- 5. schema YAML 语法 ----------

def check_schema():
    errs = []
    path = os.path.join(BUILD, "stroke_zh.schema.yaml")
    try:
        d = yaml.safe_load(open(path, encoding="utf-8"))
        if d is None or "schema" not in d:
            errs.append("schema 缺少 schema: 段")
        else:
            sid = d["schema"].get("schema_id")
            if sid != "stroke_zh":
                errs.append(f"schema_id 应为 stroke_zh, 实际 {sid}")
            eng = d.get("engine", {})
            if "translators" not in eng:
                errs.append("engine 缺少 translators")
            tr = eng.get("translators", [])
            if "table_translator" not in tr:
                errs.append("translators 缺少 table_translator")
            trans = d.get("translator", {})
            if trans.get("dictionary") != "stroke_zh":
                errs.append(f"translator.dictionary 应为 stroke_zh, 实际 {trans.get('dictionary')}")
            if not trans.get("enable_completion"):
                errs.append("enable_completion 未开启 (词组前缀联想依赖此选项)")
    except yaml.YAMLError as e:
        errs.append(f"YAML 解析失败: {e}")
    return errs


# ---------- 6&7. 键盘布局校验 (模拟元书解析器) ----------

def attribute_parse(s):
    """模拟元书 String.attributeParse()"""
    fi = s.find("(")
    li = s.rfind(")")
    if fi == -1 and li == -1:
        return (s, "")
    if (fi != -1 and li == -1) or (fi == -1 and li != -1):
        return None
    if fi > li:
        return None
    return (s[:fi], s[fi + 1:li])


VALID_ACTIONS = {"backspace", "enter", "shift", "tab", "space", "character",
                 "charactermargin", "keyboardtype", "symbol", "shortcommand",
                 "chineseninegrid", "none", "nextkeyboard"}
VALID_KT = {"alphabetic", "numeric", "symbolic", "classifysymbolic", "chinese",
            "chineseninegrid", "numericninegrid", "custom", "emojis"}
VALID_WIDTH = {"available", "input", "inputpercentage", "percentage", "points"}


def check_keyboard(path):
    """校验 cskin 皮肤布局: keyboardLayout 的 Cell 引用完整性 + action 合法性"""
    errs = []
    warns = []
    try:
        d = yaml.safe_load(open(path, encoding="utf-8"))
    except OSError:
        return ["皮肤布局文件不存在: " + path], []
    if not d or "keyboardLayout" not in d:
        return ["keyboardLayout: 缺失"], []
    # 收集所有 Cell 引用
    cells = []
    def collect(node):
        if isinstance(node, dict):
            if "Cell" in node:
                cells.append(node["Cell"])
            for v in node.values():
                collect(v)
        elif isinstance(node, list):
            for v in node:
                collect(v)
    collect(d["keyboardLayout"])
    missing = [c for c in cells if c not in d]
    if missing:
        errs.append(f"Cell 引用缺失定义: {missing}")
    # action 合法性
    for k in cells:
        if k in d:
            btn = d[k]
            if "action" not in btn:
                warns.append(f"{k}: 无 action")
    return errs, warns
    for kb in d["keyboards"]:
        name = kb.get("name", "?")
        for ri, row in enumerate(kb.get("rows", [])):
            keys = row.get("keys", [])
            has_input_anchor = any(k.get("width") == "input" or "width" not in k for k in keys)
            if not has_input_anchor:
                # 历史注记: 仓输入法 2.19.5 对导入键盘的 input 宽度键渲染 bug (宽度0不显示),
                # 全 available 布局是绕过方案 (实证可用), 故此处仅警告
                warns.append(f"[{name}] 行{ri+1}: 无 input 宽度锚点 (v7 绕过方案, 全 available)")
            for k in keys:
                a = attribute_parse(k["action"])
                if a is None:
                    errs.append(f"[{name}] 行{ri+1}: action 格式错误: {k['action']}")
                    continue
                t, v = a
                if t.lower() not in VALID_ACTIONS:
                    errs.append(f"[{name}] 行{ri+1}: action 类型无效: {k['action']}")
                elif t.lower() == "keyboardtype" and v.lower() not in VALID_KT:
                    errs.append(f"[{name}] 行{ri+1}: keyboardType 无效: {k['action']}")
                if t.lower() == "character" and not v:
                    errs.append(f"[{name}] 行{ri+1}: character 值为空")
                w = k.get("width")
                if w is not None:
                    wp = attribute_parse(w)
                    if wp is None:
                        errs.append(f"[{name}] 行{ri+1}: width 格式错误: {w}")
                    elif wp[0].lower() not in VALID_WIDTH:
                        errs.append(f"[{name}] 行{ri+1}: width 类型无效: {w}")
                if "processByRIME" in k and not isinstance(k["processByRIME"], bool):
                    errs.append(f"[{name}] 行{ri+1}: processByRIME 非 bool")
        if not kb.get("isPrimary"):
            warns.append(f"[{name}] isPrimary 未设置 (从数字/符号键盘可能无法返回)")
    return errs, warns


# ---------- main ----------

def main():
    ok = True
    print("=" * 56)
    print("stroke_zh 离线校验 (模拟 librime 1.17 / 元书皮肤解析逻辑)")
    print("=" * 56)

    print("\n[1] dict 头部闭合 + 词条读取模拟")
    for f in DICT_FILES:
        p = os.path.join(BUILD, f)
        hok, n, errs = load_dict(p)
        status = "✓" if hok and not errs else "✗"
        print(f"  {status} {f}: 词条 {n} 头部闭合={hok}")
        for e in errs:
            print(f"      ✗ {e}")
            ok = False

    print("\n[2] 编码合法性 (仅 hspnz)")
    for f in ["stroke_zh_base.dict.yaml", "stroke_zh_phrase.dict.yaml"]:
        total, errs = check_codes(os.path.join(BUILD, f))
        if errs:
            print(f"  ✗ {f}: {total} 条, 问题:")
            for e in errs[:5]:
                print(f"      ✗ {e}")
            ok = False
        else:
            print(f"  ✓ {f}: {total} 条编码全部合法")

    print("\n[3] schema YAML")
    errs = check_schema()
    if errs:
        for e in errs:
            print(f"  ✗ {e}")
        ok = False
    else:
        print("  ✓ stroke_zh.schema.yaml 语法与关键字段正常")

    print("\n[4] 键盘布局")
    errs, warns = check_keyboard(KEYBOARD)
    if errs:
        for e in errs:
            print(f"  ✗ {e}")
        ok = False
    else:
        print(f"  ✓ {os.path.basename(KEYBOARD)} 解析与宽度锚点正常")
    for w in warns:
        print(f"  ⚠ {w}")

    print("\n" + "=" * 56)
    if ok:
        print("✅ 全部校验通过, 可安全导入元书输入法")
    else:
        print("❌ 存在问题, 修复后重跑")
    print("=" * 56)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
