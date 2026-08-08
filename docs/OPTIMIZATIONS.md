# 优化记录（迭代历史）

本方案从 v1.0.0 至今的优化记录，按功能分类。每条记录含「问题 → 方案 → 关键参数」。

## 一、笔顺数据（大陆标准）

| 版本 | 内容 |
|---|---|
| 1.0.0 | 官方 rime-stroke（台湾 CNS11643）——「着」12 画 vs 大陆 11 画，**放弃** |
| 探索 | Conway Stroke Data（香港，缺 1953 简体字）；hanzi-writer（SVG 需转换算法，5 版失败）；Gemini 推荐全幻觉 |
| **1.5.0** | **hzbishun 13000.csv**（GB/T 25741 国标，20902 字，GB2312 全覆盖）——最终采用 |

详见 docs/STROKE_DATA.md

## 二、常用字过滤与扩充

| 版本 | 内容 |
|---|---|
| 1.3.0 | **GB2312 6763 常用字**（PingFang 100% 支持，消除乱码）——从 11 万单字过滤 |
| **1.9.0** | **扩到 7953 字**：GB2312 6763 + 通用规范汉字表 8105 基本区增量 1190 字（啰/瞭/玺/玥/乂 等） |
| — | 8105 里的 273 个扩展区字（CJK-A/B+）因 iOS 字体缺失**不加入**（乱码） |

关键：`build.py` 的 `load_common_chars()`（GB2312 内置编码 + data/guifan8105.txt）

## 三、词组匹配（核心优化）

| 问题 | 方案 | 参数 |
|---|---|---|
| RIME 词组编码=每字完整笔画拼接，打不全前字笔画无法接下一字 | **4 笔简码**：每字前 4 笔拼接（统一规则，无选择难题） | `[:4]` |
| 词组被单字碾压（排 229 位） | 词组权重 ×100 → **×10**（单字词组平衡） | `PHRASE_WEIGHT_FACTOR = 10` |
| 3 笔简码同码爆炸（41 个） | 统一 4 笔（同码 0-9 个） | 每字 4 笔 |
| 「我们」打不出 | 简码命中（phshpsns 直接第一） | — |
| 1.10.0 | 词组阈值 100 → 50：3 万 → 8.6 万词（jieba 词频≥50） | `PHRASE_MIN_FREQ = 50` |
| **2.0.0** | **词库换雾凇**：jieba → rime-ice 雾凇 base（62 万词，词频≥100），含成语/现代词/专业词；jieba 保留仅作单字频次 | `rime_ice_base.dict.yaml` |
| **2.1.0** | **单字/词组彻底分流**：雾凇词组量太大（624k 词条）把常用单字挤出第一页（子#35/天#57/真#179）→ 词组只留"每字前4笔"简码（314k 词条），schema 拆双 translator：单字 `enable_completion:true` 前缀联想 + 词组 `enable_completion:false` 精确匹配 | 见 docs/DESIGN.md |
| **v1.3.0** | **词组表再收缩**：5/6 字词要打 20/24 笔无实用性 → 不收；编码 ≤3 笔的伪词组（一人/十一/一一）会占掉简码席位 → 不收。314,153 → **309,416** 条 | `PHRASE_MAX_LEN = 4`、`PHRASE_MIN_CODE_LEN = 4` |

**打词组规则**：每个字打前 4 笔（不足 4 笔打全部），连续打满编码（2 字=8 笔、3 字=12 笔、4 字=16 笔）精确上屏。
**单字规则（v1.3 起）**：1/2/3 笔是简码精确匹配 → 高频字第一页；4 笔以上走前缀联想。

## 三·五、候选排序与高频字简码（v1.3 核心）

**问题（P0-1，用户真机确认）**：干净重装 + 空用户词典，打 `szh` 三笔，「是」不在第一页。v1.2 声称的「single_char_filter 单字优先」是假的。

