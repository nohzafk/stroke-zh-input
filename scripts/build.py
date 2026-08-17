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
  - stroke_zh_phrase.dict.yaml      词组码表 (雾凇词库, 每字前4笔拼接, 带频次)
  - stroke_zh.dict.yaml             主码表 (import 单字+词组)
  - stroke_zh.schema.yaml           方案配置 (单 translator + 高频字简码分流)
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
PHRASE_MAX_LEN = 4      # 词组最大字数 (5/6 字词要打 20/24 笔, 无实用性, v1.3 起不收)
PHRASE_MIN_FREQ = 50   # 词组过滤阈值: 雾凇权重列 (rime_ice_base.dict.yaml 权重, 非 jieba)
                        # 控制词组表规模, 调低则词多. (历史注释曾写「jieba 词频阈值」,
                        # 但过滤条件一直是雾凇权重 — 2026-08-17 核对代码后修正注释)

# 词组权重 (v1.4 改造, 2026-08-17):
#   - 双库词 (jieba 词库也有): 直接用 jieba 词频 — 真实语料频率, 常用词靠前
#   - 雾凇独有词 (jieba 没有): 保留, 线性缩放到 jieba 量级 (独有词 p50 = 双库词 jieba p50),
#     不挤压 jieba 常用词; 独有词之间保持原雾凇相对顺序
#   - 废弃 PHRASE_WEIGHT_FACTOR×10: 单字用字频表 10^5~10^7, 候选排序主键是剩余编码长度,
#     词组打满编码即剩余 0 必在首位, 同码决胜时 jieba 高频词组仍领先多数单字, 无需放大.
#     同码竞争例: 「日月」与「明」同码, 字频表单字权重高 → 打「明」8 笔出「明」, 正确.
PHRASE_CODE_STROKES = 4  # 仅 encoder 公式兜底用 (v1.4 词组编码已改自然码; 造词优先走 stem 列,
                            # 公式只在 stem 缺失时触发, 实际不生效 — 见 encoder_rules 注释)
PHRASE_MIN_CODE_LEN = 6  # 词组编码最短笔数. librime 排序主键是剩余编码长度升序:
                         # 输入 N 笔时, 编码恰好 N 笔的词条精确匹配 (remaining=0) 永远排在
                         # 全码更长的单字补全候选前 (权重只是次级键). v1.4 自然码 3-5 笔 →
                         # 2字词最短 6 笔, 4-5 笔词组(一个/一只)会抢占单字 4-5 笔前缀,
                         # 把或/事/眼 等挤出第一页 (实测 4 笔命中率 98%→94%). v1.3 词组
                         # 固定 8 笔所以无此问题. 6-7 笔词组权重另行打折 (见词组生成处).
PHRASE_SHORT_FREQ_THRESHOLD = 10000  # 4-5 笔码高频词组放行阈值 (jieba 词频).
                         # 「第一」(第4笔+一1笔=5笔码) 等超高频词被排除线误杀 → 放行.
                         # 阈值 10000 = 22 个日常必打词 (一个/一些/一般/一定/第一/一下/
                         # 一次/一直/一起/一点…); 低于阈值的不放行 (仍保护单字前缀).
MAX_CODE_LENGTH = 32    # 编码长度上限 (4字词=16笔, 单字全码最长 13 笔, 留余量)

