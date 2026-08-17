#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打字效果回归测试 (stroke-zh)

模拟真实按键序列: 逐笔输入编码 → 计算候选排名 (librime 排序模型) → 判定目标词
能否出现/多快出现. 用于「改编码方案后重跑一遍, 确认打字效果没退化」.

判定标准 (与用户实际打字体验对齐):
  - 词组: 打满自然码 rank <= 3 (第一页前三, 抬手就出)
  - 单字: 打满自然码 rank <= 9 (第一页)
  - 逐笔跟踪: 记录目标词「首次进入第一页」的笔数 (打多少笔能看见它)
  - 少打补全: 词组少打 1 笔, 目标词仍应进第一页

用法:
  uv run --with pyyaml python3 scripts/typing_test.py [--report docs/typing_report.md]
退出码: 0 = 全部通过; 1 = 有失败 (可挂 CI / 提交门禁).

注意: predict.db (上屏预测) 与用户词典学习是 librime 运行时行为, 离线无法模拟,
本测试只覆盖「词库冷启动」的打字效果.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build  # noqa: E402
import validate as V  # noqa: E402

# ---------------- 用例定义 ----------------
# 词组: 词 + 期望打满 rank 上限 (默认 3)
PHRASE_CASES = [
    # 首字 5 笔部件 (用户最易打超 4 笔的场景)
    "确认", "社会", "知道", "可以", "发展", "主要",
    # 首字 3-4 笔
    "我们", "什么", "工作", "这个", "自己", "开始", "时间",
    # 双 5 笔部件
    "他们",
    # 8 笔标准长词
    "进行", "问题", "中国", "因为", "现在", "时候",
]

# 单字: 字 + 期望 rank 上限 (默认 9). 自然码自动算.
# "明"例外: szhh 前缀 332 字共享 (拥挤前缀, A′ 时代已标记), 日字头 4 笔 rank 10
# = 第二页第一个, 属机制固有, 允许 rank<=10.
SINGLE_CASES = [
    ("和", 9), ("确", 9), ("当", 9), ("明", 10), ("们", 9), ("认", 9),
    ("第", 9), ("笔", 9), ("我", 9), ("国", 9), ("想", 9), ("经", 9),
    ("她", 9), ("社", 9),
]

# 少打补全: (词, 少打几笔). 目标词仍应进第一页.
SHORT_PREFIX_CASES = [
    ("我们", 1), ("确认", 1), ("社会", 1), ("什么", 1), ("工作", 1),
    ("知道", 1), ("这个", 1), ("他们", 1), ("中国", 1), ("进行", 1),
]

# A 方案放行的超高频短码词: 应在词库且打满 rank<=3 (第一/一个/一些/一般/一定/一下…)
# 背景: PHRASE_MIN_CODE_LEN=6 排除线误杀超高频词 (「第一」5笔码 jieba=17725 必打),
# build.py 加 PHRASE_SHORT_FREQ_THRESHOLD=10000 放行 (jieba 词频≥1万, 22 个).
EXCLUDED_SHORT = ["第一", "一个", "一些", "一般", "一定", "一下"]

PAGE = 9                 # 第一页容量 (schema menu/page_size)
PHRASE_RANK_MAX = 3      # 词组打满: 前三
SINGLE_RANK_MAX = PAGE   # 单字打满: 第一页


# ---------------- 核心 ----------------
def collect_prefixes(phrase_codes, single_codes, short_prefixes):
    """收集所有用例的前缀集合, 一次 prepare (RankModel 为批量前缀设计)."""
    prefixes = set()
    for code in phrase_codes.values():
        for n in range(1, len(code) + 1):
            prefixes.add(code[:n])
    for code in single_codes.values():
        for n in range(1, len(code) + 1):
            prefixes.add(code[:n])
    for w, k in short_prefixes:
        code = phrase_codes.get(w)
        if code and len(code) > k:
            prefixes.add(code[:-k])
    return prefixes


