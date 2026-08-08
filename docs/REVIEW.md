# stroke_zh 方案设计审查报告

> 审查对象：v1.2.0（git `cfdeed0`）
> 审查日期：2026-08-08
> 审查范围：docs/DESIGN.md、docs/OPTIMIZATIONS.md、docs/STROKE_DATA.md、docs/PREDICT.md、docs/REGRESSION.md、README.md、scripts/build.py、scripts/build_pinyin.py、scripts/make_predict_data_ice.py、scripts/validate.py、cskin/、dist/ 产物
> 审查方法：通读文档与脚本；对照 `~/projects/stroke-zh-tools/librime-src/` 的 librime 源码确认引擎实际行为；用实际构建产物（`build/*.dict.yaml`，322,106 条）复现 librime 候选排序，测量排名与命中率

---

## 0. 结论摘要

方案的**词组部分设计正确且实测有效**：每字前 4 笔的定长截码在 62 万词量级下撞码可控，打满编码后目标词稳定排在第 1~3 位。笔顺数据选型（hzbishun / GB 标准）、GB2312+8105 基本区字表过滤、predict.db 纯后缀 value 这三项决策都正确，且踩坑记录准确。

但方案的**核心 UX 目标「每字打 3 笔 → 常用字第一页上屏」并未达成**，且 v1.2 引入的 `single_char_filter` 几乎不起作用、在少数起作用的位置起的是反作用。根本原因是一条被忽略的引擎事实：

> **librime 的候选排序主键是「剩余编码长度升序」，不是字频。**
> 源码：`librime-src/src/rime/dict/dictionary.cc:73-84` `compare_chunk_by_head_element()`

排序比较依次为：① 精确匹配优先 → ② **剩余编码短的优先** → ③ 权重降序。权重只是第三顺位的比较项。这条规则使得：8 笔的词组码在 3 笔前缀下剩余 5 笔，而 10 笔的单字全码剩余 7 笔，**词组反而排在常用单字之前**。DESIGN.md §4.1 以「前缀联想 + 字频排序天然等价」为由否掉简码表，这个推断不成立。

冷启动实测模拟（无用户词典）：

| 指标 | 现状 |
|---|---|
| 前 300 高频字，3 笔进第一页 | 25% |
| 前 600 高频字，3 笔进第一页 | 18% |
| 前 1000 高频字，3 笔进第一页 | 14% |
| 前 600 高频字，平均需要几笔才进第一页 | **5.71 笔**（中位 6 笔） |

另有一个已发布产物的实际缺陷：`dist/stroke_zh.zip`（README 首选的纯笔画包）**不含 `predict.db`**，纯笔画方案没有上屏预测。

以下按严重程度分级列出 25 项发现。

---

## 一、严重（P0）——核心功能未达成或产物有缺陷

### P0-1 「3 笔上屏」对绝大多数常用字不成立

**现象**
用实际构建产物复现 librime 排序，测试 DESIGN.md §5.1 同一批常用字在 3 笔前缀下的排名。54 字中 **31 字未进第一页（rank > 9）**：

| 字 | 编码 | 3 笔前缀 | 冷启动 rank | 同前缀候选数 |
|---|---|---|---|---|
| 都 | hshpszhhzs | hsh | **11547** | 25881 |
| 最 | szhhhsshhhzn | szh | **11001** | 22237 |
| 是 | szhhhshpn | szh | **9096** | 22237 |
| 真 | hsszhhhhpn | hss | **5618** | 13024 |
| 要 | hszsshzph | hsz | 3492 | 9088 |
| 看 | phhpszhhh | phh | 3187 | 7563 |
| 着 | nphhhpszhhh | nph | 3086 | 6169 |
| 就 | nhszhspnhpzn | nhs | 2073 | 4413 |
| 很 | ppszhhzpn | pps | 1133 | 2733 |
| 说 | nznpszhpz | nzn | 999 | 2058 |
| 和 | phspnszh | phs | 305 | 9461 |
| 里 | szhhshh | szh | 284 | 22237 |
| 时 | szhhhsn | szh | 283 | 22237 |
| 更 | hszhhpn | hsz | 192 | 9088 |
| 的 | pszhhpzn | psz | **157** | 5302 |
| 没 | nnhpzzn | nnh | 141 | 13039 |
| 再 | hszshh | hsz | 108 | 9088 |
| 我 | phshzpn | phs | **92** | 9461 |
| 这 | nhpnnzn | nhp | **90** | 8320 |
| 有 | hpszhh | hps | 54 | 14458 |
| 在 | hpshsh | hps | **53** | 14458 |
| 你 | pspzspn | psp | **49** | 3541 |
| 到 | hznhshss | hzn | 48 | 528 |
| 地 | hshzsz | hsh | 46 | 25881 |
| 来 | hnphspn | hnp | 37 | 1254 |
| 会 | pnhhzn | pnh | 25 | 4471 |
| 多 | pznpzn | pzn | 22 | 4060 |
| 好 | zphzsh | zph | 13 | 3835 |
| 年 | phhshs | phh | 13 | 7563 |
| 去 | hshzn | hsh | 11 | 25881 |
| 能 | znszhhpzpz | zns | 564 | 1525 |

按字频分段的第一页命中率：

| 字频区间 | 3 笔 | 4 笔 | 5 笔 | 全码 |
|---|---|---|---|---|
| 第 1-100 字 | 31% | 33% | 48% | 55% |
| 第 101-300 字 | 22% | 29% | 37% | 45% |
| 第 301-600 字 | 11% | 17% | 20% | 28% |
| 第 601-1000 字 | 8% | 12% | 22% | 23% |
| 第 1001-2000 字 | 5% | 8% | 12% | 13% |
| 第 2001-3500 字 | 2% | 5% | 9% | 8% |