# ---- 高频字简码 (A1) ----
# librime 候选排序主键是「剩余编码长度升序」, 不是权重 (dict/dictionary.cc:73-84):
# 打 3 笔时, 全码 8 笔的常用字只是 remaining=5 的补全候选, 被任何剩余码更短的条目
# (含大量词组) 压在后面 —— 实测「是」打 szh 排第 9096 位, 真机验证一致.
# 唯一的解法是把该笔数本身作为精确匹配条目写进词库 (= 五笔/郑码/仓颉的简码).
#
# v1.4 (A′): 级别从 (1,2,3) 扩到 (1..7). v1.3 只建到 3 笔, 于是第 4 笔一跨出去就掉回
# 补全惩罚 —— 字频前 100 字「4 笔进第一页」只有 45%, 比 3 笔的 96% 还差 51 个点
# (「第」打 phn rank 2, 打 phnp rank 1354; 「和」打偏旁禾 phspn rank 15). 这不是「容忍
# 不标准笔数」的可选优化, 是「多打一笔反而更差」的设计倒挂: 用户按偏旁部首打字,
# 偏旁是 2-7 笔, 不是恰好 3 笔. 扩到 7 笔后前 100 字 4 笔 45%→100%、5 笔 63%→98%、
# 6 笔 78%→100%, 命中率对笔数单调不降, 由 validate.py MULTI_STROKE_FLOOR 锁住.
# (以上口径 = validate.py 的累计频段 + hit_rate, 跑 validate.py 即可复现.)
#
# 为什么是 7 笔封顶: 偏旁本身最多 6-7 笔 (⺮ 6, 金 8 已极少), 再长的前缀落在 5^8 以上的
# 稀疏码空间里, 补全候选本来就排得进第一页 (6 笔命中率已到 100%), 再扩只是加死条目;
# 且 8 笔正是二字词组码的长度, 不扩到 8 笔就不会与词组抢同一个精确匹配码.
# 为什么不用 speller/algebra 的 abbrev (原生缩写机制): algebra 对整个词典生效, 没有按
# 条目收窄的语法, 而词组码与单字全码在长度上完全重叠 → 30 万词组会全部在 1-4 笔变成
# 精确匹配 = P0-1 完全复发. 拆词典又会重演 v1.1 (部署只编译顶层 translator 的词典).
# 实测加词条的 prism 成本与 abbrev 相同 (distinct code 只 +3,884), abbrev 省的只有 table.
SHORTCODE_LEVELS = (1, 2, 3, 4, 5, 6, 7)  # 简码级别: 取该字真实笔顺的前 1..7 笔
PAGE_SIZE = 9                 # = schema menu/page_size, 第一页容量
# 权重剥离的笔数上限. **必须独立于 SHORTCODE_LEVELS**, 不能复用 max(SHORTCODE_LEVELS):
# 下面那处剥离是把 <=3 笔条目的权重统一压成纯字频 (去掉 HIGH_FREQ_SINGLE_BONUS 的 ×100),
# 目的是让最挤的 1-3 笔前缀严格按字频排序. 扩到 7 笔后若跟着一起走, 4-7 笔的**全码**
# 也会被剥离 —— 「我」的全码正好 7 笔且在加成名单里, 权重会掉 100 倍.
BONUS_STRIP_MAX_LEN = 3
# 发简码的名额按前缀算, 不按字频前 N 名算: 每个前缀第一页只有 PAGE_SIZE 个位置,
# 名额给该前缀下字频最高的字 (全码等于该前缀的字先留位, 见 build_shortcodes).
# 进不了第一页的简码是死条目 (用户不翻页), 所以不发. 这样「szh 前缀有 65 个高频字」
# 这种拥挤前缀不会浪费名额, 3 笔前缀稀疏的中低频字也能拿到简码 —— 比「只发字频前
# 1000 字」覆盖得更准 (实测 1017 条简码, 字频 1-600 段 3 笔命中率 19% → 71%).

# 拼音方案产物 (stroke_zh_plus.zip 用; 由 scripts/build_pinyin.py 生成)
PINYIN_FILES = ["pinyin_lite.schema.yaml", "pinyin_lite.dict.yaml"]

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


def load_char_freq(path):
    """《25 亿字语料汉字字频表》(BLCU) -> {字: 频次}.

    数据在 data/rime_ice_8105.dict.yaml 的权重列里 (雾凇随 8105 单字表附带,
    出处见该文件头部注释). 用它决定「哪些字发简码、简码之间怎么排序」——
    jieba 的单字项是分词词典的副产物, 不是字频表; 而 HIGH_FREQ_SINGLE_BONUS
    那 55 字是手工名单, 名单外的字享受不到任何排序优待 (docs/REVIEW.md P2-12).
    同字多音取最大值.
    """
    freq = {}
    for line in open(path, encoding="utf-8"):
        s = line.rstrip("\n")
        if not s or s.startswith("#") or s in ("---", "..."):
            continue
        if ":" in s and not s.startswith(" "):
            continue
        row = s.split("\t")
        if len(row) >= 3 and len(row[0]) == 1:
            try:
                w = int(row[2])
            except ValueError:
                continue
            if w > freq.get(row[0], 0):
                freq[row[0]] = w
    return freq


