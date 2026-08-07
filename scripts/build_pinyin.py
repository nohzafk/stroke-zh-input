#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""简体拼音方案构建: 基于雾凇词库 (rime-ice), 词频过滤 + 常用字过滤 + 离线转 T9 数字码.
词库直接存 T9 数字码 (ni hao → 64426), 运行时零派生规则 → 部署快 (40万条几秒编译).
产物: build/pinyin_lite.schema.yaml + build/pinyin_lite.dict.yaml
用法: python3 scripts/build_pinyin.py
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
BUILD = os.path.join(ROOT, "build")

SCHEMA_ID = "pinyin_lite"

# T9 数字映射 (标准手机键盘): abc=2 def=3 ghi=4 jkl=5 mno=6 pqrs=7 tuv=8 wxyz=9
T9_MAP = {
    "a": "2", "b": "2", "c": "2", "d": "3", "e": "3", "f": "3",
    "g": "4", "h": "4", "i": "4", "j": "5", "k": "5", "l": "5",
    "m": "6", "n": "6", "o": "6", "p": "7", "q": "7", "r": "7", "s": "7",
    "t": "8", "u": "8", "v": "8", "w": "9", "x": "9", "y": "9", "z": "9",
}


def pinyin_to_t9(pinyin: str) -> str:
    """ni hao → 64426 (连写). ü 按 u 处理 (8 键)."""
    return "".join(T9_MAP.get(c.lower(), "8") for c in pinyin if c.isalpha())


# 模糊音规则 (词库端生成变体, 运行时零开销)
# 平翘舌: zh↔z ch↔c sh↔s ; 前后鼻: an↔ang en↔eng in↔ing uan↔uang ian↔iang
FUZZY_SETS = [
    ("zh", "z"), ("ch", "c"), ("sh", "s"),
    ("ang", "an"), ("eng", "en"), ("ing", "in"),
    ("uang", "uan"), ("iang", "ian"),
]


def pinyin_variants(pinyin: str) -> list[str]:
    """对拼音串生成模糊音变体. 如: ni hao → [ni hao]; zhi dao → [zhi dao, zi dao]"""
    syls = pinyin.split()
    result = [syls]
    for i, syl in enumerate(syls):
        alts = [syl]
        for orig, alt in FUZZY_SETS:
            if syl.endswith(orig):
                alts.append(syl[: -len(orig)] + alt)
            elif syl.endswith(alt) and orig in ("zh", "ch", "sh"):
                alts.append(syl[: -len(alt)] + orig)
        if len(alts) > 1:
            new = []
            for v in result:
                for a in alts:
                    new.append(v[:i] + [a] + v[i + 1 :])
            result = new
    return [" ".join(v) for v in result]


def load_common_chars():
    """GB2312 6763 + 通用规范汉字表 8105 基本区 (与笔画方案一致)"""
    chars = []
    for hi in range(0xB0, 0xD8):
        for lo in range(0xA1, 0xFF):
            try:
                c = bytes([hi, lo]).decode("gb2312")
                if len(c) == 1 and "\u4e00" <= c <= "\u9fff":
                    chars.append(c)
            except UnicodeDecodeError:
                pass
    for hi in range(0xD8, 0xF8):
        for lo in range(0xA1, 0xFF):
            try:
                c = bytes([hi, lo]).decode("gb2312")
                if len(c) == 1 and "\u4e00" <= c <= "\u9fff":
                    chars.append(c)
            except UnicodeDecodeError:
                pass
    guifan = os.path.join(DATA, "guifan8105.txt")
    if os.path.exists(guifan):
        for line in open(guifan, encoding="utf-8"):
            c = line.strip()
            if len(c) == 1 and "\u4e00" <= c <= "\u9fff" and c not in chars:
                chars.append(c)
    return set(dict.fromkeys(chars))


