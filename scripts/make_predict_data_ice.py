#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 librime-predict 预测数据 (key\tvalue\tweight) — 雾凇词库版, GB2312 过滤.

逻辑 (与 2026-08-06 jieba 版一致, 后缀拆分 — 重要!):
  - 词 "下面" → key="下" value="面"
  - 词 "下一页" → key="下" value="一页"; key="下一" value="页"
  - 高频单字作句子开始: key="$" value=字
librime-predict 候选为 0 宽度后缀, 点击只上屏后缀 → "下"+"面"="下面" 不重复.

数据源: rime_ice_base.dict.yaml (雾凇基础词库, 格式: 词\\t编码\\t词频)
权重 (v1.4 改造, 2026-08-17): 双库词 (jieba 词库也有) 用 jieba 词频 — 真实语料频率,
常用预测词靠前; 雾凇独有词 (jieba 无) 保留, 线性缩放到 jieba 量级 (独有 p50 对齐
双库 jieba p50, 与 build.py 词组权重同法). 过滤仍按雾凇词频 MIN_FREQ (规模不变).
用法: python3 make_predict_data_ice.py > predict_data_ice.txt
      (Mac 端) build_predict predict.db < predict_data_ice.txt
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import load_jieba, load_rime_ice, p50   # noqa: E402 (复用词库加载, 无副作用)

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

    # 预测权重: 双库词用 jieba 词频, 独有词缩放 (与 build.py 词组权重同法, 见文件头注释)
    jieba = load_jieba(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "data", "jieba_dict.txt"))
    ice = load_rime_ice(ICE)
    both_freqs = [jieba[w] for w, f in ice.items() if w in jieba and f >= MIN_FREQ]
    only_freqs = [f for w, f in ice.items() if w not in jieba and f >= MIN_FREQ]
    scale = p50(both_freqs) / p50(only_freqs)
    print(f"# predict weights: 双库 jieba p50={p50(both_freqs)}, "
          f"独有缩放系数={scale:.4f}", file=sys.stderr)

    def weight(word: str, rime_w: int) -> int:
        return jieba[word] if word in jieba else max(1, round(rime_w * scale))

    # 句子开始预测: 高频单字 (GB2312)
    single_freq: dict[str, int] = {}
    for line in open(ICE, encoding="utf-8"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 3 and len(parts[0]) == 1 and parts[0] in COMMON:
            try:
                single_freq[parts[0]] = max(single_freq.get(parts[0], 0),
                                            weight(parts[0], int(parts[2])))
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
        w = weight(word, w)
        for i in range(1, n):
            add(word[:i], word[i:], w)

    for key in sorted(data):
        for value, weight in sorted(data[key].items(), key=lambda x: -x[1]):
            print(f"{key}\t{value}\t{weight}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