def build_shortcodes(char_codes, freq, blocked):
    """高频字简码 (A1): 按 SHORTCODE_LEVELS 给字追加简码条目, 每个前缀发 PAGE_SIZE 个名额.

    简码条目让该字在该笔数上成为**精确匹配** (剩余码长 0), 按
    dict/dictionary.cc:78-79 排在所有补全候选之前 —— 这才是「打几笔就上屏」的实现手段,
    前缀联想 + 字频排序做不到 (DESIGN.md §4.1 旧结论错误, 见 docs/REVIEW.md P1-5).
    v1.4 (A′) 把级别从 (1,2,3) 扩到 (1..7), 本函数逻辑不变 —— 配额/留位/扣位三条规则
    在 4-7 笔上同样成立, 见 SHORTCODE_LEVELS 的注释.

    名额分配 (同一前缀 PAGE_SIZE 个位置, 先扣占位, 余额按字频发):
      1. blocked[前缀]: 同码词组条目 (权重量级压过字频, 抢不动) 先扣掉;
      2. 全码正好等于该前缀的字 (十/口/工/士…) 留位: 这些字**没有更长的编码可退**,
         被挤出第一页就等于打满全码也选不到, 所以无条件占一个位置;
      3. 余额按字频降序发给该前缀下全码更长的字 —— 它们进不了第一页还能多打几笔.
    这样 blocked + 留位 + 简码 <= PAGE_SIZE, 该码上每个有字频的条目都在第一页.
    字频表里没有的字 (囗/扌 这类在 25 亿字语料里出现 0 次的部件) 不留位, 会落到
    第二页 —— 用它们的位置换「日/最」这种高频字进第一页, 是刻意的取舍.

    权重取字频表原值 = 全部 <=3 笔编码统一按《25 亿字语料汉字字频表》排序 (调用方
    对已有的 <=3 笔全码条目做同样的换算), 所以同一前缀第一页就是字频前 9 名,
    不会再出现「囗/扌 这种零频字占位、日/最 落到第二页」.

    参数: char_codes {字: 全码}, freq {字: 字频}, blocked {前缀: 词组精确匹配条目数}
    返回 (entries, stats): entries = [(字, 简码, 权重)]
    """
    ranked = [c for c in sorted(freq, key=lambda c: (-freq[c], c)) if c in char_codes]
    entries = []
    stats = {}
    for level in SHORTCODE_LEVELS:
        groups = defaultdict(list)
        reserved = defaultdict(int)
        for ch in ranked:                       # ranked 已按字频降序 → 组内自然有序
            code = char_codes[ch]
            if len(code) > level:
                groups[code[:level]].append(ch)
            elif len(code) == level:
                reserved[code] += 1             # 全码就是该前缀, 留位
        n = 0
        for prefix, cands in groups.items():
            slots = PAGE_SIZE - blocked.get(prefix, 0) - reserved.get(prefix, 0)
            for ch in cands[:max(slots, 0)]:
                entries.append((ch, prefix, freq[ch]))
                n += 1
        stats[level] = n
    return entries, stats


def encoder_rules():
    """自动造词公式兜底 (v1.4): 主路径是 stem 列 (自然码, 见 base_entries 的 stem),
    UnityTableEncoder::TranslateWord 查到 stem 就直接用, 公式只在 stem 缺失时兜底.
    公式仍是「每字前 4 笔」展开 (AaAb…), 与 v1.4 自然码不同 — 但 base 表 stem 列
    对每个字都有值 (natural_code or 全码兜底), 公式路径实际不触发, 保留作安全网.
    """
    letters = "ABCDEFGHIJKLMNOPQRST"           # 不用 U~Z: 那些是倒数索引
    strokes = "abcdefghijklmnopqrstuvwxyz"[:PHRASE_CODE_STROKES]
    rules = []
    for n in range(PHRASE_MIN_LEN, PHRASE_MAX_LEN + 1):
        rules.append((n, "".join(letters[i] + s for i in range(n) for s in strokes)))
    return rules


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


# ============ 自然码 (v1.4 视觉块输入) ============
# 每字一个自然码 = 整字全码的前缀, 由首部件决定:
#   首部件 3~5 笔 → 打全部件 (确=石5笔, 明=日4笔, 当=⺌3笔)
#   首部件 >5 笔或独体 → 打前 4 笔 (我/国/笔)
#   首部件 <=2 笔 → 打前 4 笔 (认=讠人凑块, 们=亻门5笔由部件规则兜底)
# 用户视觉块停笔 = 首部件或整块; 词组 = 每字自然码 + 空格分隔 (拼音式多音节).
# 依据: 用户实测 (2026-08-17) 确/当/笔/认/们/我/第 的自然停笔规律.