def filter_ice(src, dst, common, min_freq, append=False):
    """过滤雾凇词库 + 模糊音变体 + 拼音转 T9 数字码: 词\\tT9码\\t权重.
    词频≥min_freq + 词内所有字须为常用字. 同词同码去重.
    append=True 时追加写 (用于合并多个词库到同一 dict).
    返回 (保留数, 跳过数)."""
    kept = 0
    skipped = 0
    seen: set[tuple[str, str]] = set()
    if append:
        # 追加模式: 读取已有条目去重
        if os.path.exists(dst):
            for line in open(dst, encoding="utf-8"):
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 2:
                    seen.add((parts[0], parts[1]))
        mode = "a"
    else:
        mode = "w"
    with open(dst, mode, encoding="utf-8") as out:
        if not append:
            out.write("# Rime dictionary: pinyin_lite\n")
            out.write("# encoding: utf-8\n")
            out.write("#\n")
            out.write("---\n")
            out.write("name: pinyin_lite\n")
            out.write('version: "1.0.0"\n')
            out.write("sort: by_weight\n")
            out.write("...\n")
        for line in open(src, encoding="utf-8"):
            s = line.rstrip("\n")
            if not s or s.startswith("#") or s in ("---", "..."):
                continue
            if ":" in s and not s.startswith(" "):
                continue
            parts = s.split("\t")
            if len(parts) < 3:
                continue
            text, pinyin, weight = parts[0], parts[1], parts[2]
            try:
                w = int(weight)
            except ValueError:
                continue
            if w < min_freq:
                skipped += 1
                continue
            if not text or not all("\u4e00" <= c <= "\u9fff" for c in text):
                skipped += 1
                continue
            if not all(c in common for c in text):
                skipped += 1
                continue
            for variant in pinyin_variants(pinyin):
                code = pinyin_to_t9(variant)
                if not code:
                    continue
                if (text, code) in seen:
                    continue
                seen.add((text, code))
                out.write(f"{text}\t{code}\t{weight}\n")
                kept += 1
    return kept, skipped


def build_schema():
    """生成拼音 schema (T9 数字码直配, 无运行时派生规则 → 部署快)"""
    schema = f"""# Rime schema
# encoding: utf-8
schema:
  schema_id: {SCHEMA_ID}
  name: 简体拼音
  version: "1.0.0"
  description: 简体拼音 T9 九宫格 (雾凇词库, 离线转数字码)

switches:
  - name: ascii_mode
    reset: 0
    states: [ 中文, ABC ]
  - name: full_shape
    states: [ 半角, 全角 ]
  - name: ascii_punct
    states: [ 中文标点, 西文标点 ]

engine:
  processors:
    - ascii_composer
    - recognizer
    - key_binder
    - speller
    - punctuator
    - selector
    - navigator
    - express_editor
  segmentors:
    - ascii_segmentor
    - matcher
    - abc_segmentor
    - punct_segmentor
    - fallback_segmentor
  translators:
    - punct_translator
    - table_translator
  filters:
    - uniquifier

speller:
  alphabet: '987654321'
  delimiter: "''"
  auto_select: true
  auto_select_pattern: '^\\d+$'
  max_code_length: 30

translator:
  dictionary: {SCHEMA_ID}
  enable_completion: true
  enable_user_dict: true
  max_phrase_length: 6
  comment_format: []   # 候选只显示汉字, 不显示数字编码注释 (像系统拼音键盘)

punctuator:
  import_preset: default

key_binder:
  import_preset: default

recognizer:
  import_preset: default
"""
    dst = os.path.join(BUILD, f"{SCHEMA_ID}.schema.yaml")
    with open(dst, "w", encoding="utf-8") as f:
        f.write(schema)
    return dst


def main() -> None:
    os.makedirs(BUILD, exist_ok=True)
    common = load_common_chars()
    print(f"[1/3] 常用字集: {len(common)} 字")
    dst = os.path.join(BUILD, f"{SCHEMA_ID}.dict.yaml")
    # 雾凇 base 词组库 (词频≥20 + 常用字过滤 + 模糊音变体 + T9 转码)
    kept1, skipped1 = filter_ice(
        os.path.join(DATA, "rime_ice_base.dict.yaml"), dst, common, min_freq=20,
    )
    print(f"[2/3] base 词组库: 保留 {kept1}, 跳过 {skipped1}")
    # 8105 单字表 (词频≥1, 追加合并, 保证单字都能打)
    kept2, skipped2 = filter_ice(
        os.path.join(DATA, "rime_ice_8105.dict.yaml"), dst, common, min_freq=1, append=True,
    )
    print(f"      8105 单字表: 保留 {kept2}, 跳过 {skipped2}")
    print(f"      合并后词条: {kept1 + kept2}")
    schema = build_schema()
    print(f"[3/3] schema: {schema}")
    print("完成! 产物: build/pinyin_lite.schema.yaml + pinyin_lite.dict.yaml")


if __name__ == "__main__":
    main()
