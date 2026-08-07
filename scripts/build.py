#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
笔画·增强 (stroke_zh) RIME 方案构建脚本
========================================
数据源:
  - data/stroke_official.dict.yaml  官方 rime-stroke 五笔画码表 (字 -> 笔画序)
  - data/jieba_dict.txt             jieba 词库 (词 频次 [词性])

产物 (build/):
  - stroke_zh_base.dict.yaml        单字码表 (官方全量, 频次改用 jieba 单字频次)
  - stroke_zh_phrase.dict.yaml      词组码表 (词 -> 每字笔画序拼接, 带频次)
  - stroke_zh.dict.yaml             主码表 (import 以上两者)
  - stroke_zh.schema.yaml           方案配置 (五笔画 + 前缀联想 + 用户词典学习)
  - stroke_zh.zip                   元书输入法可直接导入的打包 (dist/)

用法: python3 scripts/build.py
"""
import os
import re
import sys
import zipfile
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
BUILD = os.path.join(ROOT, "build")
DIST = os.path.join(ROOT, "dist")

PHRASE_MIN_LEN = 2      # 词组最小字数
PHRASE_MAX_LEN = 6      # 词组最大字数
PHRASE_MIN_FREQ = 50   # jieba 词频阈值 (控制词组表规模, 调低则词多)
PHRASE_WEIGHT_FACTOR = 10  # 词组权重系数: jieba 词频与单字频次量级差 2-3 个数量级,
                            # 乘此系数让常用词组在候选里提前 (否则被单字碾压排后面)
MAX_CODE_LENGTH = 32    # 编码长度上限 (6字词=30笔, 留余量)

# 合法编码字符 (五笔画: 横竖撇捺折)
VALID_CODE_CHARS = set("hspnz")

# 高频无搭配单字权重加成: 这些字常用但很少组词(如"的/有/个"), 打单字时被词组
# 碾压排后(实测"的"打2笔排第9、"个"排第40). 权重 ×100 让它们打前几笔即靠前.
# 不影响词组输入: 单字编码与词组简码独立, 只在同前缀竞争时单字提前.
HIGH_FREQ_SINGLE_BONUS = {
    "的", "有", "个", "是", "在", "了", "和", "我", "你", "他", "这", "那", "不", "人",
    "中", "大", "上", "为", "以", "要", "就", "都", "也", "很", "到", "说", "去", "能",
    "会", "着", "没", "看", "好", "来", "时", "里", "地", "子", "日", "年", "天", "下",
    "小", "多", "少", "又", "才", "只", "可", "再", "最", "真", "太", "更",
}
SINGLE_BONUS_MULT = 100  # 高频单字权重倍数

# Conway/汉典 数字笔画 (1=横 2=竖 3=撇 4=点/捺 5=折) → hspnz
CONWAY_DIGIT_MAP = {"1": "h", "2": "s", "3": "p", "4": "n", "5": "z"}

# 标准笔顺补充表: 官方码表 (台湾 CNS11643) 与大陆标准笔顺有差异的字
# 同一字追加标准笔顺编码 (两种编码都能打), 用户遇到打不出的字在此补充
STROKE_FIX = {
    '着': 'nphhhpszhhh',   # 大陆: 丶丿一一一丿丨𠃍一一一 (11画) vs 台湾码表 nphhshpszhhh
}


def load_common_chars():
    """常用字集 = GB2312 6763 + 通用规范汉字表 8105 基本区增量 (共约 7957 字).
    PingFang SC 完整支持基本区 (U+4E00-U+9FFF); 扩展区字 (CJK-A/B+) 字体缺失
    会乱码, 8105 里的 273 个扩展区字不加入."""
    chars = []
    for hi in range(0xB0, 0xD8):        # GB2312 一级汉字 3755
        for lo in range(0xA1, 0xFF):
            try:
                c = bytes([hi, lo]).decode('gb2312')
                if len(c) == 1 and '\u4e00' <= c <= '\u9fff':
                    chars.append(c)
            except UnicodeDecodeError:
                pass
    for hi in range(0xD8, 0xF8):        # GB2312 二级汉字 3008
        for lo in range(0xA1, 0xFF):
            try:
                c = bytes([hi, lo]).decode('gb2312')
                if len(c) == 1 and '\u4e00' <= c <= '\u9fff':
                    chars.append(c)
            except UnicodeDecodeError:
                pass
    # 通用规范汉字表 8105 增量 (仅基本区)
    guifan = os.path.join(DATA, "guifan8105.txt")
    if os.path.exists(guifan):
        for line in open(guifan, encoding="utf-8"):
            c = line.strip()
            if len(c) == 1 and '\u4e00' <= c <= '\u9fff' and c not in chars:
                chars.append(c)
    return set(dict.fromkeys(chars))

SCHEMA_ID = "stroke_zh"
SCHEMA_NAME = "笔画·增强"


def parse_yaml_header(path):
    """解析 RIME dict 头部. 健壮版: 跳过注释/空行/---/.../键值对行,
    其余即数据行. 兼容官方 stroke 无闭合 --- 的格式."""
    header = {}
    data = []
    for line in open(path, encoding="utf-8"):
        s = line.strip()
        if not s or s.startswith("#") or s == "---" or s == "...":
            continue
        if ":" in s and not s.startswith(" "):
            k, v = s.split(":", 1)
            header[k.strip()] = v.strip()
            continue
        data.append(line.rstrip("\n"))
    return header, data


def expand_conway(seq: str) -> list[str] | None:
    """展开 Conway 笔画序列 (含 (a|b) 多选 与 \\1 反向引用).

    例: 4311(|2)1325111 -> [431111325111, 431121325111]
        32(1534|1543)\\1  -> [3215341534, 3215431543]  (\\1 = 第一分组捕获值)
    返回 None 表示无法展开 (应跳过, 由台湾码表兜底).
    """
    results: list[tuple[str, str | None]] = [("", None)]  # (编码, 第一分组值)
    i = 0
    while i < len(seq):
        c = seq[i]
        if c == "(":
            j = seq.find(")", i)
            if j < 0:
                return None
            options = seq[i + 1:j].split("|")
            new_results = []
            for code, g1 in results:
                for o in options:
                    new_results.append((code + o, g1 if g1 is not None else o))
            results = new_results
            i = j + 1
        elif c == "\\" and i + 1 < len(seq) and seq[i + 1] == "1":
            new_results = []
            for code, g1 in results:
                if g1 is None:
                    return None
                new_results.append((code + g1, g1))
            results = new_results
            i += 2
        else:
            results = [(code + c, g1) for code, g1 in results]
            i += 1
    return [code for code, _ in results]


def load_stroke(path):
    """笔画码表 -> {char: [codes]}
    数据源: hzbishun 13000.csv (基于 GB 标准的大陆简体笔顺, 20902 字, GB2312 全覆盖)
    列: 字序,字,画数,笔画码,Unicode,GB内码
    """
    import csv as _csv
    char_map = {}
    hz = os.path.join(DATA, "hzbishun_13000.csv")
    with open(hz, encoding="utf-8") as f:
        for row in _csv.reader(f):
            if len(row) >= 5 and row[1] and row[3]:
                ch = row[1]
                # 数字笔画 (1=横 2=竖 3=撇 4=点 5=折) → hspnz
                code = "".join(CONWAY_DIGIT_MAP.get(d, "?") for d in row[3])
                if set(code) <= VALID_CODE_CHARS:
                    char_map.setdefault(ch, []).append(code)
    return char_map


def load_jieba(path):
    """解析 jieba dict -> {word: freq}"""
    freq = {}
    for line in open(path, encoding="utf-8-sig"):
        parts = line.rstrip("\n").split()
        if len(parts) >= 2:
            try:
                freq[parts[0]] = int(parts[1])
            except ValueError:
                continue
    return freq


def load_rime_ice(path):
    """解析雾凇词库 (词\\t拼音\\t权重) -> {word: weight}"""
    result = {}
    for line in open(path, encoding="utf-8"):
        s = line.rstrip("\n")
        if not s or s.startswith("#") or s in ("---", "..."):
            continue
        if ":" in s and not s.startswith(" "):
            continue
        parts = s.split("\t")
        if len(parts) < 3:
            continue
        try:
            result[parts[0]] = int(parts[2])
        except ValueError:
            continue
    return result


def write_dict(path, name, version, entries, sort="by_weight", extra_header=""):
    """entries: list of "word\tcode\tfreq" 已排序
    注意: 头部必须以 ... 闭合 (librime LoadDictHeader 只认 ... 为 yaml 文档结束符,
    用 --- 闭合会把词条全吞进 header → 0 entries → 编译失败)"""
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Rime dictionary: %s\n" % name)
        f.write("# encoding: utf-8\n")
        f.write("#\n# 由 scripts/build.py 自动生成, 勿手改.\n#\n")
        f.write("---\n")
        f.write("name: %s\n" % name)
        f.write("version: \"%s\"\n" % version)
        f.write("sort: %s\n" % sort)
        if extra_header:
            f.write(extra_header)
        f.write("...\n")
        for e in entries:
            f.write(e + "\n")


def main():
    print("[1/6] 加载官方笔画码表 ...")
    char_map = load_stroke(os.path.join(DATA, "stroke_official.dict.yaml"))
    print("      汉字数:", len(char_map))

    print("[2/6] 加载词库 ...")
    jieba = load_jieba(os.path.join(DATA, "jieba_dict.txt"))
    print("      jieba (单字频次):", len(jieba), "词")
    rime_ice = load_rime_ice(os.path.join(DATA, "rime_ice_base.dict.yaml"))
    print("      雾凇 (词组):", len(rime_ice), "词")

    # ---- 单字表: 常用字 (GB2312), 频次用 jieba 单字频次 ----
    print("[3/6] 生成单字码表 (GB2312 常用字) ...")
    COMMON_CHARS = load_common_chars()
    base_entries = []
    skipped_base = {"illegal": 0, "long": 0, "not_common": 0}
    for ch, codes in char_map.items():
        for code in codes:
            # 过滤非法编码 (编码含非 hspnz 字符会触发 librime 编译异常/闪退)
            if not set(code) <= VALID_CODE_CHARS:
                skipped_base["illegal"] += 1
                continue
            # 过滤超长编码 (超出 max_code_length 的条目, 均为扩展区生僻字)
            if len(code) > MAX_CODE_LENGTH:
                skipped_base["long"] += 1
                continue
            # 过滤生僻字 (非 GB2312 常用字, iOS 字体不支持显示乱码)
            if ch not in COMMON_CHARS:
                skipped_base["not_common"] += 1
                continue
            f = jieba.get(ch, 1)
            # 高频无搭配单字: 权重加成 (打单字时不被词组碾压)
            if ch in HIGH_FREQ_SINGLE_BONUS:
                f *= SINGLE_BONUS_MULT
            base_entries.append(f"{ch}\t{code}\t{f}")
        # 标准笔顺补充: 同一字追加大陆标准笔顺编码 (两种都能打)
        if ch in STROKE_FIX and STROKE_FIX[ch] not in codes:
            base_entries.append(f"{ch}\t{STROKE_FIX[ch]}\t{jieba.get(ch, 1)}")
    # 按频次降序 (RIME by_weight 会重排, 这里排序只为确定性)
    base_entries.sort(key=lambda e: int(e.rsplit("\t", 1)[1]), reverse=True)
    write_dict(
        os.path.join(BUILD, "stroke_zh_base.dict.yaml"),
        "stroke_zh_base", "1.0.0", base_entries,
    )
    print("      单字条数:", len(base_entries),
          f"(跳过: 非法 {skipped_base['illegal']}, 超长 {skipped_base['long']}, 生僻 {skipped_base['not_common']})")

    # ---- 词组表 ----
    print("[4/6] 生成词组码表 ...")
    phrase_entries = []
    skipped = {"multi_char_skip": 0, "unknown_char": 0, "low_freq": 0, "non_cjk": 0, "long_code": 0, "rare_chars": 0}
    for word, f in rime_ice.items():
        n = len(word)
        if not (PHRASE_MIN_LEN <= n <= PHRASE_MAX_LEN):
            skipped["multi_char_skip"] += 1
            continue
        if f < PHRASE_MIN_FREQ:
            skipped["low_freq"] += 1
            continue
        # 过滤非纯汉字 (含数字/字母/标点则跳过)
        if not all("\u4e00" <= c <= "\u9fff" or "\u3400" <= c <= "\u4dbf" for c in word):
            skipped["non_cjk"] += 1
            continue
        try:
            # 取每字的第一个合法编码 (Conway 数据可能含 ? 等特殊标记)
            code = ""
            for ch in word:
                legal = [c for c in char_map[ch] if set(c) <= VALID_CODE_CHARS]
                if not legal:
                    raise KeyError(ch)
                code += legal[0]
        except (KeyError, IndexError):
            skipped["unknown_char"] += 1
            continue
        # 过滤超长编码 (超过 max_code_length 的词条可能触发编译异常)
        if len(code) > MAX_CODE_LENGTH:
            skipped["long_code"] += 1
            continue
        # 过滤含生僻字的词 (词内所有字须为 GB2312 常用字, 否则 iOS 显示乱码)
        if not all(c in COMMON_CHARS for c in word):
            skipped["rare_chars"] += 1
            continue
        phrase_entries.append(f"{word}\t{code}\t{f * PHRASE_WEIGHT_FACTOR}")
        # 简码: 每字前4笔拼接 (词组快打统一规则)
        # 完整编码要求打全前字笔画才能接下一字; 4笔简码歧义小 (多数词同码归零)
        short = "".join(
            next(c for c in char_map[ch] if set(c) <= VALID_CODE_CHARS)[:4] for ch in word
        )
        if len(short) <= MAX_CODE_LENGTH and short != code:
            phrase_entries.append(f"{word}\t{short}\t{f * PHRASE_WEIGHT_FACTOR}")
    phrase_entries.sort(key=lambda e: int(e.rsplit("\t", 1)[1]), reverse=True)
    write_dict(
        os.path.join(BUILD, "stroke_zh_phrase.dict.yaml"),
        "stroke_zh_phrase", "1.0.0", phrase_entries,
    )
    print("      词组条数:", len(phrase_entries))
    print("      跳过统计:", skipped)

    # ---- 主码表 ----
    print("[5/6] 生成主码表 ...")
    with open(os.path.join(BUILD, "stroke_zh.dict.yaml"), "w", encoding="utf-8") as f:
        f.write("# Rime dictionary: stroke_zh\n# encoding: utf-8\n#\n---\n")
        f.write("name: stroke_zh\n")
        f.write('version: "1.0.0"\n')
        f.write("sort: by_weight\n")
        f.write("import_tables:\n")
        f.write("  - stroke_zh_base\n")
        f.write("  - stroke_zh_phrase\n")
        # 自动造词: 上屏未收录词时按规则生成编码 (每字前4笔, 与简码规则一致)
        f.write("encoder:\n")
        f.write("  rules:\n")
        f.write("    - length_equal: 2\n")
        f.write('      formula: "AaAbAcAdBaBbBcBd"\n')
        f.write("    - length_equal: 3\n")
        f.write('      formula: "AaAbAcAdBaBbBcBdCaCbCcCd"\n')
        f.write("    - length_in_range: [4, 6]\n")
        f.write('      formula: "AaAbAcAdBaBbBcBdCaCbCcCdZaZbZcZd"\n')
        f.write("...\n")

    # ---- schema ----
    print("[6/6] 生成 schema ...")
    schema = f"""# Rime schema: {SCHEMA_ID}
