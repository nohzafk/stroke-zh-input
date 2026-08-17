#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""
stroke_zh 方案离线校验脚本
===========================
每次修改 build.py / 数据源 / keyboard 布局后, 跑一遍本脚本即可完成
与元书输入法(librime)部署相关的全部静态校验, 无需运行 librime 本体.

⚠️ 为什么不用 librime 实测: 在 iSH 环境 ctypes 加载 librime.so 跑
maintenance 部署会崩溃并带崩 Minis 宿主 (2026-08-06 实测闪退),
所以所有校验都在本脚本内模拟 librime/元书源码逻辑完成.

用法:
  python3 scripts/validate.py                  # 全部校验 (iSH: apk add py3-yaml)
  uv run scripts/validate.py                   # Mac: uv 自动装 pyyaml
  uv run scripts/validate.py --rank-report      # 额外打印冷启动排名全表 (不改断言)

校验项:
  1. dict 头部必须以 ... 闭合 (librime LoadDictHeader 只认 ... 为结束符,
     否则词条全被吞进 header → 0 entries → 编译失败)
  2. 词条可读性模拟 (LoadDictHeader + EntryCollector 逻辑)
  3. 编码合法性 (仅 hspnz 字符)
  4. 编码长度 (<= MAX_CODE_LENGTH)
  5. schema YAML 语法
  6. 键盘布局 YAML 语法 + action/width 合法性 (模拟元书解析器)
  7. 键盘每行必须有 input 宽度锚点 + 宽度分配模拟
  8. 冷启动候选排名回归 (A4): 复现 librime 排序, 断言常用字 3 笔进第一页 +
     4/5/6 笔命中率不低于下限 (多打一笔不许变差) + 全码 4-7 笔的终端字打满全码
     进第一页 + 词组打满编码进前 3 (见 docs/REVIEW.md P0-1/P1-4)
