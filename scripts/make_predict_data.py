#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 librime-predict 预测数据 (key\tvalue\tweight) — GB2312 常用字过滤版.
逻辑复刻 librime-predict/tools/make_predict_data:
  - 词 "你好" → key="你" value="好"
  - 词 "你好吗" → key="你" value="好吗"; key="你好" value="吗"
  - 高频单字作句子开始: key="$" value=字
过滤: 只保留 GB2312 常用字词 (predict 候选干净, 无生僻字)
输出: stdout, 供 Mac 端 build_predict 生成 predict.db
"""
import sys


def load_common_chars():
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
MIN_FREQ = 50       # 参与预测的词最低词频 (过滤罕见词)
MAX_WORD_LEN = 4    # 参与拆分的词最大长度
JIEBA = "/var/minis/shared/rime-stroke-zh/data/jieba_dict.txt"


def main() -> int:
    data: dict[str, dict[str, int]] = {}

    def add(key: str, value: str, weight: int) -> None:
        d = data.setdefault(key, {})
        if value not in d or d[value] < weight:
            d[value] = weight

    # 句子开始预测: 高频单字 (GB2312)
    single_freq: dict[str, int] = {}
    for line in open(JIEBA, encoding="utf-8-sig"):
        parts = line.rstrip("\n").split()
        if len(parts) >= 2 and len(parts[0]) == 1 and parts[0] in COMMON:
            try:
                single_freq[parts[0]] = max(single_freq.get(parts[0], 0), int(parts[1]))
            except ValueError:
                pass
    for ch, w in sorted(single_freq.items(), key=lambda x: -x[1])[:100]:
        add("$", ch, w)

    # 词 → bigram (GB2312 词)
    for line in open(JIEBA, encoding="utf-8-sig"):
        parts = line.rstrip("\n").split()
        if len(parts) < 2:
            continue
        word, w_str = parts[0], parts[1]
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