**根因**（librime `dict/dictionary.cc:73-84`）：候选先按 `remaining_code.length` **升序**排，权重只是次级键。3 笔前缀下单字全码还剩 6 笔、8 笔词组码只剩 5 笔 → 词组整段排在单字前，权重再高也翻不过来。
`single_char_filter` 救不了：它遇到第一个 completion 候选就 `break`（`gear/single_char_filter.cc:41-45`），而 `table_translator` 给一切「剩余编码非 0」的候选都打 completion 标记（`gear/table_translator.cc:82-85`）→ 前缀联想段它一个字也管不到。

| 措施 | 方案 | 关键参数 |
|---|---|---|
| **高频字简码表** | 给高频字建 1/2/3 笔**真词条**（短前缀变精确匹配，五笔/郑码/仓颉通行做法）。名额**按前缀发**：每前缀 9 席，先扣已有精确匹配占位，再给「全码=该前缀」的字（十/口/工/士）无条件留一席，余额按字频降序发 | `SHORTCODE_LEVELS = (1,2,3)`、`PAGE_SIZE = 9`；产出 **1,017** 条（1 笔 43 / 2 笔 204 / 3 笔 770） |
| **单字权重换字频表** | jieba 单字项是分词副产物（10³~10⁵），词组权重是雾凇词频×10（10⁵~10⁸）→ 打满 8 笔全码的单字（明/果/者/李/林）被同码词组压到第二页。改用 BLCU《25 亿字语料汉字字频表》（10⁵~10⁷，与词组同量级） | `data/rime_ice_8105.dict.yaml` 权重列；缺频次退回 jieba |
| **移除 single_char_filter** | filters 只留 `uniquifier`。留着零收益，且掩盖上面两个真问题 | schema `filters: [uniquifier]` |
| **回归测试** | `validate.py` 校验项 5：按 `dictionary.cc` 规则重放全部 318,386 条词条（空用户词典、同权重取最坏名次），逐字频段统计 3 笔命中率并断言下限 | `HIT_RATE_FLOOR` 六段 |

**A4 实测命中率**（3 笔进第一页，v1.2 → v1.3）：

| 字频段 | v1.3 | 断言下限 | 组合天花板 |
|---|---|---|---|
| 1-100 | **96%** | 93% | 98% |
| 1-300 | **87%** | 84% | 89% |
| 1-600 | **71%**（v1.2 为 19%） | 68% | 73% |
| 1-1000 | **57%** | 54% | 58% |
| 1001-2000 | 13% | 11% | 13% |
| 2001-3500 | 5% | 4% | 5% |

**天花板是组合上限**：3 笔前缀只有 5³=125 个 × 每页 9 席 ≈ 1,100 席，而字频前 600 的字挤在 104 个前缀上（`szh` 一个前缀 65 字、`hsh` 38 字）。前 600 段理论上限 73%，实测 71%，差的 2 点是「留位」规则的代价（保十/口/工/士 可打，优于多抬两个能退到 4 笔的字）。
**已知例外 4 个**（断言允许 4 个）：最/都/日/可 撞在最拥挤的前缀（szh/hsh/hsz）上，组合无解。

## 四、上屏后预测

| 版本 | 内容 |
|---|---|
| 1.4.0 | librime-predict 插件 + predict.db（jieba 二元组） |
| 2.0.0 | predict.db 换雾凇词库二元组（8.3 万条，词频≥50） |
| 优化 | 连续预测 3 轮、9 候选（max_iterations 3 / max_candidates 9） |
| 优化 | predict.db 重建：**GB2312 过滤**（候选无生僻字，62188 条） |
| **v1.2.0** | **predict.db 重建为纯后缀 value**（词「下一页」→ key=下 value=一页；8.3 万条→66.9 万条，MIN_FREQ 100）——修复预测点击重复（下→下面→「下下面」根因：08-07 版 value 存完整词，点击上屏整词拼接） |

详见 docs/PREDICT.md

## 五、皮肤（cskin）迭代