# encoding: utf-8
#
# 笔画·增强: 五笔画 (横竖撇捺折) + 词组前缀联想
# 键位: h=s横 s=竖 p=撇 n=捺 z=折 (兼容 Mac 笔画排位 j/k/l/u/i)
# 基于官方 rime-stroke 码表 + jieba 词库词组表生成, 纯离线.
# 由 scripts/build.py 自动生成, 勿手改; 想调整去改脚本.

schema:
  schema_id: {SCHEMA_ID}
  name: "{SCHEMA_NAME}"
  version: "1.0.0"
  description: |
    五筆畫 (橫豎撇捺折) + 詞組聯想
    h,s,p,n,z = 橫、豎、撇、捺、折

switches:
  - name: ascii_mode
    reset: 0
    states: [ 中文, 西文 ]
  - name: full_shape
    states: [ 半角, 全角 ]
  - name: ascii_punct
    states: [ 。，, ．， ]
  - name: prediction
    states: [ 关闭预测, 开启预测 ]
    reset: 1

engine:
  processors:
    - predictor
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
    - predict_translator
    - reverse_lookup_translator
    - punct_translator
    - table_translator

predictor:
  # 上屏后预测下一个词 (librime-predict 插件, 元书需编译支持)
  db: predict.db
  max_candidates: 9      # 预测候选数 (与 page_size 一致, 避免句号翻页)
  max_iterations: 3      # 连续预测次数 (你→们→? 可连续多轮)

