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

**打词组规则**：每个字打前 4 笔（不足 4 笔打全部），连续打不选字。
**长词联想**：打前几个字（如「权限」2 字 8 码）→ 整个词（权限范围）出现在候选（前缀联想 enable_completion）；打前 3 字 12 码几乎唯一命中。

## 四、上屏后预测

| 版本 | 内容 |
|---|---|
| 1.4.0 | librime-predict 插件 + predict.db（jieba 二元组） |
| 2.0.0 | predict.db 换雾凇词库二元组（8.3 万条，词频≥50） |
| 优化 | 连续预测 3 轮、9 候选（max_iterations 3 / max_candidates 9） |
| 优化 | predict.db 重建：**GB2312 过滤**（候选无生僻字，62188 条） |

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
| `encoder.rules`（AaAbAcAdBaBbBcBd...） | 主 dict 头部 | 造词编码公式 = 每字前 4 笔（与简码一致） |
| `reverse_lookup_translator` + `reverse_lookup` 段 | schema | 生成 reverse.bin 反查库（encoder 必需） |

**实测**（2026-08-07）：打"转圈"（词库没有）每字全码上屏 → 自动收录 → 4 笔简码可打。
注意：只加 `enable_encoder` 不生效（librime 源码确认还需 dict encoder.rules + reverse 库）。

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
| `scripts/build.py` | 构建 RIME 方案（数据源→yaml→zip） |
| `scripts/validate.py` | 离线校验（dict 头部闭合/编码合法/Cell 引用） |
| `scripts/make_predict_data.py` | 生成预测数据（GB2312 过滤） |

**开发规范**：Python 文件用 `ty` 类型检查；外部依赖用 uv 单文件语法。