| 版本 | 内容 |
|---|---|
| v1 | 两行布局（6+5 键）——用户觉得布局奇怪 |
| v2 | **九宫格**（仿 iOS 笔画键盘，基于官方 T9 皮肤模板） |
| 迭代 | 浅色主题（dark/light 均浅色 → 后改 dark 深色/light 浅色） |
| 迭代 | 英文键盘行4：`123 ， 空格 。 ？ #+= 中英 回车`（后去句号/问号） |
| 迭代 | 符号键盘：自定义 symbolic 失败（元书不支持/空白）→ **用元书内置** |
| 迭代 | 「？」键 → **清除**（`#重输`，打错一键清空） |
| 迭代 | 工具栏：加过（中英/剪贴板/常用语/emoji）→ **全部移除**（保持极简） |
| 迭代 | 上划数字：加过 → **取消**（只能打 1-5 没用） |
| 迭代 | 左列符号栏：t9Symbols（拼音提示）→ **symbols 固定标点**（`，。？！、；：「」（）…—～`），去单元格背景（无阴影） |
| 迭代 | 深色模式颜色统一：笔画键/中英键 黑色 → **白色**（与其他键一致） |
| 迭代 | 折键「乙」→ **「𠃍」**（横折，系统笔画键盘同款，U+200CD 扩展区字元书可显示） |
| 迭代 | 英文键盘**长按拉丁变体**：字母→声调变体（a→àáâäæāå）、数字→上标/度（0→°、1→¹），仿 iOS 系统 |
| 最终 | 主键盘 = 符号列 + 九宫格（横竖撇捺折清除 / 123 空格中英）+ 退格回车列 |