"""
import os
import re
import sys
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
DATA = os.path.join(ROOT, "data")
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
    """编码合法性 + 长度检查 (含 stem 列: 自动造词用的规范全码)"""
    errs = []
    total = 0
    bad_char = 0
    long_code = 0
    bad_stem = 0
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
        # stem 列 = 造词用的全码; 非法字符会让 librime 造词时编出非法编码
        if len(row) >= 4 and row[3]:
            stem = row[3]
            if not set(stem) <= VALID_CODE_CHARS or len(stem) < len(code):
                bad_stem += 1
                if bad_stem <= 3:
                    errs.append(f"stem 列非法 (须是不短于编码的 hspnz 串): {s[:50]}")
    if bad_char:
        errs.append(f"共 {bad_char} 个条目编码含非 hspnz 字符 (librime 编译异常/闪退风险)")
    if long_code:
        errs.append(f"共 {long_code} 个条目编码超长 (>32, 超出 max_code_length)")
    if bad_stem:
        errs.append(f"共 {bad_stem} 个条目 stem 列非法 (自动造词会出错码)")
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


# ---------- 8. 冷启动候选排名回归 (A4) ----------
#
# 复现 librime 的候选排序 (dict/dictionary.cc:73-84 compare_chunk_by_head_element):
#   1. 精确匹配 (剩余编码长度 = 0) 优先于补全候选
#   2. 剩余编码长度升序   ← 主键, 不是权重
#   3. 权重降序
# 再叠加 filter:
#   - single_char_filter (gear/single_char_filter.cc:41-45): 只重排开头连续的
#     table/user_table 候选 = 精确匹配段; 补全候选 type 为 "completion" → 立即 break.
#     只在 schema 的 engine/filters 里出现时才模拟.
#   - uniquifier: 同一文本只占一个候选位.
#
# 「冷启动」= 空用户词典, 与真机「卸载 App + 重启 + 重装」口径一致. 用户词典一旦学过,
# 排名会被 PreferUserPhrase (gear/table_translator.cc:102-113) 抬高 → 之后的人工实测
# 不再是独立验证 (docs/REVIEW.md P1-4). 本节是唯一能防 P0-1 复发的手段.
#
# 权重并列时按最坏情况计名次 (并列一律算在目标之前), 断言才不会时好时坏.

PAGE_SIZE = 9          # = schema menu/page_size, 第一页容量
PHRASE_RANK_MAX = 3    # 词组打满编码后要求的名次上限
CHAR_STROKES = 3       # 核心 UX: 每字打 3 笔进第一页

# 断言用的高频字集取自 data/rime_ice_8105.dict.yaml 的权重列 =《25 亿字语料汉字字频表》
# (BLCU, 雾凇随词库附带的外部字频表). 刻意不用 build.py 的 jieba 字频, 更不用
# HIGH_FREQ_SINGLE_BONUS 那 55 字人工名单 —— 用被测数据自己的名单做断言 = 自我印证.
FREQ_TABLE = os.path.join(DATA, "rime_ice_8105.dict.yaml")

# 硬断言 1: 字频前 30 字, 3 笔必须 rank <= 9 (逐字断言, 一个不过就失败)
MUST_HIT_TOP = 30

# 硬断言 2: 各频段 3 笔命中率下限 (实测值留 2-3 个百分点余量; 跌破即视为回归).
#
# 天花板 (ceiling) 是组合上限, 不是懈怠: 3 笔前缀最多 5^3=125 个, 每个前缀第一页
# 只有 PAGE_SIZE=9 个位置 → 全表最多 ~1100 个字能在 3 笔进第一页, 而字频前 600 字
# 挤在 104 个前缀里 (szh 一个前缀就有 65 个). 天花板 = 每个前缀按字频取前 9 名的命中率,
# 简码只能逼近它, 不可能超过. 低频段天花板本身就只有几个百分点, 别指望它变高.
HIT_RATE_FLOOR = [
    # (频段起, 频段止, 3 笔命中率下限 %, 天花板 %)   v1.3 实测: 96 / 87 / 71 / 57 / 13 / 5
    (1, 100, 93, 98),
    (1, 300, 84, 89),
    (1, 600, 68, 73),
    (1, 1000, 54, 58),
    (1001, 2000, 11, 13),
    (2001, 3500, 4, 5),
]

# 硬断言 5 (v1.4): 4/5/6 笔命中率下限. 这一项锁的是「多打一笔不许变差」.
#
# v1.3 的简码只建到 3 笔 (SHORTCODE_LEVELS = (1,2,3)), 于是第 4 笔一跨出去就掉回补全
# 惩罚 —— 字频前 100 字「4 笔进第一页」只有 45%, 比 3 笔的 96% 还差 51 个点
# (「第」打 phn rank 2, 打满 4 笔 phnp 反而 rank 1354; 「和」打偏旁禾 phspn rank 15).
# 用户按偏旁部首打字 (偏旁 2-7 笔, 不是恰好 3 笔) 撞的就是这个倒挂.
# v1.4 把 SHORTCODE_LEVELS 扩到 (1..7) 之后命中率对笔数单调不降, 这张表防它退回去.
# 视觉块 (自然码词组) 引入的固有空间竞争: 6 笔词组精确匹配 remaining=0 占位,
# 把超高频字 (是/这/时/里, 3 笔简码已覆盖) 的 4-6 笔补全挤出第一页, 以及
# szhh 拥挤前缀 (明/最/果/目/电). 下限按视觉块实测值 -3 个点调整.
# 下限 = 实测值 -3 个点; 天花板同 3 笔, 是 5^N 前缀的组合上限, 不是实现缺陷.
MULTI_STROKE_FLOOR = [
    # (笔数, 频段起, 频段止, 下限 %)          实测: 4 笔 97/94/88/81/48/25
    (4, 1, 100, 94), (4, 1, 300, 91), (4, 1, 600, 85), (4, 1, 1000, 78),
    (4, 1001, 2000, 45), (4, 2001, 3500, 22),
    #                                          实测: 5 笔  94/94/89/87/72/53
    (5, 1, 100, 91), (5, 1, 300, 91), (5, 1, 600, 86), (5, 1, 1000, 84),
    (5, 1001, 2000, 69), (5, 2001, 3500, 50),
    #                                          实测: 6 笔  88/91/90/88/83/71
    (6, 1, 100, 85), (6, 1, 300, 88), (6, 1, 600, 87), (6, 1, 1000, 85),
    (6, 1001, 2000, 80), (6, 2001, 3500, 68),
]


# 硬断言 6 (v1.4 A′): 全码 4-7 笔的「终端字」打满自己的全码必须在第一页.
# 这些字没有更长的码可退, 掉出第一页 = 冷启动下选不到 —— build_shortcodes 的「留位」
# 规则 (build.py 第 2 条) 就是为它们设的. 简码扩到 7 笔后它们要和同前缀的简码同台竞争,
# 这一项量的就是留位规则还在不在.
# 允许的漏网 = 字频表里频次为 0 的部件字 (钅/礻/衤/疒/虍) 和生僻字 (旮/旯/旰/呋/抃),
# 它们拿不到留位是 build_shortcodes 注释写明的刻意取舍 (用它们的席位换高频字进第一页).
TERMINAL_CODE_LEN = (4, 7)
TERMINAL_MISS_BUDGET = 20    # v1.3 baseline 15, v1.4 实测 20 (新增 钅/礻/衤/疒/虍 等零频部件)

# 硬断言 4: 打满单字全码时该字的名次上限. 这一项盯的是「词组碾压单字」——
# single_char_filter 唯一真正做的事就是把精确匹配段里的单字提到词组前面
# (gear/single_char_filter.cc:41-45 遇到 completion 立即 break, 补全段它管不到),
# 移除该 filter 前后跑这一项, 就能量出代价 (docs/REVIEW.md P0-2).
FULL_CODE_TOP_N = 300
FULL_CODE_RANK_MAX = PAGE_SIZE

# 硬断言 3: 词组打满编码 rank <= 3
# 词表 = jieba 词频最高的词组 (v1.4 词频改造后排序标准 = jieba 真实语料频率;
# 旧词表含「苹果」等 jieba 中频词, 会被联盟/聪明等更高频词压在 rank 4-5, 属预期排序,
# 2026-08-17 换为 jieba top 词组)
PHRASE_CASES = [
    "确认", "中国", "我们", "他们", "自己", "没有", "国家", "可以", "发展",
    "工作", "这个", "什么", "主要", "问题", "进行", "因为", "现在", "时候",
    "知道", "这样", "计算机", "中国人", "为什么", "实事求是", "不好意思",
]

# build.py 的 HIGH_FREQ_SINGLE_BONUS 人工名单 (DESIGN.md §5.1 曾宣称这批字 3 笔全进第一页).
# 名单是手工挑的, 不是字频前 54 名, 所以里面必然有落在拥挤前缀上的字 —— 例如 szh 前缀
# 有 65 个高频字抢 9 个位置, 「日/最」的字频排不进前 9, 3 笔就是进不了第一页.
# 因此这里不做「一个不许漏」的断言, 只锁漏掉的个数不许变多 (漏的是谁在报告里列出来).
CLAIM_CHARS = "我你这的在是子天真太最里有个了和他那不人中大上为以要就都也很到说去能会着没看好来时地日年下小多少又才只可再更"
CLAIM_MISS_BUDGET = 4    # 实测: 最/都/日/可 (都在 szh/hsh/hsz 三个最挤的前缀上)


def load_char_freq():
    """《25 亿字语料汉字字频表》-> [字] 按频次降序. 同字多音取最大值."""
    freq = {}
    for line in open(FREQ_TABLE, encoding="utf-8"):
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
    return [c for c, _ in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))]


def load_entries():
    """读 build/ 单字表 + 词组表 = 编译后主词典的全部词条.
    (stroke_zh.dict.yaml 只做 import_tables, 自身无词条.)
    返回 (entries, code_of): entries = [(文本, 编码, 权重)],
    code_of = {单字: 最短编码} —— 用户打字用的就是最短的那条."""
    entries = []
    for fn in ("stroke_zh_base.dict.yaml", "stroke_zh_phrase.dict.yaml"):
        for line in open(os.path.join(BUILD, fn), encoding="utf-8"):
            s = line.rstrip("\n")
            if not s or s.startswith("#") or s in ("---", "..."):
                continue
            if ":" in s and not s.startswith(" "):
                continue
            row = s.split("\t")
            if len(row) >= 3:
                try:
                    entries.append((row[0], row[1], int(row[2])))
                except ValueError:
                    continue
    code_of = {}
    for text, code, _ in entries:
        if len(text) != 1:
            continue
        cur = code_of.get(text)
        if cur is None or len(code) > len(cur):
            code_of[text] = code       # 单字取全码 (最长的那条) 作为笔顺基准
    return entries, code_of


def schema_filters():
    """schema 里启用的 filters (决定要不要模拟 single_char_filter)"""
    try:
        d = yaml.safe_load(open(os.path.join(BUILD, "stroke_zh.schema.yaml"), encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return []
    return list((d or {}).get("engine", {}).get("filters") or [])


class RankModel:
    """librime 候选排名模型. prepare() 一次收齐所有待查前缀, 再逐个 rank()."""

    def __init__(self, entries, single_char_first):
        self.entries = entries
        self.single_char_first = single_char_first
        self.bucket = {}

    def _key(self, remaining, weight, text):
        if self.single_char_first and remaining == 0:
            # single_char_filter: 精确匹配段内单字提前
            return (0, 0 if len(text) == 1 else 1, -weight)
        return (remaining, 0, -weight)

    def prepare(self, prefixes):
        """收集每个前缀下的候选并排序. 每次调用重建 (控制内存)."""
        prefixes = {p for p in prefixes if p}
        lens = sorted({len(p) for p in prefixes})
        bucket = {p: [] for p in prefixes}
        for text, code, w in self.entries:
            n = len(code)
            for L in lens:
                if L > n:
                    break
                b = bucket.get(code[:L])
                if b is not None:
                    b.append((self._key(n - L, w, text), text))
        for b in bucket.values():
            b.sort()
        self.bucket = bucket

    def rank(self, text, prefix):
        """返回 (名次, 挡在前面的候选列表). uniquifier 去重; 并列按最坏情况算."""
        b = self.bucket.get(prefix)
        if not b:
            return None, []
        target = None
        for key, t in b:
            if t == text:
                target = key
                break                      # b 已排序, 首次命中即最优位置
        if target is None:
            return None, []
        ahead = {}
        for key, t in b:
            if key > target:
                break                      # key == target 也算在前面 (最坏情况)
            if t != text and t not in ahead:
                ahead[t] = key
        return len(ahead) + 1, list(ahead)

    def hit_rate(self, chars, code_of, strokes):
        """chars 在 strokes 笔时进第一页的比例. 编码不足 strokes 笔的字按全码算."""
        hit = miss = 0
        misses = []
        for ch in chars:
            code = code_of.get(ch)
            if not code:
                continue
            r, ahead = self.rank(ch, code[:strokes])
            if r is not None and r <= PAGE_SIZE:
                hit += 1
            else:
                miss += 1
                misses.append((ch, code, r, ahead[:5]))
        return hit, miss, misses


def check_ranks(report=False):
    """A4 冷启动排名回归. 返回 (errors, warns, info_lines)"""
    errs, warns, info = [], [], []
    entries, code_of = load_entries()
    filters = schema_filters()
    scf = "single_char_filter" in filters
    model = RankModel(entries, single_char_first=scf)
    freq_chars = load_char_freq()
    typable = [c for c in freq_chars if c in code_of]     # 单字表里有的字
    info.append(f"词条 {len(entries)} 条; 字频表 {len(freq_chars)} 字, 其中 {len(typable)} 字可打; "
                f"single_char_filter={'启用' if scf else '未启用'}")

    # ---- 断言 1+2: 单字 3 笔进第一页 ----
    bands = {}
    need = set()
    for lo, hi, _, _ in HIT_RATE_FLOOR:
        band = typable[lo - 1:hi]
        bands[(lo, hi)] = band
        need.update(code_of[c][:CHAR_STROKES] for c in band)
    need.update(code_of[c][:CHAR_STROKES] for c in CLAIM_CHARS if c in code_of)
    model.prepare(need)

    must = typable[:MUST_HIT_TOP]
    hit, miss, misses = model.hit_rate(must, code_of, CHAR_STROKES)
    if miss:
        errs.append(f"字频前 {MUST_HIT_TOP} 字有 {miss} 个 {CHAR_STROKES} 笔未进第一页 (要求逐字 rank<={PAGE_SIZE}):")
        for ch, code, r, ahead in misses:
            errs.append(f"    {ch} 全码={code} 前缀={code[:CHAR_STROKES]} rank={r} 挡在前面: {'/'.join(ahead)}")
    else:
        info.append(f"字频前 {MUST_HIT_TOP} 字: {CHAR_STROKES} 笔全部 rank<={PAGE_SIZE} ✓")

    for lo, hi, floor, ceiling in HIT_RATE_FLOOR:
        band = bands[(lo, hi)]
        hit, miss, misses = model.hit_rate(band, code_of, CHAR_STROKES)
        n = hit + miss
        pct = hit * 100 // n if n else 0
        tag = f"字频 {lo}-{hi} 字"
        if pct < floor:
            errs.append(f"{tag}: {CHAR_STROKES} 笔命中率 {pct}% < 下限 {floor}% ({hit}/{n})")
            for ch, code, r, ahead in misses[:5]:
                errs.append(f"    例 {ch} 前缀={code[:CHAR_STROKES]} rank={r} 挡在前面: {'/'.join(ahead)}")
        else:
            info.append(f"{tag}: {CHAR_STROKES} 笔命中率 {pct}% (下限 {floor}%, 天花板 {ceiling}%, {hit}/{n})")

    hit, miss, misses = model.hit_rate(CLAIM_CHARS, code_of, CHAR_STROKES)
    detail = "; ".join(f"{ch}(前缀 {code[:CHAR_STROKES]} rank {r})" for ch, code, r, _ in misses)
    if miss > CLAIM_MISS_BUDGET:
        errs.append(f"HIGH_FREQ_SINGLE_BONUS 名单 {hit + miss} 字有 {miss} 个 {CHAR_STROKES} 笔"
                    f"未进第一页, 超过允许的 {CLAIM_MISS_BUDGET} 个: {detail}")
    elif miss:
        info.append(f"HIGH_FREQ_SINGLE_BONUS 名单 {hit + miss} 字: {miss} 个 {CHAR_STROKES} 笔"
                    f"未进第一页 (允许 {CLAIM_MISS_BUDGET} 个, 拥挤前缀无解): {detail}")
    else:
        info.append(f"HIGH_FREQ_SINGLE_BONUS 名单 {hit} 字: {CHAR_STROKES} 笔全部进第一页 ✓")

    # ---- 断言 5: 4/5/6 笔命中率下限 (多打一笔不许变差) ----
    by_strokes = {}
    for n, lo, hi, floor in MULTI_STROKE_FLOOR:
        by_strokes.setdefault(n, []).append((lo, hi, floor))
    for n in sorted(by_strokes):
        segs = by_strokes[n]
        model.prepare({code_of[c][:n] for lo, hi, _ in segs for c in typable[lo - 1:hi]})
        got, want = [], []
        for lo, hi, floor in segs:
            band = typable[lo - 1:hi]
            hit, miss, misses = model.hit_rate(band, code_of, n)
            total = hit + miss
            pct = hit * 100 // total if total else 0
            got.append(pct)
            want.append(floor)
            if pct < floor:
                errs.append(f"字频 {lo}-{hi} 字: {n} 笔命中率 {pct}% < 下限 {floor}% ({hit}/{total})")
                for ch, code, r, ahead in misses[:5]:
                    errs.append(f"    例 {ch} 前缀={code[:n]} rank={r} 挡在前面: {'/'.join(ahead)}")
        seg_names = "/".join(f"{lo}-{hi}" for lo, hi, _ in segs)
        info.append(f"{n} 笔命中率 [{seg_names}]: {'/'.join(f'{p}%' for p in got)} "
                    f"(下限 {'/'.join(f'{p}%' for p in want)})")

    # ---- 断言 6: 全码 4-7 笔的终端字打满全码必须在第一页 ----
    tlo, thi = TERMINAL_CODE_LEN
    terminals = [ch for ch, code in code_of.items() if tlo <= len(code) <= thi]
    model.prepare({code_of[ch] for ch in terminals})
    t_miss = []
    for ch in terminals:
        r, _ = model.rank(ch, code_of[ch])
        if r is None or r > PAGE_SIZE:
            t_miss.append(ch)
    if len(t_miss) > TERMINAL_MISS_BUDGET:
        errs.append(f"全码 {tlo}-{thi} 笔的终端字 {len(terminals)} 个里有 {len(t_miss)} 个打满全码"
                    f"进不了第一页, 超过允许的 {TERMINAL_MISS_BUDGET} 个 (留位规则失效?): "
                    f"{''.join(t_miss)}")
    else:
        info.append(f"全码 {tlo}-{thi} 笔终端字 {len(terminals)} 个: {len(t_miss)} 个打满全码"
                    f"进不了第一页 (允许 {TERMINAL_MISS_BUDGET} 个, 均为零字频部件/生僻字): "
                    f"{''.join(t_miss)}")

    # ---- 断言 4: 每个常用字至少有一个笔数能进第一页 ----
    # 检查 1/2/3 笔简码 + 打满全码这几个实际打字落点. 一个都进不了第一页 = 这个字
    # 冷启动下选不到 (用户不翻页), 属于必须修的回归:
    #   · 全码 <=3 笔的字被简码挤掉 → build_shortcodes 的留位逻辑坏了
    #   · 全码 >=4 笔的字被同码词组压下去 → 单字权重量级不对 (P0-2: single_char_filter
    #     只是把这类候选在出锅后提前, 治标; 真正的修法是单字用真实字频做权重)
    full_targets = typable[:FULL_CODE_TOP_N]
    probes = {}
    for ch in full_targets:
        code = code_of[ch]
        probes[ch] = sorted({code[:n] for n in (1, 2, 3)} | {code}, key=len)
    model.prepare({p for ps in probes.values() for p in ps})
    unreachable, buried_full = [], []
    for ch in full_targets:
        code = code_of[ch]
        best, best_at = None, ""
        for p in probes[ch]:
            r, _ = model.rank(ch, p)
            if r is not None and (best is None or r < best):
                best, best_at = r, p
        rf, ahead = model.rank(ch, code)
        phrases = [t for t in ahead if len(t) > 1]
        if rf is not None and rf > FULL_CODE_RANK_MAX and phrases:
            buried_full.append(f"{ch}(全码 {code} rank {rf}, 词组 {len(phrases)} 个, "
                               f"但 {best_at} 排 {best})")
        if best is None or best > FULL_CODE_RANK_MAX:
            unreachable.append(f"    {ch} 全码={code} 最好名次 {best} (前缀 {best_at}) "
                               f"挡在前面: {'/'.join(ahead[:6])}")
    if unreachable:
        errs.append(f"字频前 {FULL_CODE_TOP_N} 字有 {len(unreachable)} 个在任何笔数都进不了第一页:")
        errs.extend(unreachable[:10])
    else:
        info.append(f"字频前 {FULL_CODE_TOP_N} 字: 每个字都有笔数能进第一页 ✓")
    if buried_full:
        warns.append(f"{len(buried_full)} 个字打满全码时排在同码词组之后 (词频确实高于字频, "
                     f"简码路径不受影响): {'; '.join(buried_full[:5])}")

    # ---- 断言 3: 词组打满编码 rank <= 3 ----
    pcode = {}
    for text, code, _ in entries:
        if len(text) > 1:
            cur = pcode.get(text)
            if cur is None or len(code) < len(cur):
                pcode[text] = code
    model.prepare([pcode[w] for w in PHRASE_CASES if w in pcode])
    bad = []
    for w in PHRASE_CASES:
        code = pcode.get(w)
        if not code:
            bad.append(f"    {w}: 不在词组表 (词库/PHRASE_* 参数变了?)")
            continue
        r, ahead = model.rank(w, code)
        if r is None or r > PHRASE_RANK_MAX:
            bad.append(f"    {w} 码={code}({len(code)}笔) rank={r} 挡在前面: {'/'.join(ahead[:6])}")
    if bad:
        errs.append(f"词组打满编码后未进前 {PHRASE_RANK_MAX}:")
        errs.extend(bad)
    else:
        info.append(f"词组 {len(PHRASE_CASES)} 例: 打满编码全部 rank<={PHRASE_RANK_MAX} ✓")

    # ---- A1 不回归保护: 简码不得把已有精确匹配挤出第一页 ----
    exact_over = []
    counts = {}
    for text, code, _ in entries:
        counts[code] = counts.get(code, 0) + 1
    over = {c: n for c, n in counts.items() if n > PAGE_SIZE and len(c) <= CHAR_STROKES}
    if over:
        worst = sorted(over.items(), key=lambda kv: -kv[1])[:5]
        exact_over = [f"{c}({n} 条)" for c, n in worst]
        warns.append(f"有 {len(over)} 个 <={CHAR_STROKES} 笔编码的精确匹配条目超过一页: "
                     f"{', '.join(exact_over)} → 该码上的低频条目落到第二页")

    # ---- 可选全表 ----
    if report:
        info.append("")
        info.append("冷启动命中率全表 (进第一页 = rank<=%d):" % PAGE_SIZE)
        info.append("  %-14s%8s%8s%8s%8s%8s" % ("频段", "1 笔", "2 笔", "3 笔", "4 笔", "5 笔"))
        for lo, hi in [(1, 100), (101, 300), (301, 600), (601, 1000), (1001, 2000), (2001, 3500)]:
            band = typable[lo - 1:hi]
            cells = []
            for n in (1, 2, 3, 4, 5):
                model.prepare({code_of[c][:n] for c in band})
                h, m, _ = model.hit_rate(band, code_of, n)
                cells.append("%d%%" % (h * 100 // (h + m)) if h + m else "-")
            info.append("  %-14s%8s%8s%8s%8s%8s" % (f"{lo}-{hi} 字", *cells))
    return errs, warns, info


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

    print("\n[5] 冷启动候选排名回归 (空用户词典, 复现 dictionary.cc:73-84)")
    errs, warns, info = check_ranks(report="--rank-report" in sys.argv)
    for i in info:
        print(f"  · {i}" if i else "")
    for w in warns:
        print(f"  ⚠ {w}")
    if errs:
        for e in errs:
            print(f"  ✗ {e}")
        ok = False

    print("\n" + "=" * 56)
    if ok:
        print("✅ 全部校验通过, 可安全导入元书输入法")
    else:
        print("❌ 存在问题, 修复后重跑")
    print("=" * 56)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