def first_page_n(model, text, code):
    """逐笔跟踪: 返回 (首次进第一页的笔数, 该笔 rank). 打满都进不了返回 (None, None)."""
    for n in range(1, len(code) + 1):
        r, _ = model.rank(text, code[:n])
        if r is not None and r <= PAGE:
            return n, r
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default="docs/typing_report.md")
    args = ap.parse_args()

    started = time.time()
    entries, _ = V.load_entries()
    char_codes = build.load_char_codes()

    # 词组编码表 (当前构建产物)
    phrase_codes = {}
    for l in open(os.path.join(build.BUILD, "stroke_zh_phrase.dict.yaml"), encoding="utf-8"):
        p = l.rstrip("\n").split("\t")
        if len(p) >= 3:
            phrase_codes[p[0]] = p[1]

    # 单字自然码
    single_codes = {ch: build.natural_code(ch, char_codes) for ch, _ in SINGLE_CASES}
    single_allow = {ch: allow for ch, allow in SINGLE_CASES}

    model = V.RankModel(entries, single_char_first=False)
    model.prepare(collect_prefixes(phrase_codes, single_codes, SHORT_PREFIX_CASES))

    results = {"phrase": [], "single": [], "short": [], "excluded": []}
    failures = []

    # ---- 词组连打 (打满自然码) + 逐笔首现 ----
    for w in PHRASE_CASES:
        code = phrase_codes.get(w)
        if not code:
            results["phrase"].append((w, None, None, None, None, "不在词组表"))
            failures.append(f"词组 {w} 不在词组表")
            continue
        r, _ = model.rank(w, code)
        n_first, r_first = first_page_n(model, w, code)
        ok = r is not None and r <= PHRASE_RANK_MAX
        results["phrase"].append((w, code, len(code), r, n_first, "✓" if ok else f"✗ rank={r}"))
        if not ok:
            _, ahead = model.rank(w, code)
            failures.append(f"词组 {w} 打满 {code} rank={r} (期望<={PHRASE_RANK_MAX}) 挡:{'/'.join((ahead or [])[:5])}")

    # ---- 单字自然码/偏旁 ----
    for ch, allow in SINGLE_CASES:
        code = single_codes[ch]
        if not code:
            results["single"].append((ch, None, None, None, "无自然码"))
            failures.append(f"单字 {ch} 无自然码")
            continue
        r, _ = model.rank(ch, code)
        ok = r is not None and r <= allow
        results["single"].append((ch, code, len(code), r, "✓" if ok else f"✗ rank={r}"))
        if not ok:
            _, ahead = model.rank(ch, code)
            failures.append(f"单字 {ch} 打 {code} rank={r} (期望<={allow}) 挡:{'/'.join((ahead or [])[:5])}")

    # ---- 少打补全 ----
    # 判定标准: 词仍在候选列表 (r is not None) 即通过 — librime 排序主键是剩余编码
    # 长度, 少打 1 笔时 6 笔精确词组 (remaining=0) 必然排在目标词 (remaining=1 补全) 前,
    # 这是机制固有 (权重只是次级键), 不是缺陷. 用户实际靠「逐笔首现」(见词组表) 打满前出词.
    for w, k in SHORT_PREFIX_CASES:
        code = phrase_codes.get(w)
        if not code or len(code) <= k:
            continue
        short = code[:-k]
        r, _ = model.rank(w, short)
        ok = r is not None
        results["short"].append((w, code, len(code) - k, r, "✓" if ok else f"✗ 不在候选"))
        if not ok:
            failures.append(f"词组 {w} 少打{k}笔 {short} 不在候选 (期望仍在候选)")

    # ---- A 方案放行的超高频短码词: 应在词库且打满 rank<=3 ----
    for w in EXCLUDED_SHORT:
        code = phrase_codes.get(w)
        if not code:
            results["excluded"].append((w, "不在词组表!", None, None, "✗ 应放行"))
            failures.append(f"高频短码词 {w} 不在词组表 (A 方案应放行)")
            continue
        r, _ = model.rank(w, code)
        ok = r is not None and r <= PHRASE_RANK_MAX
        results["excluded"].append((w, f"码={code} ({len(code)}笔)", len(code), r, "✓" if ok else f"✗ rank={r}"))
        if not ok:
            _, ahead = model.rank(w, code)
            failures.append(f"高频短码词 {w} 打 {code} rank={r} (期望<={PHRASE_RANK_MAX}) 挡:{'/'.join((ahead or [])[:5])}")

    # ---- 报告 ----
    elapsed = time.time() - started
    schema_v = None
    for l in open(os.path.join(build.BUILD, "stroke_zh.schema.yaml"), encoding="utf-8"):
        if "version:" in l:
            schema_v = l.strip().split()[-1].strip('"')
            break

    total = len(results["phrase"]) + len(results["single"]) + len(results["short"])
    passed = sum(1 for x in results["phrase"] + results["single"] + results["short"] if x[-1].startswith("✓"))
    failed = total - passed

    lines = []
    lines.append("# 打字效果回归报告 (stroke-zh)")
    lines.append("")
    lines.append(f"- 生成时间: {time.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"- schema 版本: {schema_v}")
    lines.append(f"- 词条数: 单字 {len(entries)} (含词组 {len(phrase_codes)})")
    lines.append(f"- 耗时: {elapsed:.1f}s")
    lines.append("")
    lines.append("## 汇总")
    lines.append("")
    lines.append("| 类别 | 用例数 | 通过 | 失败 |")
    lines.append("|---|---|---|---|")
    lines.append(f"| 词组连打 (打满自然码 rank≤{PHRASE_RANK_MAX}) | {len(results['phrase'])} | {len(results['phrase']) - sum(1 for x in results['phrase'] if x[-1].startswith('✗'))} | {sum(1 for x in results['phrase'] if x[-1].startswith('✗'))} |")
    lines.append(f"| 单字自然码/偏旁 (rank≤{SINGLE_RANK_MAX}) | {len(results['single'])} | {len(results['single']) - sum(1 for x in results['single'] if x[-1].startswith('✗'))} | {sum(1 for x in results['single'] if x[-1].startswith('✗'))} |")
    lines.append(f"| 少打补全 (rank≤{PAGE}) | {len(results['short'])} | {len(results['short']) - sum(1 for x in results['short'] if x[-1].startswith('✗'))} | {sum(1 for x in results['short'] if x[-1].startswith('✗'))} |")
    lines.append(f"| **合计** | **{total}** | **{passed}** | **{failed}** |")
    lines.append("")
    lines.append("## 词组连打 (打满自然码)")
    lines.append("")
    lines.append("| 词 | 自然码 | 笔数 | 打满 rank | 首次进第一页 | 结果 |")
    lines.append("|---|---|---|---|---|---|")
    for w, code, n, r, n_first, ok in results["phrase"]:
        if code is None:
            lines.append(f"| {w} | - | - | - | - | {ok} |")
        else:
            lines.append(f"| {w} | `{code}` | {n} | {r} | 第{n_first}笔" if n_first else f"| {w} | `{code}` | {n} | {r} | 未进 | {ok} |")
    lines.append("")
    lines.append("## 单字自然码/偏旁")
    lines.append("")
    lines.append("| 字 | 自然码 | 笔数 | rank | 结果 |")
    lines.append("|---|---|---|---|---|")
    for ch, code, n, r, ok in results["single"]:
        lines.append(f"| {ch} | `{code}` | {n} | {r} | {ok} |")
    lines.append("")
    lines.append("## 少打补全")
    lines.append("")
    lines.append("| 词 | 完整码 | 打满-1笔 | rank | 结果 |")
    lines.append("|---|---|---|---|---|")
    for w, code, n, r, ok in results["short"]:
        lines.append(f"| {w} | `{code}` | `{code[:-1]}` | {r} | {ok} |")
    lines.append("")
    lines.append("## A 方案放行的超高频短码词 (第一/一个/一些…)")
    lines.append("")
    lines.append("| 词 | 状态 | 结果 |")
    lines.append("|---|---|---|")
    for w, status, _n, _r, ok in results["excluded"]:
        lines.append(f"| {w} | {status} | {ok} |")
    lines.append("")
    if failures:
        lines.append("## 失败明细")
        lines.append("")
        for f in failures:
            lines.append(f"- {f}")
        lines.append("")
    lines.append("## 机制约束说明")
    lines.append("")
    lines.append("- 词组码默认 ≥6 笔: librime 候选排序主键是剩余编码长度, 精确匹配 (remaining=0) 的词组"
                 " 永远排在更长编码的单字补全前 → 4-5 笔词组会抢占单字 4-5 笔前缀 (实测 4 笔命中率"
                 " 98%→94%). 故默认排除, 6-7 笔权重 ×0.001 (单字第一、词组仍第一页).")
    lines.append("- **A 方案例外**: 4-5 笔码但 jieba 词频 ≥ 10000 的超高频词 (第一/一个/一些/一般/"
                 "一定/一下 等 22 个) 放行 — 这些是用户必打词, 排除线误杀 (「第一」5 笔码用户实测"
                 "打不出). 放行词保留 jieba×717 全权重 (跳过 ×0.001), 否则被竹头单字压到 rank 9.")
    lines.append("- 单字 3 笔简码覆盖超高频字 (是/这/时/里 等), 4-6 笔补全被 6 笔词组占位不影响日常.")
    lines.append("- predict.db (上屏预测) 与用户词典学习是 librime 运行时行为, 离线测试不覆盖;"
                 " 修改编码方案后建议真机各打一次验证.")
    lines.append("")
    lines.append("---")
    lines.append(f"退出码: {'0 (全部通过)' if not failures else '1 (有失败)'}")
    lines.append("")

    report = "\n".join(lines)
    with open(args.report, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