**皮肤格式要点**（元书 v3 文档）：
- cskin = zip（**必须含一层皮肤文件夹**：`stroke_zh/config.yaml + dark/ + light/ + demo.png`）
- config.yaml：pinyin/alphabetic/numeric 键盘映射（iPhone portrait/landscape）
- 布局：keyboardLayout（HStack/VStack/Cell）+ 按键定义 + 样式（buttonStyleType 必须）
- 动作：character/symbol/space/backspace/enter/keyboardType/shortcut(#重输 等)
- 长按变体：`hintSymbolsGridStyle` 引用网格（symbolRows + 每格 foregroundStyle + action）
- 深浅色：dark/ 深色主题、light/ 浅色主题（各一套完整布局）
- **左列动态候选无法实现**：t9Symbols 由元书控制（符号↔拼音两态），皮肤无法接 RIME 动态候选
- **脚本按键**：元书 Pro 支持 JS 脚本（`{runScript: "名称"}`），可做快捷短语/剪贴板/网络等，未采用

## 五·五、自动造词（enable_encoder）

| 配置 | 位置 | 说明 |
|---|---|---|
| `enable_encoder: true` + `encode_commit_history` | schema translator | 开启自动造词 |
| `encoder.rules`（**逐字展开**） | 主 dict 头部 | 造词编码公式 = 每字前 4 笔；2 字词 `AaAbAcAdBaBbBcBd`（8 位）、3 字词 12 位、4 字词 16 位 |
| `columns: text/code/weight/stem` | `stroke_zh_base.dict.yaml` | `stem` 存该字**全码**（简码行也写全码），造词反查只取 stem |
| `reverse_lookup_translator` + `reverse_lookup` 段 | schema | 生成 reverse.bin 反查库（encoder 必需） |

**实测**（2026-08-07）：打"转圈"（词库没有）每字全码上屏 → 自动收录 → 4 笔简码可打。
注意：只加 `enable_encoder` 不生效（librime 源码确认还需 dict encoder.rules + reverse 库）。

**v1.3 两处修正**：
- **公式必须逐字展开**：`algo/encoder.cc` 里 `Aa` = 第 1 字第 1 码，而 `U`~`Z` 是**倒数**索引（`Z` = 末字，`encoder.cc:120`）。缩写公式在长词上取错位。
- **`stem` 列保护造词**：`UnityTableEncoder::TranslateWord` 先 `LookupStems` 再 `ReverseLookup`，反查取值来自 `set<string>`（字典序 → 简码排在全码前），且 DFS 组合上限只有 32（`encoder.cc:15`）。不给 stem，简码会被当成该字编码去拼 → 造词编码错，或 3/4 字词的 DFS 被简码组合挤爆而漏掉正确编码。

## 五·六、拼音辅助方案（pinyin_lite）

| 项目 | 说明 |
|---|---|
| 方案 | pinyin_lite（简体拼音，雾凇 rime-ice 词库 base 40.9万 + 8105 单字表 = 62.9 万词条） |
| T9 九宫格 | 词库**离线转 T9 数字码**（ni hao → 64426），运行时零派生规则 → 40 万词条秒级部署 |
| 模糊音 | 词库端生成变体（zh↔z ch↔c sh↔s；an↔ang en↔eng in↔ing uan↔uang ian↔iang），打 zi 也出「知」 |
| 切换 | 皮肤按键 combine: switchRimeSchema + keyboardType（必须成对，否则"切回笔画但打拼音"） |
| 构建 | scripts/build_pinyin.py（雾凇过滤 + 模糊音变体 + T9 转码 + 8105 合并）；Mac 端编译（python3.14，iSH 慢） |

### 模糊音（平翘舌/前后鼻不分）

**目标**：拼音不准也能打对字（如打 zi 出「知/之」、打 yin 出「英/应」）。

**实现原理**：**词库端生成变体，运行时零开销**——build_pinyin.py 对每个词的拼音串应用规则生成变体，变体也转 T9 码入库。编译时多花 4 秒，打字时无任何性能损失。

**规则集**（`scripts/build_pinyin.py` 的 `FUZZY_SETS`）：
| 类型 | 规则 |
|---|---|
| 平翘舌 | zh↔z、ch↔c、sh↔s |
| 前后鼻 | an↔ang、en↔eng、in↔ing |
| 前后鼻（介音） | uan↔uang、ian↔iang |

**效果验证**（实测）：
- 打 `94`（zi 码）→ 出「子/自」，也出「知/之」（原 zhi，平翘舌不分）
- 打 `264`（ang 码）→ 出「昂」，也出「安/按」（an，前后鼻不分）
- 打 `946`（yin 码）→ 出「因/音」，也出「英/应」（ying，前后鼻不分）

**代价**：词条膨胀约 1.43 倍（40.9 万 → 62 万，30.5% 的词含模糊音音节），部署稍慢但可接受。

## 五·七、双皮肤与布局铁律

| 皮肤 | 名称 | 内容 |
|---|---|---|
| stroke_zh.cskin | 笔画增强 | 纯笔画（无拼音功能） |
| stroke_zh_pinyin.cskin | 笔画拼音 | 笔画 + T9 拼音（切换键右下角） |

**布局铁律**（用户实测验证，违反则渲染异常）：
1. **只给特殊元素设比例，其余吃剩余**：中列仅底部行设 `style: bottomRowStyle`（height 1/4），行1/行2 不设 style（自动均分剩余）；全部设比例 = 触发 bug
2. **右列**：仅切换键设 `size.height '1/4'`，backspace/enter 不设 size（吃剩余 3/8）；全部显式设比例 = 最后一个按钮渲染丢失
3. **config.yaml 必须注册 `t9pinyin:` 节**（keyboardType: t9pinyin 的目标键盘），否则切换后空白
4. **dark 颜色**：候选文字 #FFFFFF、高亮背景 #707070、键盘背景 #00000003、键 #707070/#4C4C4C（从 light 复制转深色必须改背景+文字+候选全套，否则白底白字全白）

## 六、构建/校验

| 脚本 | 用途 |
|---|---|
| `scripts/build.py` | 构建 RIME 方案（数据源→yaml→zip），自动打包 `predict.db` |
| `scripts/validate.py` | 离线校验（dict 头部闭合/编码合法/stem 列/Cell 引用/**冷启动排名回归**） |
| `scripts/make_predict_data_ice.py` | 生成预测数据（雾凇词库，**纯后缀 value**，GB2312 过滤） |

**v1.3 打包硬失败（A7-1）**：`predict.db`（或拼音版的 `pinyin_lite.*`）缺文件时 `build.py` 直接 `SystemExit`，错误里带重建提示（`build_pinyin.py` / `docs/PREDICT.md`）。此前是「只生成 yaml，predict.db 手动加回 zip」——手动步骤漏过一次就产出没有预测功能的包，且无任何提示。

**开发规范**：Python 文件用 `ty` 类型检查；外部依赖用 uv 单文件语法。
