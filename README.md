# stroke-zh — 简体笔画输入方案 + 元书输入法皮肤

**纯笔画输入**（横竖撇捺折），不用拼音也能流畅打字。为 iOS 设计，跑在**元书输入法**（新一代 RIME 输入法）上：单字 + 词组快打 + 上屏预测 + 自动造词 + 可选拼音辅助，全部离线、无广告、无颜文字键。

## 功能一览

| 功能 | 说明 |
|---|---|
| **单字输入** | 7953 个常用简体字，按大陆标准笔顺打（一丨丿丶𠃍 → h/s/p/n/z） |
| **词组快打** | 30.9 万词组（雾凇 rime-ice，含成语/现代词，2~4 字），**每字打前 4 笔**即出词（不足 4 笔打全部） |
| **上屏预测** | 打完上屏自动预测下一个词（连续 3 轮） |
| **自动造词** | 词库没有的词（人名/术语），打全码上屏一次即自动收录 |
| **拼音辅助**（可选） | 笔画打不出时一键切到拼音 T9 九宫格（按 abc/def/ghi 键出候选），**支持模糊音**（平翘舌/前后鼻不分，打 zi 也出「知」） |
| **清除键** | 打错一键清空，不用狂按退格 |
| **双皮肤** | 纯笔画版 / 笔画拼音版（切换键在右下角，两键盘对称） |

## 安装（5 分钟）

1. App Store 安装**元书输入法**
2. **导入方案**（二选一）：
   - `dist/stroke_zh.zip` — 纯笔画方案
   - `dist/stroke_zh_plus.zip` — 笔画 + 拼音方案（含 pinyin_lite，T9 九宫格）
3. **导入皮肤**（与方案包配套）：
   - `dist/stroke_zh.cskin` — 「笔画增强」（纯笔画，配 stroke_zh.zip）
   - `dist/stroke_zh_pinyin.cskin` — 「笔画拼音」（带 T9 切换，配 stroke_zh_plus.zip）
4. 系统键盘添加元书，输入方案选「笔画·增强」

## 打字规则

| 场景 | 怎么做 |
|---|---|
| 打单字 | 按笔顺打：横竖撇捺折 = 一丨丿丶𠃍。如 `pszh` → 的 |
| 打词组 | **每字前 4 笔，连续打**：我们 = `phsh`+`psns`；效果 = `nhpn`+`szhh` |
| 打错了 | 点「清除」键一键清空重来 |
| 缺词（自动造词） | 每字打**全码**上屏一次，之后就有 4 笔简码 |
| 拼音辅助 | 笔画键盘右下角「拼音」键 → 拼音九宫格（abc/def/ghi 键）→ 打完点「笔画」切回 |

**两个键盘切换键都在右下角同一位置**，切换时手指不用重新找。

## 方案设计

- **笔顺数据**：`data/hzbishun_13000.csv`（GB/T 25741 大陆标准，20902 字，GB2312 全覆盖，**非台湾笔顺**）
- **常用字**：GB2312 6763 + 通用规范汉字表 8105 基本区 = **7953 字**（PingFang 全支持，无乱码）
- **高频字简码**（v1.3）：1,017 条 1/2/3 笔简码词条 —— 打 3 笔是**精确匹配**，高频字进第一页（字频前 300 命中率 87%）。librime 候选先按剩余码长升序排、权重只是次级键，所以短前缀必须建真词条，靠前缀联想 + 高权重是无效的
- **词组编码**：每字前 4 笔拼接（只保留简码，不存全码），4 笔同码少、统一规则无选择负担；2 字词 = 8 笔码（5⁸≈39 万槽位，几乎不撞码）；只收 2~4 字词、编码 ≥4 笔
- **候选排序**：单字 = BLCU 25 亿字语料字频（与词组同量级）、词组权重 ×10、54 个高频少组词字 ×100、用户词典动态调频
- **预测**：predict.db（雾凇词库二元组，GB2312 过滤），librime-predict 插件
- **拼音**：pinyin_lite（简体，雾凇 rime-ice 基础词库过滤 62.9 万词条），九宫格按键发数字 1-9，词库离线转 T9 数字码（ni hao → 64426，运行时零派生规则 → 部署快）

详细设计见 **docs/DESIGN.md**（含 Google Gemini 调研结论与修改对照）。

## 文件结构

```
rime-stroke-zh/
├── scripts/          build.py（方案构建）/ validate.py（校验）/ build_pinyin.py（拼音方案）/ make_predict_data_ice.py（预测数据，雾凇后缀版）
├── data/             hzbishun_13000.csv（笔顺）/ rime_ice_base.dict.yaml（雾凇词组）/ rime_ice_8105.dict.yaml（拼音单字）/ jieba_dict.txt（单字频次）/ guifan8105.txt（字表）
├── cskin/            元书皮肤源（config + dark/light 布局）
├── predict.db        预测库
├── dist/             stroke_zh.zip / stroke_zh_plus.zip / stroke_zh.cskin / stroke_zh_pinyin.cskin
└── docs/             SETUP / STROKE_DATA / PREDICT / OPTIMIZATIONS
```

## 构建与校验

```sh
python3 scripts/build.py           # 笔画方案（build/*.yaml）
python3 scripts/build_pinyin.py    # 拼音方案
python3 scripts/validate.py        # 离线校验（模拟 librime 解析）
python3 scripts/make_predict_data_ice.py > predict_data.txt   # 预测数据（雾凇后缀版）
# Mac 端: build_predict predict.db < predict_data.txt   # 编译 predict.db（需要 librime 动态库）
# 打包由 build.py 完成（zip 含 build/*.yaml + predict.db）；缺文件时直接报错退出
```

> **升级到 v1.3 要清空用户词典**：简码与自动造词公式都变了，旧用户词典按旧公式记的词条与新码表不一致。

## 文档

| 文档 | 内容 |
|---|---|
| [docs/SETUP.md](docs/SETUP.md) | 换手机/重装从头部署 ★ |
| [docs/STROKE_DATA.md](docs/STROKE_DATA.md) | 笔顺数据来源、两岸差异、复现 |
| [docs/PREDICT.md](docs/PREDICT.md) | 预测库生成流程（Mac 工具） |
| [docs/OPTIMIZATIONS.md](docs/OPTIMIZATIONS.md) | 布局铁律、迭代记录、踩坑总结 |
| [docs/REGRESSION.md](docs/REGRESSION.md) | **回归验证清单**（改动后必查，防修 A 破坏 B）★ |

## 开发规范

- Python 脚本用 `ty` 类型检查：`ty check scripts/`
- 外部依赖用 uv 单文件语法：`uv run --with py3-yaml ...`

## 致谢

- RIME 引擎与社区（librime）
- 元书输入法（新一代 RIME iOS 输入法）
- hzbishun（GB/T 25741 大陆笔顺数据）
- rime-ice 雾凇（词组/拼音词库，jielong/现代词频）
- jieba（单字频次）
- librime-predict（上屏预测插件）
- CobraKeyboardSkins（元书官方皮肤模板）
- 语燕输入法（T9 拼音 algebra 规则参考）

