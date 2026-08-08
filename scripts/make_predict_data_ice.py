#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 librime-predict 预测数据 (key\tvalue\tweight) — 雾凇词库版, GB2312 过滤.

逻辑 (与 2026-08-06 jieba 版一致, 后缀拆分 — 重要!):
  - 词 "下面" → key="下" value="面"
  - 词 "下一页" → key="下" value="一页"; key="下一" value="页"
  - 高频单字作句子开始: key="$" value=字
librime-predict 候选为 0 宽度后缀, 点击只上屏后缀 → "下"+"面"="下面" 不重复.

数据源: rime_ice_base.dict.yaml (雾凇基础词库, 格式: 词\\t编码\\t词频)
用法: python3 make_predict_data_ice.py > predict_data_ice.txt
      (Mac 端) build_predict predict.db < predict_data_ice.txt
"""
import sys

def load_common_chars():
    """GB2312 全部 6763 汉字 (PingFang SC 可显示, 预测候选干净)."""
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
    return set(dict.fromkeys(chars))


COMMON = load_common_chars()
MIN_FREQ = 100       # 参与预测的词最低词频 (雾凇词频体系)
MAX_WORD_LEN = 4     # 参与拆分的词最大长度
ICE = "data/rime_ice_base.dict.yaml"   # 雾凇基础词库


def main() -> int:
    data: dict[str, dict[str, int]] = {}

    def add(key: str, value: str, weight: int) -> None:
        d = data.setdefault(key, {})
        if value not in d or d[value] < weight:
            d[value] = weight

    # 句子开始预测: 高频单字 (GB2312)
    single_freq: dict[str, int] = {}
    for line in open(ICE, encoding="utf-8"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 3 and len(parts[0]) == 1 and parts[0] in COMMON:
            try:
                single_freq[parts[0]] = max(single_freq.get(parts[0], 0), int(parts[2]))
            except ValueError:
                pass
    for ch, w in sorted(single_freq.items(), key=lambda x: -x[1])[:100]:
        add("$", ch, w)

    # 词 → 后缀拆分 (GB2312 词)
    for line in open(ICE, encoding="utf-8"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 3:
            continue
        word, w_str = parts[0], parts[2]
        try:
            w = int(w_str)
        except ValueError:
            continue
        if w < MIN_FREQ:
            continue
        n = len(word)
        if n < 2 or n > MAX_WORD_LEN:
            continue
        if not all(c in COMMON for c in word):
            continue
        for i in range(1, n):
            add(word[:i], word[i:], w)

    for key in sorted(data):
        for value, weight in sorted(data[key].items(), key=lambda x: -x[1]):
            print(f"{key}\t{value}\t{weight}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