# 常用偏旁部首 (终止表): 拆字拆到这些就停 (部件 = 视觉块)
BUSHOU = {
    "一": 1, "人": 2, "亻": 2, "讠": 2, "阝": 2, "冫": 2, "亠": 2, "丷": 2,
    "十": 2, "八": 2, "儿": 2, "几": 2, "刀": 2, "力": 2, "又": 2, "厶": 2,
    "氵": 3, "扌": 3, "宀": 3, "艹": 3, "辶": 3, "口": 3, "土": 3, "女": 3,
    "小": 3, "山": 3, "尸": 3, "广": 3, "门": 3, "彳": 3, "犭": 3, "饣": 3,
    "弓": 3, "马": 3, "子": 3, "寸": 3, "工": 3, "大": 3, "也": 3, "夕": 3,
    "木": 4, "日": 4, "月": 4, "火": 4, "王": 4, "心": 4, "礻": 4, "斤": 4,
    "见": 4, "车": 4, "贝": 4, "水": 4, "牛": 4, "手": 4, "毛": 4, "气": 4,
    "片": 4, "父": 4, "爪": 4, "风": 4, "斗": 4, "文": 4, "方": 4, "云": 4,
    "元": 4, "天": 4, "太": 4, "少": 4, "户": 4, "支": 4, "不": 4, "止": 4,
    "歹": 4, "比": 4, "中": 4, "石": 5, "田": 5, "禾": 5, "白": 5, "皮": 5,
    "目": 5, "衤": 5, "钅": 5, "疒": 5, "立": 5, "穴": 5, "皿": 5, "生": 5,
    "矢": 5, "示": 5, "瓜": 5, "鸟": 5, "龙": 5, "母": 5, "本": 5, "术": 5,
    "正": 5, "甘": 5, "世": 5, "古": 5, "电": 5, "甲": 5, "申": 5, "由": 5,
    "竹": 6, "米": 6, "羊": 6, "羽": 6, "耳": 6, "臣": 6, "自": 6, "至": 6,
    "舌": 6, "舟": 6, "衣": 6, "西": 6, "页": 6, "血": 6, "虫": 6, "行": 6,
    "色": 6, "言": 7, "走": 7, "足": 7, "酉": 7, "辛": 7, "辰": 7, "身": 7,
    "谷": 7, "角": 7, "里": 7, "金": 8, "鱼": 8, "雨": 8, "青": 8, "其": 8,
    "齿": 8, "隹": 8, "骨": 9, "鬼": 9, "食": 9, "音": 9, "首": 9, "高": 10,
    "黑": 12, "鹿": 11,
}

_chaizi_map = None