speller:
  alphabet: hspnz
  delimiter: " '"
  max_code_length: {MAX_CODE_LENGTH}

menu:
  page_size: 9

translator:
  dictionary: {SCHEMA_ID}
  enable_completion: true     # 前缀联想: 打几笔即出候选
  enable_user_dict: true      # 用户词典学习: 常用字/词自动前置
  enable_encoder: true        # 自动造词: 打词表没有的词(每字全码)上屏后自动收录进用户词典
  encode_commit_history: true # 造词时参考上屏上下文
  max_phrase_length: {PHRASE_MAX_LEN}
  preedit_format:
    - xlit/hspnz/一丨丿丶𠃍/   # 打字时编码显示笔画符号 (元书字体支持)
  comment_format:
    - xform/~//
    - xlit/hspnz/一丨丿丶𠃍/   # 候选词的剩余编码也显示笔画符号

punctuator:
  import_preset: default

reverse_lookup:
  dictionary: {SCHEMA_ID}
  enable_completion: true
  prefix: "`"
  suffix: "'"
  tips: 〔笔画〕

key_binder:
  import_preset: default
  bindings:
    # 兼容其他筆畫名稱 (捺屬點部、提屬橫部)
    - {{ when: always, accept: "d", send: "n" }}
    - {{ when: always, accept: "t", send: "h" }}
    # 兼容 Mac 筆畫輸入法按鍵: j橫 k豎 l撇 u捺 i折
    - {{ when: always, accept: "j", send: "h" }}
    - {{ when: always, accept: "k", send: "s" }}
    - {{ when: always, accept: "l", send: "p" }}
    - {{ when: always, accept: "u", send: "n" }}
    - {{ when: always, accept: "i", send: "z" }}

recognizer:
  import_preset: default
"""
    with open(os.path.join(BUILD, "stroke_zh.schema.yaml"), "w", encoding="utf-8") as f:
        f.write(schema)
    print("      schema 完成")

    # ---- 打包 ----
    zip_path = os.path.join(DIST, "stroke_zh.zip")
    files = [
        "stroke_zh.schema.yaml",
        "stroke_zh.dict.yaml",
        "stroke_zh_base.dict.yaml",
        "stroke_zh_phrase.dict.yaml",
    ]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in files:
            z.write(os.path.join(BUILD, fn), arcname=fn)
    print()
    print("=" * 50)
    print("完成! 打包: dist/stroke_zh.zip")
    for fn in files:
        print(f"  build/{fn}  ({os.path.getsize(os.path.join(BUILD, fn))/1024:.0f} KB)")
    print(f"  总包: {os.path.getsize(zip_path)/1024:.0f} KB")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