注意「全码」一列也只有 55%/45%/28%：打完整笔画都进不了第一页，因为大量词组的截码比该字全码更短。

**根因**
`dictionary.cc:73-84`：

```cpp
if (a.is_exact_match() != b.is_exact_match())
    return a.is_exact_match() > b.is_exact_match();
if (a.remaining_code.length() != b.remaining_code.length())
    return a.remaining_code.length() < b.remaining_code.length();   // ← 主导
return a.credibility + a.entries[a.cursor].weight >
       b.credibility + b.entries[b.cursor].weight;
```

排序主键是剩余码长升序。`prism.cc:284-325` `ExpandSearch()` 用 `std::queue` 做 BFS，同样是短码优先返回，与上面的比较器一致。所以「剩余码短」这一偏好贯穿整条链路。

2 字词截码固定 8 笔。打 3 笔时词组剩余 5 笔，而常用字全码普遍 6~12 笔、剩余 3~9 笔。**大部分常用字的剩余码长于 8 笔词组**，于是被 314,153 条词组整体压在后面。字频（含 ×100 加成）只在剩余码长相同的组内才起作用。

**影响**
方案第一目标失效。用户实际需要平均 5.71 笔（前 600 字）才能让目标字进第一页，而不是文档承诺的 3 笔。

**建议**
见 §二 的 A1（显式简码表）与 A2（词组前缀门槛）。两者叠加可把前 600 字的 3 笔命中率从 18% 提到 72% 以上。

---

### P0-2 `single_char_filter` 基本不生效，且在生效处方向相反

**现象**
DESIGN.md §4.3 声称「打 1~7 笔第一页全是单字，词组排后」。实际不成立。

**根因**
两处源码事实相互作用：

1. `gear/table_translator.cc:82-85` —— 任何补全候选的 type 是 `"completion"`，不是 `"table"`：
   ```cpp
   bool incomplete = e->remaining_code_length != 0;
   auto type = incomplete       ? "completion"
               : is_user_phrase ? "user_table"
                                : "table";
   ```
2. `gear/single_char_filter.cc:41-45` —— 遇到第一个非 `table`/`user_table` 候选立即 `break`：
   ```cpp
   auto phrase = As<Phrase>(Candidate::GetGenuineCandidate(cand));
   if (!phrase ||
       (phrase->type() != "table" && phrase->type() != "user_table")) {
     break;
   }
   ```

短前缀阶段候选几乎全是 `completion` → 过滤器在第一个候选处就退出 → **零作用**。

它唯一生效的位置是「精确匹配头部」，效果是把与词组同码的单字提到词组之前。这与设计意图完全相反。实测：**5,747 / 314,153 条词组的编码与某个单字的全码完全相同**，这些词组全部被该单字抢先：

| 词组 | 编码 | 被哪个单字抢先 |
|---|---|---|
| 中国 | szhsszhh | 固 |
| 同时 | szhsszhh | 固（且排在 中国 之后 → rank 3）|
| 机构 | hspnhspn | 林 |
| 检查 | hspnhspn | 林 |
| 模式 | hspnhhsh | 枉 |
| 苹果 | hsshszhh | 昔 |
| 拆迁 | hshpphsn | 拆 / 坼 |
| 一些 | hshsh | 正 |

**影响**
v1.2 的核心改动没有产生宣称的效果。它带来的唯一可观测变化是 5,747 条词组各降一位。DESIGN.md §4.1「`single_char_filter` 单字优先重排已彻底解决」与 §4.3「效果与 v1.1 双 translator 同等」两处结论均不成立。

**建议**
1. 从 filters 中移除 `single_char_filter`。它无法实现分流，且伤害词组排名。
2. 用 §二 A1 + A2 实现真正的分流。
3. 如果保留，请在文档中把它的作用范围如实写成「仅在精确匹配组内把单字提前」。

---

### P0-3 `dist/stroke_zh.zip` 不含 `predict.db`，纯笔画方案没有预测

**现象**

```
=== dist/stroke_zh.zip ===   (README 步骤 2 的首选包)
  stroke_zh.schema.yaml
  stroke_zh.dict.yaml
  stroke_zh_base.dict.yaml
  stroke_zh_phrase.dict.yaml          ← 4 个文件，无 predict.db

=== dist/stroke_zh_plus.zip ===
  ... 6 个 yaml ...
  predict.db                          ← 只有 plus 包有
```

zip 内文件 mtime 为 `08-08 13:34`，`predict.db` mtime 为 `08-08 13:19`。zip 在 predict.db 之后重建，而手动加回 predict.db 的步骤被漏掉。

**根因**
`build.py:456-465` 的 `files` 列表只含 4 个 yaml，不含 `predict.db`。DESIGN.md §6 已写明「`build.py` 只生成 yaml，`predict.db` 需手动加回 zip」——把一个必需步骤留在人工流程里，于是它被漏掉了。

**影响**
按 README 导入 `stroke_zh.zip` 的用户没有上屏预测。schema 里 `predictor: {db: predict.db}` 指向不存在的文件。README 与 DESIGN.md 宣传的预测功能在首选包里不可用。REGRESSION.md 第 6 项（预测）在该包上必然失败。

**建议**
把 `predict.db` 加入 `build.py` 的打包列表，并在打包前断言文件存在。删除文档里的手动步骤。凡「必需但靠人记住」的步骤都应转为脚本内的硬失败。

---

## 二、高（P1）——验证方法与关键规则错误