def load_chaizi():
    """加载拆字表 (data/chaizi-jt.txt, kfcd/chaizi) -> {字: 首部件}"""
    global _chaizi_map
    if _chaizi_map is not None:
        return _chaizi_map
    _chaizi_map = {}
    path = os.path.join(DATA, "chaizi-jt.txt")
    if not os.path.exists(path):
        return _chaizi_map
    for line in open(path, encoding="utf-8"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 2 and len(parts[0]) == 1:
            comps = parts[1].split()
            if comps:
                _chaizi_map.setdefault(parts[0], comps[0])
    return _chaizi_map


def first_component(ch, char_codes):
    """返回 (首部件, 有效笔画数). 递归拆到偏旁表或不可拆.
    首部件 <=2 笔 (主→丶) 用户不会按它停 → 退回整字 (按整字全码长处理)."""
    split_map = load_chaizi()
    cur = ch
    seen = set()
    for _ in range(6):
        if cur in BUSHOU:
            n = BUSHOU[cur]
            if n >= 3:
                return cur, n
            return ch, len(char_codes.get(ch, "")) or 0
        if cur in seen:
            break
        seen.add(cur)
        nxt = split_map.get(cur)
        if not nxt or nxt == cur:
            break
        cur = nxt
    return cur, len(char_codes.get(ch, "")) or 0


def natural_code(ch, char_codes):
    """每字自然码 = 整字全码前 N 笔. 查不到码返回 None (该字不参与词组)."""
    code = char_codes.get(ch)
    if not code:
        return None
    _comp, n = first_component(ch, char_codes)
    if n <= 2:
        N = 4
    elif n <= 5:
        N = n
    else:
        N = 4
    N = min(N, len(code))
    return code[:N]


def load_char_codes():
    """字 -> 第一个合法编码 (与 main 生成 char_codes 同逻辑).
    typing_test.py 复用: 单字自然码 = natural_code(ch, load_char_codes())"""
    char_map = load_stroke(os.path.join(DATA, "stroke_official.dict.yaml"))
    char_codes = {}
    for ch, codes in char_map.items():
        for code in codes:
            if set(code) <= VALID_CODE_CHARS:
                char_codes.setdefault(ch, code)
                break
    return char_codes


def p50(vals):
    """中位数 (空列表返回 1, 防除零)"""
    if not vals:
        return 1
    s = sorted(vals)
    return s[len(s) // 2]


def resolve(fn):
    """产物文件的实际路径: build/ 优先, 其次仓库根 (predict.db 放在根目录)"""
    for base in (BUILD, ROOT):
        p = os.path.join(base, fn)
        if os.path.exists(p):
            return p
    return None


def pack_zip(zip_name, files):
    """打包 dist/<zip_name>. files 里的每一项都必须存在, 缺一个就报错.

    为什么必须硬失败: predict.db 曾长期只靠「手动加回 zip」这一步补进产物, 结果
    dist/stroke_zh.zip 发出去时不含 predict.db → 纯笔画方案完全没有上屏预测,
    而文档把预测写成已验证特性 (docs/REVIEW.md P0-3). 手动步骤一定会漏, 改成构建期断言.
    """
    missing = []
    srcs = []
    for fn in files:
        p = resolve(fn)
        if p:
            srcs.append((p, fn))
        else:
            missing.append(fn)
    if missing:
        hint = ""
        if any(f.startswith("pinyin_lite") for f in missing):
            hint = " (先跑 python3 scripts/build_pinyin.py)"
        if "predict.db" in missing:
            hint = " (先按 docs/PREDICT.md 生成 predict.db)"
        raise SystemExit(f"✗ 打包 {zip_name} 失败: 缺少 {', '.join(missing)}{hint}")
    with zipfile.ZipFile(os.path.join(DIST, zip_name), "w", zipfile.ZIP_DEFLATED) as z:
        for p, arcname in srcs:
            z.write(p, arcname=arcname)


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
    os.makedirs(BUILD, exist_ok=True)
    os.makedirs(DIST, exist_ok=True)

    print("[1/8] 加载官方笔画码表 ...")
    char_map = load_stroke(os.path.join(DATA, "stroke_official.dict.yaml"))
    print("      汉字数:", len(char_map))

    print("[2/8] 加载词库 ...")
    jieba = load_jieba(os.path.join(DATA, "jieba_dict.txt"))
    print("      jieba (单字频次):", len(jieba), "词")
    rime_ice = load_rime_ice(os.path.join(DATA, "rime_ice_base.dict.yaml"))
    print("      雾凇 (词组):", len(rime_ice), "词")
    char_freq = load_char_freq(os.path.join(DATA, "rime_ice_8105.dict.yaml"))
    print("      字频表 (25 亿字语料):", len(char_freq), "字")

    # 词组权重缩放系数: 雾凇独有词 (jieba 没有的词) 原权重 p50≈1040, 双库词 jieba
    # 词频 p50≈7, 量级差 2-3 个数量级. 不缩放则独有词整体挤压 jieba 常用词.
    # 线性缩放 (独有词 p50 对齐双库词 jieba p50) 保持独有词之间相对顺序.
    both_freqs = [jieba[w] for w, f in rime_ice.items()
                  if w in jieba and f >= PHRASE_MIN_FREQ]
    only_freqs = [f for w, f in rime_ice.items()
                  if w not in jieba and f >= PHRASE_MIN_FREQ]
    PHRASE_SCALE = p50(both_freqs) / p50(only_freqs)
    # 词组整体提权: jieba 词频 p50≈7 vs 单字字频表 p50≈4200, 差 ~600 倍. 不放大则
    # 打满编码时 (同码条目全部剩余 0, 纯权重决胜) 任何词组都输给单字字频表 —
    # 例: 「苹果」码与生僻字「昔」同码, jieba 1334 被字频表 10^5 秒杀 → rank 5;
    # 放大后 80 万 > 10 万, 「昔」不再挡路, 词组之间仍按 jieba 词频相对排序.
    SCALE_UP = p50(list(char_freq.values())) / p50(both_freqs)
    print(f"      词组权重: 双库 jieba p50={p50(both_freqs)}"
          f", 独有缩放系数={PHRASE_SCALE:.4f}"
          f", 提权系数={SCALE_UP:.0f} (对齐单字字频表 p50={p50(list(char_freq.values()))})")

    # ---- 单字表: 常用字 (GB2312), 权重用《25 亿字语料汉字字频表》----
    # 为什么不用 jieba 单字频次: jieba 的单字项是分词词典的副产物, 量级只有 10^3~10^5,
    # 而同码词组权重是 jieba 词频×10 (10^5~10^8) → 单字全码被同码词组整页压下去.
    # 实测移除 single_char_filter 后, 字频前 300 字里「明」打满全码排 41 位 (前面 40 个词组).
    # single_char_filter 只是在候选出锅后把精确匹配段的单字提前, 掩盖了权重量级不对这个
    # 真正的病因 (docs/REVIEW.md P0-2/P2-12). 改用真实字频 (10^5~10^7) 后单字与词组同量级,
    # 按真实使用频率排序, 不需要任何「单字优先」的特殊规则.
    print("[3/8] 生成单字码表 (GB2312 常用字) ...")
    COMMON_CHARS = load_common_chars()
    # (字, 编码) -> 权重. 同一对只留最大权重 (简码可能与全码重合, 如「十」的 2 笔简码)
    base_codes = {}
    char_codes = {}          # 字 -> 全码 (第一个合法编码, 与词组取码规则一致)
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
            f = char_freq.get(ch) or jieba.get(ch, 1)   # 字频表缺字时退回 jieba
            # 高频无搭配单字: 权重加成 (打单字时不被词组碾压)
            if ch in HIGH_FREQ_SINGLE_BONUS:
                f *= SINGLE_BONUS_MULT
            base_codes[(ch, code)] = max(base_codes.get((ch, code), 0), f)
            char_codes.setdefault(ch, code)
        # 标准笔顺补充: 同一字追加大陆标准笔顺编码 (两种都能打)
        if ch in STROKE_FIX and STROKE_FIX[ch] not in codes and ch in COMMON_CHARS:
            key = (ch, STROKE_FIX[ch])
            base_codes[key] = max(base_codes.get(key, 0),
                                  char_freq.get(ch) or jieba.get(ch, 1))
    print("      单字条数:", len(base_codes),
          f"(跳过: 非法 {skipped_base['illegal']}, 超长 {skipped_base['long']}, 生僻 {skipped_base['not_common']})")

    # ---- 词组表 ----
    print("[4/8] 生成词组码表 ...")
    phrase_entries = []
    skipped = {"multi_char_skip": 0, "unknown_char": 0, "low_freq": 0, "non_cjk": 0,
               "long_code": 0, "rare_chars": 0, "short_code": 0}
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
        # 词组编码 (v1.4 视觉块): 每字自然码**连续拼接** (无空格!).
        # 为什么无空格: librime 编译词典时空格=多音节=拆成多个音节分别进 prism 键集合
        # (entry_collector.cc: CreateEntry 按空格 split raw_code, 逐个 syllabary.insert),
        # table_translator 只做整键前缀匹配不组合音节 → 空格编码的词组在 prism 里无整键,
        # 用户实测"确认打不出来、候选全是单字" (2026-08-17).
        # 连续串 = 单个超长音节 = 整键进 prism = 前缀匹配直接出词 (v1.3 的成熟机制).
        # 用户连续打自然码 (每字自然停笔 3~5 笔) 即出词, 无需切分键.
        codes = []
        for ch in word:
            nc = natural_code(ch, char_codes)
            if not nc:
                codes = None
                break
            codes.append(nc)
        if codes is None:
            skipped["unknown_char"] += 1
            continue
        short = "".join(codes)
        if len(short.replace(" ", "")) < PHRASE_MIN_CODE_LEN:
            # A 方案 (v1.4): 超高频短码词放行 (jieba 词频≥阈值), 否则跳过.
            # 「第一/一个/一些」是用户必打词, 码长 4-5 笔撞排除线 → 误杀.
            # 放行词权重仍走 ≤7 笔 ×0.001 折扣, 不压单字前缀 (见下方打折).
            if word in jieba and jieba[word] >= PHRASE_SHORT_FREQ_THRESHOLD:
                pass
            else:
                skipped["short_code"] += 1      # 一人/十一/一一 …… 占短前缀槽位, 不收
                continue
        if len(short) <= MAX_CODE_LENGTH:
            if word in jieba:
                w = jieba[word]                    # 双库词: jieba 真实语料词频 (常用词靠前)
            else:
                w = f * PHRASE_SCALE               # 雾凇独有词: 缩放 (p50 对齐, 不挤压常用词)
            w = max(1, round(w * SCALE_UP))        # 提到单字量级 (同码决胜不被字频表碾压)
            # 4-7 笔词组权重打折 (×0.001): 自然码 3-5 笔 → 2字词最短 6 笔, 与单字
            # 6-7 笔全码同码决胜. 不打折则词组(jieba×717 几千万)碾压单字(字频表几百万),
            # 终端字打满全码掉出第一页 (实测 78 个: 挂/彩/韩…被土地/地址/城墙压).
            # 打折后单字第一、词组仍在第一页; 8+ 笔码与单字空间隔离, 不打折.
            # A 方案放行词 (4-5 笔高频短码词) 例外: 不打折 (jieba×717 全权重),
            # 否则「第一」被竹头单字(笑/第/等 字频百万)压到 rank 9 (第一页末位).
            # 放行词仅 22 个超高频词, 用户打它们就是想出词, 提权合理.
            if len(short) <= 7 and not (word in jieba and jieba[word] >= PHRASE_SHORT_FREQ_THRESHOLD):
                w = max(1, round(w * 0.001))
            phrase_entries.append((word, short, w))
    print("      词组条数:", len(phrase_entries))
    print("      跳过统计:", skipped)

    # ---- 高频字简码 (A1) ----
    print("[5/8] 生成高频字简码 ...")
    # 短前缀上不参与字频竞争的精确匹配条目 = 同码词组 (权重是词频×系数, 量级压过字频).
    # 这里跟着 SHORTCODE_LEVELS 走: 扩到 7 笔后, 4-7 笔的 15,436 个词组码会自动计入扣位,
    # 简码就抢不到它们的席位 —— 实测 top3000 词组打满编码的名次零变化.
    blocked = defaultdict(int)
    for _word, code, _w in phrase_entries:
        if len(code) <= max(SHORTCODE_LEVELS):
            blocked[code] += 1
    short_entries, short_stats = build_shortcodes(char_codes, char_freq, blocked)
    # 全部 <=BONUS_STRIP_MAX_LEN 笔的单字条目 (简码 + 本来就这么短的全码) 统一换成字频权重:
    # 同一前缀的精确匹配段这样才是按字频排序. 原来的 jieba 权重量级只有几万,
    # 会让「囗(权重 2)/扌(21)」这类零频字压在「日/最」前面占掉第一页.
    # 用 BONUS_STRIP_MAX_LEN 而不是 max(SHORTCODE_LEVELS): 理由见该常量的注释.
    for (ch, code) in list(base_codes):
        if len(code) <= BONUS_STRIP_MAX_LEN:
            base_codes[(ch, code)] = max(char_freq.get(ch, 0), 1)
    for ch, code, w in short_entries:
        key = (ch, code)
        base_codes[key] = max(base_codes.get(key, 0), w)
    print("      简码条数:", len(short_entries),
          "(" + ", ".join(f"{k} 笔 {v}" for k, v in sorted(short_stats.items())) + ")")

    # ---- 落盘 (按权重降序, RIME by_weight 会重排, 这里排序只为确定性) ----
    # stem 列 = 该字的全码 (v1.4 视觉块修正). librime 造词时 UnityTableEncoder::TranslateWord
    # 先查 stem, 查到后由 TableEncoder::Encode 按公式取码 (公式 AaAb… 固定取每字前 4 笔) —
    # stem 必须 >= 公式取码位数, 否则 3 笔自然码的字 (当/展/问) 公式取第 4 笔会越界.
    # 全码长度 (6-30 笔) 恒 >= 4, 造词安全. 词组表是自然码连续串 (每字自然停笔),
    # 自动造词是公式 4 笔制 — 两个体系并存: 词库词打自然码, 新学的词打 4 笔 (词库已覆盖日常).
    # 没有 stem 列时它会枚举该字的全部编码 (含简码) 做 DFS, 而 DFS 上限只有 32 个组合
    # (algo/encoder.cc:15), 3/4 字词会被截断 → 学不到正确的码, 还会塞一堆短码垃圾条目.
    base_entries = [f"{ch}\t{code}\t{w}\t{char_codes.get(ch, code)}"
                    for (ch, code), w in
                    sorted(base_codes.items(), key=lambda kv: (-kv[1], kv[0][1], kv[0][0]))]
    write_dict(
        os.path.join(BUILD, "stroke_zh_base.dict.yaml"),
        "stroke_zh_base", "1.0.0", base_entries,
        extra_header="columns:\n  - text\n  - code\n  - weight\n  - stem\n",
    )
    phrase_lines = [f"{w_}\t{c}\t{f}" for w_, c, f in
                    sorted(phrase_entries, key=lambda e: (-e[2], e[1], e[0]))]
    write_dict(
        os.path.join(BUILD, "stroke_zh_phrase.dict.yaml"),
        "stroke_zh_phrase", "1.0.0", phrase_lines,
    )
    print(f"      单字表 {len(base_entries)} 条 (含简码), 词组表 {len(phrase_lines)} 条")

    # ---- 主码表 ----
    print("[6/8] 生成主码表 ...")
    with open(os.path.join(BUILD, "stroke_zh.dict.yaml"), "w", encoding="utf-8") as f:
        f.write("# Rime dictionary: stroke_zh\n# encoding: utf-8\n#\n---\n")
        f.write("name: stroke_zh\n")
        f.write('version: "1.0.0"\n')
        f.write("sort: by_weight\n")
        f.write("import_tables:\n")
        f.write("  - stroke_zh_base\n")    # 单字表
        f.write("  - stroke_zh_phrase\n")  # 词组表 (必须 import: librime 部署只编译 import 链,
                                           # 独立 translator 词典不会被编译 → 词组会消失)
        # 自动造词: 上屏未收录词时按规则生成编码 (逐字展开, 与词组编码规则同源)
        f.write("encoder:\n")
        f.write("  rules:\n")
        for n, formula in encoder_rules():
            f.write(f"    - length_equal: {n}\n")
            f.write(f'      formula: "{formula}"\n')
        f.write("...\n")

    # ---- schema ----
    print("[7/8] 生成 schema ...")
    schema = f"""# Rime schema: {SCHEMA_ID}
# encoding: utf-8
#
# 笔画·增强: 五笔画 (横竖撇捺折) + 高频字 1~7 笔简码 + 词组(每字自然码+切分)
# 键位: h=s横 s=竖 p=撇 n=捺 z=折 (兼容 Mac 笔画排位 j/k/l/u/i)
# 基于官方 rime-stroke 码表 + 雾凇词库词组表生成, 纯离线.
# 由 scripts/build.py 自动生成, 勿手改; 想调整去改脚本.
#
# v1.4 词组改视觉块自然码 (v1.3 之后首个发布版, 含词频/A′ 演进) (每字按首部件自然停笔), 编码 = 自然码 + 空格.
# 升级**必须清空用户词典** (编码格式从每字4笔变自然码+切分).

schema:
  schema_id: {SCHEMA_ID}
  name: "{SCHEMA_NAME}"
  version: "1.4.0"
  description: |
    五筆畫 (橫豎撇捺折) + 高頻字簡碼(1~7筆) + 詞組(每字自然碼)
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
  filters:
    # uniquifier: 去重 (同一词不会因全码/简码/用户词典重复占位)
    #
    # 这里**故意不用 single_char_filter**: 它只重排开头连续的 table/user_table 候选,
    # 遇到第一个 completion 类型的候选就 break (gear/single_char_filter.cc:41-45),
    # 而 table_translator 给一切「剩余编码非 0」的候选都打 completion 标记
    # (gear/table_translator.cc:82-85) → 前缀联想段它一个字也管不到.
    # 它管得到的只有精确匹配段, 而实测字频前 300 字打满全码时前面根本没有词组
    # (validate.py 断言 4, 词组码是每字 4 笔, 与单字全码几乎不撞), 收益为 0.
    # 留着只会让人误以为「单字优先」已解决, 掩盖真正的手段 = 简码 (A1).
    - uniquifier

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
  enable_encoder: true        # 自动造词: 打词表没有的词(每字前4笔)上屏后自动收录进用户词典
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
    print("[8/8] 打包 dist/ ...")
    scheme_files = [
        "stroke_zh.schema.yaml",
        "stroke_zh.dict.yaml",
        "stroke_zh_base.dict.yaml",
        "stroke_zh_phrase.dict.yaml",
        "predict.db",          # 上屏预测库 (缺失即构建失败, 见 pack_zip)
    ]
    zips = [
        ("stroke_zh.zip", scheme_files),
        ("stroke_zh_plus.zip", scheme_files + PINYIN_FILES),
    ]
    for zip_name, files in zips:
        pack_zip(zip_name, files)
    print()
    print("=" * 50)
    print("完成!")
    for fn in scheme_files:
        p = resolve(fn)
        print(f"  {os.path.relpath(p, ROOT)}  ({os.path.getsize(p)/1024:.0f} KB)")
    for zip_name, _ in zips:
        print(f"  dist/{zip_name}  ({os.path.getsize(os.path.join(DIST, zip_name))/1024:.0f} KB)")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
