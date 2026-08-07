# 笔顺数据说明（stroke data）

本方案的五笔画编码（横竖撇捺折）数据来源、探索过程与整合方式。

## 编码规则

五笔画分类（所有数据源统一）：

| 数字 | 字母 | 笔画 | 说明 |
|---|---|---|---|
| 1 | `h` | 横 | 含提（如"冰"的提） |
| 2 | `s` | 竖 | 含竖钩 |
| 3 | `p` | 撇 | |
| 4 | `n` | 点/捺 | 点与捺同归 |
| 5 | `z` | 折 | 其余全部（横折、竖弯钩、撇点等） |

例："着" = `43111325111` = 点撇横横横撇竖横折横横横（11 画）。

## 数据源

### 最终采用：hzbishun 13000.csv

- **仓库**：https://github.com/yindian/hzbishun（res/13000.csv）
- **内容**：20902 字，列 = `字序,字,画数,笔画码,Unicode,GB内码`
- **标准**：基于 **GB/T 25741-2010**（汉字部首序和笔顺）与 **GF 0014**（通用规范汉字笔顺规范）
- **覆盖**：GB2312 6763 字 **100% 覆盖**（0 缺失）
- **验证**：着/爱/办/贝/能/张/这/国/中/你/好/我 全部大陆标准 ✓
- **格式**：1-5 数字序列，build.py 转 hspnz

### 探索过程（为什么是它）

| 数据源 | 结果 |
|---|---|
| rime-stroke 官方码表 | 台湾 CNS11643 笔顺（如"着"12 画 vs 大陆 11 画），**不适用** |
| Conway Stroke Data（stroke-input） | 香港开发者，简体缺 1953 字（爱/办/贝/闭/编 等日常字缺失），**覆盖不全** |
| hanzi-writer-data / makemeahanzi | SVG 几何数据，需自写"几何→笔画类型"转换算法（横折/弧线撇/点分不清，5 版调参失败），**转换不可靠** |
| Gemini 推荐（chaizi/其它） | 幻觉（chaizi 是拆字；多个仓库/API 不存在） |
| **hzbishun 13000.csv** | **GB 标准、20902 字、GB2312 全覆盖、直接是编码（免转换）** ✅ |

## 大陆 vs 台湾笔顺差异（知识）

两岸汉字笔顺规范不同，常见差异：

1. **"着"**：大陆 11 画 `43111325111`（点撇横横横撇竖横折横横横）；台湾码表 12 画（写法不同）
2. **"为"**：大陆 `4354`（点撇横折钩点）；台湾 `4354` 一致，但部分字不同
3. **笔顺规则差异**：
   - 横折钩/横撇的归类（台湾细分为横折、竖折等，大陆统一折）
   - "火"大陆 `4334`（点撇撇捺），台湾同
   - 竖心旁、走之底等偏旁笔顺两岸不同
   - 简化字（爱/贝/办）台湾无简体形，只有繁体（愛/貝/辦）
4. **关键**：大陆标准 = 《现代汉语通用字笔顺规范》（1997）+《通用规范汉字笔顺规范》（2021 实施）；台湾标准 = 教育部《常用国字标准字体笔顺手册》

## 整合方式（build.py）

```python
def load_stroke(path):
    """读 data/hzbishun_13000.csv → {char: [codes]}"""
    # CSV 列: 字序,字,画数,笔画码,Unicode,GB内码
    # 笔画码 1-5 → hspnz (CONWAY_DIGIT_MAP)
```

- 单字表：GB2312 6763 字全量（含频次排序）
- 词组表：jieba 高频词（词内所有字在码表内）
- 超长编码（>32 笔）过滤（8 个字，生僻字）

## 复现步骤

```sh
# 1. 获取数据源 (已存入 data/hzbishun_13000.csv)
curl -L https://raw.githubusercontent.com/yindian/hzbishun/master/res/13000.csv \
  -o data/hzbishun_13000.csv

# 2. 构建
python3 -B scripts/build.py          # 生成 build/*.yaml
# 3. 校验
python3 -B scripts/validate.py
# 4. 打包 (predict.db 单独加入)
cd /tmp && mkdir -p zb && cd zb
cp /var/minis/shared/rime-stroke-zh/build/*.yaml .
cp /var/minis/shared/rime-stroke-zh/predict.db .
zip -r /var/minis/shared/rime-stroke-zh/dist/stroke_zh.zip .
```

## 文件

- `data/hzbishun_13000.csv` — 笔顺主数据（20902 字，GB 标准）
- `data/stroke_official.dict.yaml` — 官方 rime-stroke 原始码表（保留备用/参考）
- `data/jieba_dict.txt` — 词组数据源
- `predict.db` — 上屏预测库（生成流程见 Mac 端 ~/projects/stroke-zh-tools/README.md）