### P1-4 验证方法学不可靠：三重自我印证

**现象与根因**

**(a) 离线模拟未复现 librime 排序。** DESIGN.md §5.1 声称「37 个常用字全部第一页」、§5.2 表格给出 我 #1、子 #1、天 #1、真 #1。用 librime 真实排序规则复现，同批字 31/54 未进第一页，真 rank 5618。`validate.py` 也不做排名校验（它只查编码合法性与 YAML 语法）。该模拟的排序模型与引擎不一致，其结论不可用。

**(b) 用户词典污染人工实测。** `table_translator.cc:102-113` `PreferUserPhrase()`：

```cpp
if (iter_.Peek()->remaining_code_length == 0 &&
    (uter_.Peek()->remaining_code_length != 0 || is_constructed(...)))
  return false;
else
  return true;      // 两者都是补全时 → 用户词典优先
```

`enable_user_dict: true` 之下，测试者手打过一次的字/词此后排在码表补全之前。DESIGN.md §5.4 的实测（真/天/子/我 → ✅ 第一页）在测试者已多轮手打这些字之后进行，不构成独立验证。冷启动 rank：真 5618、我 92、的 157、是 9096、最 11001。

**(c) 抽样偏置。** §5.1 表格展示的 12 个字（我你这的在是子天真太最里）**全部在 `build.py:43-48` 的 `HIGH_FREQ_SINGLE_BONUS` 55 字名单内**（权重 ×100）。样本恰好取自被特殊加权的子集。分组测量：前 600 高频字中，**加成名单内 20/51 = 39% 进第一页，名单外 88/535 = 16%**。

**影响**
三处叠加，使得「已验证通过」的结论掩盖了 P0-1。v1.1 → v1.2 的改动方向也因此被误导。

**建议**
1. 建立冷启动排名回归测试。加载 `build/*.dict.yaml`，按 `(剩余码长, -权重)` 排序，断言指定字集在 N 笔时的 rank。把它加进 `validate.py`。
2. 人工实测前先删除用户词典（重装方案或清除 `*.userdb`）。在 REGRESSION.md 里把「先清用户词典」写成前置步骤。
3. 测试字集取自公开字频表的前 N 字，不要取自 `HIGH_FREQ_SINGLE_BONUS`。

---

### P1-5 「不建简码表」的决策依据错误

**现象**
DESIGN.md §4.1 用「前缀联想 + 字频排序天然等价（打 1 笔 = 最高频起笔字；打 3 笔 = 同前缀最高频字），零维护」为由，否掉了调研建议的一/二/三级简码体系。

**根因**
该等价关系不成立。如 P0-1 所述，排序主键是剩余码长而非字频。「打 3 笔 = 同前缀最高频字」只在「所有同前缀候选剩余码长相同」时才成立，而实际候选里混着 8 笔词组码与 4~12 笔单字码。

**影响**
放弃了本方案最有效的单一改进手段。

**证据（模拟：为高频字补 1/2/3 笔简码条目，使其成为精确匹配）**

| 方案 | 前 300 字 ≤3 笔 | 前 600 字 ≤3 笔 | 前 1000 字 ≤3 笔 |
|---|---|---|---|
| 现状（无简码） | 25% | 18% | 14% |
| top300 加简码 | **88%** | 48% | 31% |
| top600 加简码 | **88%** | **72%** | 45% |
| top1000 加简码 | **88%** | **72%** | **56%** |
| top1500 加简码 | 88% | 72% | 56% |

88% 是页容量上限（`page_size: 9`，多个高频字共享同一 3 笔前缀），不是算法缺陷。

**建议**
采纳简码表。见 §三 A1。

---

### P1-6 自动造词编码与词库编码在 5/6 字词上不一致

**现象**
`build.py:335-336` 的第三条 encoder 规则：

```yaml
- length_in_range: [4, 6]
  formula: "AaAbAcAdBaBbBcBdCaCbCcCdZaZbZcZd"
```

`encoder.cc:120`：`c.char_index = (*it >= 'U') ? (*it - 'Z' - 1) : (*it - 'A')` → `Z` = **末字**。所以该公式是「前三字 + 末字」，共 16 笔。

- 4 字词：A/B/C/Z = 第 1/2/3/4 字 → 与「每字 4 笔」等价 ✓
- 5 字词：A/B/C/Z = 第 1/2/3/**5** 字 → **跳过第 4 字**，16 笔；词库是 20 笔 ✗
- 6 字词：A/B/C/Z = 第 1/2/3/**6** 字 → 跳过第 4、5 字，16 笔；词库是 24 笔 ✗

实测全量比对：

| 词长 | 造词码 ≠ 词库码 |
|---|---|
| 2 字词 | 0 / 120,634 ✓ |
| 3 字词 | 0 / 114,537 ✓ |
| 4 字词 | 0 / 74,263 ✓ |
| 5 字词 | **4,267 / 4,267** ✗ |
| 6 字词 | **452 / 452** ✗ |

示例：

| 词 | 词库码 | 造词码 |
|---|---|---|
| 江泽民同志 | nnhhnnhzzhzhszhshshn（20 笔） | nnhhnnhzzhzhhshn（16 笔） |
| 马克思主义 | zzhhsszszhsnhhsnpn（18 笔） | zzhhsszszhsnpn（14 笔） |
| 人民代表大会 | pnzhzhpshzhhshhpnpnhh（21 笔） | pnzhzhpshzpnhh（14 笔） |

**根因**
公式套用了仓颉/五笔的「前三末一」惯例，与本方案「每字前 4 笔」规则不同。DESIGN.md §4.4 声称「encoder 公式 `AaAbAcAdBaBbBcBd...`（每字前 4 笔，与词组规则一致）」——对 5/6 字词不成立。

**影响**
用户造出的 5/6 字词（人名、机构名、术语，正是造词的主要用途）编码规则与词库不同。用户按「每字 4 笔」去打，打不出自己刚造的词；打「前三末一」才行，但方案从未告知这条规则。

**注**
`encoder.cc:172-173` 对短码是安全降级（`if (c.code_index >= code[...].length()) continue;`），所以笔画数不足 4 的字不会导致造词失败。这一点设计正确。

**建议**
把规则改为逐字展开，与词库一致：

```yaml
- length_equal: 4
  formula: "AaAbAcAdBaBbBcBdCaCbCcCdDaDbDcDd"
- length_equal: 5
  formula: "AaAbAcAdBaBbBcBdCaCbCcCdDaDbDcDdEaEbEcEd"
- length_equal: 6
  formula: "AaAbAcAdBaBbBcBdCaCbCcCdDaDbDcDdEaEbEcEdFaFbFcFd"
```

6 字词得 24 笔码，在 `max_code_length: 32` 之内。改动后必须清除用户词典：已学词条仍是旧码。

---

### P1-7 拼音平翘舌模糊音规则完全失效

**现象**
实测 `pinyin_variants()`：

| 输入 | 输出变体 | 期望 |
|---|---|---|
| `zhi` | `['zhi']` | 应含 `zi` |
| `chi` | `['chi']` | 应含 `ci` |
| `shi` | `['shi']` | 应含 `si` |
| `zhi dao` | `['zhi dao']` | 应含 `zi dao` |

**根因**
`build_pinyin.py:46-50` 用 `syl.endswith(orig)` 匹配，而 `zh`/`ch`/`sh` 是**声母**，不是韵尾。`"zhi".endswith("zh")` 为 False，`elif syl.endswith(alt) and orig in ("zh","ch","sh")` 中 `"zhi".endswith("z")` 也为 False。`FUZZY_SETS` 前 3 条规则永不触发。

**影响**
OPTIMIZATIONS.md §五·六 声称的「打 `94`（zi 码）→ 也出「知/之」（原 zhi，平翘舌不分）」**实际来自 T9 前缀补全，与模糊音规则无关**：T9 下 `z`→9、`h`→4，`zi` = `94`，`zhi` = `944`，`94` 是 `944` 的前缀，`enable_completion: true` 自动给出 `知/之`。`ch`/`sh` 同理（`ci`=24 / `chi`=244，`si`=74 / `shi`=744）。

功能表现正确，但归因错误。文档把一个未生效的机制当成已验证特性记录下来，后续维护者会依赖它。

**建议**
1. 若要真正实现平翘舌互换，改用前缀判断：`if syl.startswith("zh"): alts.append("z" + syl[2:])`，反向同理。
2. 先评估是否需要。T9 编码已天然覆盖该场景，显式变体只会把翘舌词提升到平舌码的**精确匹配**层，可能把 `知` 排到与 `子/自` 同级。
3. 修正文档归因。

---

### P1-8 前后鼻音规则单向，文档描述反了

**现象**

| 输入 | 输出变体 | T9 码 |
|---|---|---|
| `ang` | `['ang', 'an']` | `264`, `26` |
| `an` | `['an']` | `26` |
| `ying` | `['ying', 'yin']` | `9464`, `946` |
| `yin` | `['yin']` | `946` |

只生成「后鼻音 → 前鼻音」，不生成反向。

**影响**
OPTIMIZATIONS.md 声称「打 `264`（ang 码）→ 出「昂」，也出「安/按」（an，前后鼻不分）」**不成立**：`安` 的码是 `26`，不是 `264` 的前缀延伸，打 `264` 出不来 `安`。反方向（打 `26` 出 `昂`）成立，但靠的是前缀补全，同样不需要显式变体。

**建议**
修正文档中的效果描述。重新评估 `FUZZY_SETS` 的净收益——词条从 40.9 万膨胀到 62 万（1.43×）换来的实际增量，扣除 T9 前缀补全已覆盖的部分后可能接近于零。

---

## 三、中（P2）——设计与工程隐患

### P2-9 纯笔画皮肤在仓库里没有源，无法重建

`cskin/config.yaml` 的 `name` 是「笔画拼音」，且含 `t9pinyin:` 节 —— 它只是 `stroke_zh_pinyin.cskin` 的源。`dist/stroke_zh.cskin`（名称「笔画增强」，无 `t9pinyin:` 节）在仓库中无对应源；其 `light/pinyinPortrait.yaml` 与 `cskin/light/pinyinPortrait.yaml` 的 md5 不同（`d6e7fa66…` vs `89dd6fe6…`）。两个 `.cskin` 都是手工 zip，`scripts/` 下没有皮肤构建脚本。

**影响**：纯笔画皮肤丢失后无法从源重建；两套皮肤的差异只存在于二进制产物中，无法 review、无法 diff。

**建议**：把 `cskin/` 拆成 `cskin/common/` + 两个 variant 覆盖层，写 `scripts/build_skin.py` 生成两个 `.cskin`。皮肤源必须能生成全部已发布产物。

### P2-10 REGRESSION.md 与 v1.2 现状冲突

- 第 24 项「词组表每个词有 完整码 + 4笔简码 两行」—— v1.2 已删除全码（DESIGN.md §4.1）。该项现在必然失败。
- 第 4 项「词组被单字碾压 → 打 `phshpsns` 我们仍在候选前 3」—— 与 `single_char_filter` 的「单字优先」目标直接矛盾。
- 第 3 项与第 4 项都只测 `我们`，恰好是同码数 = 1 的最好情况；未覆盖 `中国`（同码 89）、`机构`（同码 352）。

**影响**：回归清单是防止「修 A 破坏 B」的最后一道防线，其中已有条目与现行设计互斥，执行者只能忽略它们，防线失效。

**建议**：每次设计变更同步更新 REGRESSION.md。把清单里的手工检查尽量改成 `validate.py` 里的断言。

### P2-11 `validate.py` 的键盘校验有 33 行死代码，宣称的校验项未执行

`validate.py:193` `return errs, warns` 之后，第 194-226 行永不执行。那段才是真正的校验逻辑：`action` 类型合法性、`keyboardType` 取值、`width` 格式、`processByRIME` 类型、每行 `input` 宽度锚点、`isPrimary`。模块 docstring 第 22-23 行宣称的「校验项 6：action/width 合法性」「校验项 7：宽度锚点」实际都没跑。`VALID_ACTIONS`、`VALID_KT`、`VALID_WIDTH` 三个常量只被死代码引用。

实际执行的只有 `Cell` 引用完整性和「有无 `action` 键」。

**建议**：删除 `return` 或重构。该函数还混用了两种数据模型（前半段读 `keyboardLayout`/`Cell`，死代码读 `d["keyboards"]` 的 `rows`/`keys`），说明它跨过一次格式变更且未清理。

### P2-12 字频数据源与权重体系是手调魔数

- 单字权重用 `data/jieba_dict.txt` 中的**单字条目频次**。jieba 词典是分词用的，其单字项频次不等于语料字频。
- `HIGH_FREQ_SINGLE_BONUS`（`build.py:43-48`）硬编码 55 字 ×100，靠人工维护。
- `PHRASE_WEIGHT_FACTOR = 10` 对雾凇词频统一放大，而雾凇词频是为**拼音**输入竞争调过的。

实测权重分布：

| | 值 |
|---|---|
| 加成字（是/在/我） | 79,699,100 / 72,791,500 / 32,884,100 |
| 单字权重中位数（第 4000 位） | **139** |
| 词组第 10 万位权重 | 59,500 |

加成名单外的字权重中位数 139，比第 10 万位词组低两个数量级。**这 55 字名单事实上是「3 笔能上屏」与「不能」的分界线**（名单内 39%，名单外 16%）。

**建议**：换用字级频率表（见 §五），删除人工加成名单。权重建议取对数域再线性映射，压缩动态范围：`w = round(K * log(freq))`。

### P2-13 无笔画容错，且打错后不自动清空

点/捺合并、折类归并已消除部分歧义，但「折」的归类判断仍是笔画输入的主要错误来源。一旦某笔打错，后续候选全空。`speller/auto_clear` 未配置（`speller.h:48` 默认 `kClearNone`），输入串会一直挂着，只能按「清除」键。

`enable_correction` **仅 `script_translator` 支持**（`script_translator.cc:192, 200, 541-548`），`table_translator` 不支持。所以笔画容错无法通过该开关实现。

**建议**
1. 加 `speller/auto_clear: max_length`，无候选时到长度上限自动清空。
2. 容错需在词库端做：对易混笔画对（如折/竖、点/横）生成有限变体条目，权重打折。先小规模验证收益再决定是否铺开。

### P2-14 delimiter 配置实际是死的，没有字符边界手段

`speller/delimiter: " '"` 含空格与单引号，但：
- 空格被 speller 忽略：`speller.cc:107` `if (ch == XK_space && (!use_space_ || …)) return kNoop;`，而 `use_space_` 默认 false（`speller.h:46`），schema 未设置。空格因此落到 selector → 上屏首选（行为正确，但 delimiter 里的空格无意义）。
- `'` 在九宫格上没有按键（键位为 5 笔画 + 清除 + 123 + 空格 + 中英）。

**影响**：用户无法显式标记字与字的边界。这也挡住了「变长码 + 分隔符 → 整句」这条改进路径（见 §五 B）。

**建议**：把左侧标点列的一个位置或长按手势绑定 `'`。若不需要边界，就把 delimiter 简化为 `"'"` 并在注释里说明它只服务 encoder。

### P2-15 词组打满编码前全程无有效反馈

因排序按剩余码长升序，一个 4 字词（16 笔）在打到第 8 笔时剩余 8 笔，排在所有剩余更短的候选之后。用户在打满最后一笔之前看不到目标词。3 字词 12 笔、4 字词 16 笔、5 字词 20 笔、6 字词 24 笔均如此。

**影响**：长词只能「盲打到底」。6 字词 24 笔无实用价值。

**建议**：把 `PHRASE_MAX_LEN` 从 6 降到 4（5/6 字词条 4,719 条，占 1.5%，多为「江泽民同志」类低频专名）。省下的编码空间与候选位留给单字和 2~3 字词。

### P2-16 拼音方案 preedit 显示数字码

`build_pinyin.py` 把拼音离线转成 T9 数字入库，运行时无从还原拼音，且 schema 未设 `preedit_format`。用户看到的编码行是 `64426` 而不是 `ni hao`。

**影响**：打长词时无法核对已输入内容，错了只能全删。

**建议**：见 §五 D（`speller/algebra` 派生方案），或退一步把拼音写进词条 `comment` 供候选注释显示。

### P2-17 `speller/alphabet: '987654321'` 逆序引入无意的遍历偏置

`prism.cc:310` `for (const char* c = alphabet; *c; ++c)` —— alphabet 的字符顺序决定 BFS 同层的遍历顺序，进而决定 `expand_search_limit`（初始 10，`table_translator.cc:119-120`）截断时哪些码先被取到。写成 `'987654321'` 使高位数字优先展开。

**建议**：改为 `'123456789'`，除非有实测理由保留逆序。

### P2-18 pinyin_lite 的 `auto_select` 配置过宽

`auto_select: true` + `auto_select_pattern: '^\d+$'`。该正则匹配任意长度纯数字串，于是任意长度的码只要当前唯一候选就自动上屏（`speller.cc:163-189`）。T9 下唯一候选较少，故多数时候无害，但长码上可能出现意外上屏。

**建议**：收紧为固定长度（如 `'^\d{6,}$'`），或关闭 `auto_select`。

### P2-19 `stroke_zh_plus.zip` 双方案缺少 schema 注册文件

该 zip 含 `stroke_zh` 与 `pinyin_lite` 两套 schema，但没有 `default.custom.yaml` 之类登记 `schema_list` 的文件。两个方案是否都出现在方案列表里，取决于元书自己的导入行为，属未验证的外部依赖。

**建议**：在 REGRESSION.md 加一项「导入 plus 包后，方案列表同时出现『笔画·增强』与『简体拼音』」。

---

## 四、低（P3）——文档与细节

### P3-20 DESIGN.md §5.1 的「真」编码与词库不一致
文档写 `hsszhhhpn`（9 笔），`build/stroke_zh_base.dict.yaml` 中是 `hsszhhhhpn`（10 笔）。

### P3-21 `build.py` 的 `load_stroke(path)` 忽略参数
`build.py:148-164` 的 `load_stroke(path)` 不使用 `path`，函数内硬编码 `data/hzbishun_13000.csv`；调用处 `build.py:220` 仍传 `stroke_official.dict.yaml`。打印文案 `[1/6] 加载官方笔画码表` 与文件头 docstring 的数据源说明也仍指向官方 rime-stroke 码表。

### P3-22 `STROKE_FIX` 已成死代码
`build.py:56-58` 的 `STROKE_FIX['着'] = 'nphhhpszhhh'` 与 hzbishun 数据中「着」的编码相同，`if STROKE_FIX[ch] not in codes` 恒为假。该表的注释（「官方码表（台湾 CNS11643）与大陆标准笔顺有差异」）描述的是已被替换掉的数据源。

### P3-23 `prediction` 开关无入口
schema 声明了 `prediction` 开关（`reset: 1`），但 `key_binder` 无绑定、皮肤上无按键，用户无法关闭预测。

### P3-24 `reverse_lookup` 用户不可达
`prefix: "`"` 在九宫格上没有对应按键。该段的实际作用是让部署生成 encoder 所需的 reverse 库（OPTIMIZATIONS.md §五·五 已记录）。建议在 schema 注释里写明「本段仅为 encoder 服务，非用户功能」。

### P3-25 `pinyin_variants()` 生成重复变体
`zhuang` → `['zhuang', 'zhuan', 'zhuan']`，`xiang` → `['xiang', 'xian', 'xian']`。因 `("ang","an")` 与 `("uang","uan")` 对同一音节都命中，产生相同结果。靠下游 `seen` 去重，不影响产物，但白跑一遍循环。

---

## 五、改进建议（按优先级）

### A1 — 加显式简码表（最高优先，收益最大）

**做什么**
在 `stroke_zh_base.dict.yaml` 里，为高频字额外写入 1/2/3 笔简码条目，编码取该字真实笔画的前 1/2/3 笔，权重沿用字频。

**为什么**
简码条目使这些字在 1/2/3 笔时成为**精确匹配**（剩余码长 0），按 `dictionary.cc:78-79` 排在所有补全候选之前。这直接绕开 P0-1 的根因，且不依赖 `single_char_filter`。这也是 五笔/郑码/仓颉 的标准做法（一级简码 25 字、二级简码、三级简码），RIME 的 `wubi86` 等方案均把简码直接写进词库。

**收益（实测模拟）**

| 方案 | 前 300 字 ≤3 笔 | 前 600 字 ≤3 笔 | 前 1000 字 ≤3 笔 |
|---|---|---|---|
| 现状 | 25% | 18% | 14% |
| top1000 加简码 | **88%** | **72%** | **56%** |

**成本**
词条增加约 3,000 条（前 1000 字 × 3 级），相对 322,106 条可忽略。无 schema 改动，无引擎依赖。

**注意**
1. 同一 3 笔前缀会被多个高频字共享。`page_size: 9` 之下每个前缀最多容纳 9 个，因此 88% 是上限。按字频排序决定谁进前 9。
2. 需要复核简码与词组码的碰撞：2 字词最短码 2 笔（两个 1 笔字），与 1/2 笔简码存在重叠空间。加简码后重跑排名回归。

### A2 — 给词组设前缀门槛（与 A1 叠加）

**做什么**
让词组在输入达到一定笔数前不参与候选。

**为什么**
现状下词组把常用字整体压后。实测三种情形下前 600 字进第一页的平均笔数：

| 情形 | 平均笔数 | ≤3 笔 | ≤4 笔 |
|---|---|---|---|
| 现状（词组全程参与） | 5.71 | 20% | 29% |
| 词组仅在 ≥6 笔后出现 | **4.35** | 38% | 63% |
| 完全无词组 | 4.07 | 38% | 63% |

即：把词组门槛设到 6 笔，就能拿回「无词组」情形几乎全部的收益（4.35 vs 4.07），同时保留词组功能。

**怎么做（两个选项，建议选 1）**

**选项 1：拆双 translator + `schema/dependencies`（推荐）**
v1.1 的双 translator 思路正确，失败原因也诊断正确 —— `SchemaUpdate::Run` 只编译 `translator/dictionary` 指向的词典（`lever/deployment_tasks.cc:350`，命名空间 `"translator"` 硬编码）。**但存在官方解法**：`schema/dependencies`（`lever/deployment_tasks.cc:236-244`），部署时会为每个依赖 schema 走一遍 `build_schema()`，从而编译其词典。

步骤：
1. 建 `stroke_zh_phrase.schema.yaml`，其 `translator/dictionary: stroke_zh_phrase`。
2. 在 `stroke_zh.schema.yaml` 加 `schema: dependencies: [stroke_zh_phrase]`。
3. 在 `stroke_zh.schema.yaml` 加第二个 table_translator 命名空间，指向已编译的 `stroke_zh_phrase`，设 `enable_completion: false`。
4. 主 translator 只 import 单字表。

`translator/packs`（`dict/dictionary.cc:442-450`）可作为补充：一本词典可加载多个预编译 table pack。它解决「合并加载」，不解决「编译」，须与 `dependencies` 配合。

**选项 2：不改架构，只调编码**
保留单 translator，把 2 字词截码从 8 笔提到更长（如每字前 5 笔 = 10 笔），拉大词组与单字的剩余码长差距。改动小，但收益不如选项 1，且加长用户输入。

**同时移除 `single_char_filter`**（见 P0-2）。

### A3 — 修正 encoder 规则并清用户词典（P1-6）

按 P1-6 给出的逐字公式替换 `length_in_range: [4,6]`。若同时采纳 A5（`PHRASE_MAX_LEN` 降到 4），只需 `length_equal: 4` 一条。改动后必须清用户词典。

### A4 — 建立冷启动排名回归测试（P1-4）

在 `validate.py` 中加入排名断言：
1. 读 `build/*.dict.yaml`。
2. 对给定前缀，按 `(len(code) - len(prefix), -weight)` 排序（复现 `dictionary.cc:73-84`）。
3. 断言指定字集在 N 笔时 rank ≤ 9。
4. 断言指定词集在打满编码时 rank ≤ 3。

字集取自公开字频表前 N 字，不要取自 `HIGH_FREQ_SINGLE_BONUS`。这是唯一能防止 P0-1 再次发生的手段。

### A5 — 收缩词组表

把 `PHRASE_MAX_LEN` 从 6 降到 4。理由见 P2-15：5/6 字词共 4,719 条（1.5%），需 20/24 笔，无实用性。

同时确认「每字前 4 笔」是当前最优截码长度，**不要改成 3 笔**。实测碰撞对比：

| 截码 | 唯一码数 | 平均同码 | 最大同码 | 独占码词数 | 撞码词数 |
|---|---|---|---|---|---|
| 每字前 4 笔（现行） | 220,612 | 1.42 | 351 | 61% | 38% |
| 每字前 3 笔 | 154,827 | 2.03 | **1232** | 39% | 60% |
| 每字前 2 笔 | 61,372 | 5.12 | **4879** | 11% | 88% |

且 3 笔截码会让词组码更短、剩余码长更小，进一步压低单字排名：前 600 高频字 3 笔进第一页从 **18% 降到 11%**。

### A6 — 换字频数据源，删人工加成名单（P2-12）

用字级频率表替代 jieba 单字项 + 55 字 ×100。权重取对数域映射压缩动态范围。理由：现状下那份手工名单是功能分界线，名单外的字（占绝大多数）无法享受任何排序优待，且名单需要人工维护。

### A7 — 把手动步骤脚本化（P0-3、P2-9）

1. `build.py` 打包时纳入 `predict.db`，缺失即失败。
2. 写 `scripts/build_skin.py` 生成两个 `.cskin`，皮肤源拆共用层 + variant 覆盖层。

### A8 — 修文档与死代码

P1-7、P1-8 的归因修正；P2-10 回归清单同步；P2-11 `validate.py` 死代码；P3-20~P3-25 各项。这些不影响功能，但它们正是导致 P0/P1 级误判的土壤 —— 文档把未生效的机制记录成已验证特性。

---

## 六、可借鉴的成熟方案与行业做法

### A. 五笔/郑码/仓颉的简码体系
`rime-wubi`（wubi86）等方案把一级简码（25 字）、二级简码、三级简码**直接作为词条写进词库**，而不是指望前缀联想。这正是 A1 的做法，有现成实现可对照。调研（DESIGN.md §3 第 2 点）原本给出了这个建议，被 §4.1 以错误理由否掉。

### B. librime-octagram + `enable_sentence`（结构性替代方案）
`table_translator` 已内置整句支持：`enable_sentence`、`sentence_over_completion`、`contextual_suggestions`（`table_translator.cc:218-227`），并通过 `Poet` 接语法模型（`gear/poet.cc:74-83` `create_grammar()` → `Grammar::Require("grammar")`）。rime-ice 用的是 `zh-hans-t-essay-bgw.gram`。

思路：与其用 314,153 条定长截码硬编码词组，不如让用户每字打少量笔画 + 分隔符，由语言模型组句。这能同时解决 P0-1（词组不再挤占短前缀）与 P2-15（不必盲打到底）。

**前置条件**（必须先验证，不要直接上）：
1. 笔画码变长且无天然边界，需要可输入的分隔符（见 P2-14）。
2. 元书是否随包编译 octagram 插件，未知。
3. `.gram` 文件体积与 iOS 键盘扩展内存上限的关系，未测。

建议作为 v2 的探索方向，先在桌面 Squirrel/Weasel 上验证。

### C. `schema/dependencies` —— v1.1 双 translator 的正解
`lever/deployment_tasks.cc:236-244` 已验证：部署时会为依赖 schema 走一遍构建，其词典因此被编译。这是 RIME 社区处理「多词典」的标准做法（反查方案如 `radical_pinyin` 依赖 `stroke` 即用此机制）。见 A2 选项 1。

### D. `speller/algebra` + `xlit` —— T9 的另一种取舍
README 已致谢「语燕输入法（T9 拼音 algebra 规则参考）」。该做法是词库保留拼音，用 `speller/algebra` 在部署时派生 T9 数字码。相比现行「离线转码」：
- 优点：preedit 可显示拼音（解决 P2-16）；模糊音用 `derive` 规则表达，不会出现 P1-7 那种 `endswith` 写错还无人发现的情况。
- 缺点：部署变慢（40 万词条派生规则）。

这是明确的取舍，两种都合理。若 P2-16 的体验问题被用户抱怨，再切换。

### E. 字频与词频数据
- **Jun Da 现代汉语单字频率表** —— 字级频率，语料透明，学界常用。
- **SUBTLEX-CH** —— 影视字幕语料的字级与词级频率，更贴近口语与聊天场景，适合输入法。

两者都比「jieba 分词词典里的单字项」更适合做单字权重（P2-12）。

### F. Hamster 仓输入法（github.com/imfuxiao/Hamster）
开源 iOS RIME 输入法，键盘布局与皮肤 DSL 与元书接近。可作为对照实现，用于：
- 九宫格布局与宽度分配的参考（OPTIMIZATIONS.md §五·七 的「布局铁律」是黑盒试错得出的，对照开源实现可以确认成因）。
- Lua 支持验证。DESIGN.md §4.1 因「元书对 Lua 支持不确定」放弃了 Lua filter；在 Hamster 上可以确认 Lua 方案是否可行，再决定元书上要不要试。

### G. 笔画容错
`enable_correction` 只在 `script_translator` 生效（`script_translator.cc:192`），`table_translator` 无此能力。可行路径只有两条：
1. 词库端生成易混笔画变体条目（权重打折）。参考 stroke-input.app（Conway）等笔画输入实现对易混笔画的处理。
2. 改用 `script_translator` + algebra，代价是把每一笔当作一个音节，性能与复杂度都要重新评估。

建议先用路径 1 做小规模实验（如只对「折/竖」「点/横」两对），用 A4 的回归测试量化收益与副作用。

---

## 七、建议的执行顺序

1. **A4** 先建冷启动排名回归测试。没有它，后面每一步都无法判断是否真的改善。
2. **A7-1** 把 `predict.db` 纳入打包（已发布产物有缺陷，最快可修）。
3. **A1** 加简码表 → 跑 A4 → 预期前 600 字 3 笔命中 18% → 72%。
4. **P0-2** 移除 `single_char_filter` → 跑 A4 → 预期 5,747 条词组各升一位，单字无损失。
5. **A5** 收缩 `PHRASE_MAX_LEN` 到 4 → 跑 A4。
6. **A3** 修 encoder 规则 → 清用户词典 → 实测造词。
7. **A2** 视 3~5 步后的结果决定是否还需要双 translator 门槛。
8. **A6、A8** 数据源与文档清理。
9. **B** 作为 v2 探索，先在桌面验证。

前 6 步都不改架构，风险低、可单独回滚、可用 A4 量化。

---

## 附录：本次审查复现的引擎事实

| 事实 | 源码位置 |
|---|---|
| 候选排序 = 精确匹配优先 → 剩余码长升序 → 权重降序 | `dict/dictionary.cc:73-84` |
| 前缀展开是 BFS（短码优先返回） | `dict/prism.cc:284-325` |
| 补全候选的 type 是 `"completion"`，非 `"table"` | `gear/table_translator.cc:82-85` |
| `single_char_filter` 遇非 table/user_table 即 break | `gear/single_char_filter.cc:41-45` |
| 用户词典补全优先于码表补全 | `gear/table_translator.cc:102-113` |
| 惰性取词初始 limit=10，×10 递增 | `gear/table_translator.cc:119-120, 189-207` |
| encoder 公式中 `Z` = 末字 | `algo/encoder.cc:120` |
| encoder 对短码安全降级（不失败） | `algo/encoder.cc:172-173` |
| 部署只编译 `translator/dictionary` | `lever/deployment_tasks.cc:350` |
| `schema/dependencies` 会触发依赖 schema 构建 | `lever/deployment_tasks.cc:236-244` |
| `translator/packs` 支持多 table 合并加载 | `dict/dictionary.cc:442-450` |
| `enable_correction` 仅 script_translator 支持 | `gear/script_translator.cc:192, 200, 541-548` |
| 空格默认不被 speller 消费（`use_space_ = false`） | `gear/speller.cc:107`、`gear/speller.h:46` |
| 预测候选 type 是 `"prediction"`（`SimpleCandidate`），不受 `single_char_filter` 重排 | `librime-predict/src/predict_translator.cc:34` |

排序复现模型：对输入前缀 `p`，候选集为所有 `code.startswith(p)` 的词条，按 `(len(code) - len(p), -weight)` 排序，再对剩余码长为 0 的头部应用单字提前。该模型与上表前 3 条一致。

**该模型的可falsify点**：若在真机上以**全新安装、空用户词典**状态打 `szh`（3 笔），本模型预测「是」不在前 9 位（rank ≈ 9096）。若实测「是」在第一页，则模型有误，本报告 P0-1、P0-2、P1-4、P1-5 需重新评估。建议以此作为第一个验证动作。
