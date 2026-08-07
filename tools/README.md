# stroke-zh 预测工具 (predict.db 生成)

为 RIME 笔画输入方案 (stroke_zh) 生成「上屏后预测」数据库 (predict.db)。
方案本体在 iPhone 上维护（Minis 环境 /var/minis/shared/rime-stroke-zh/）。

## 依赖

- Homebrew: `brew install librime marisa`（提供 librime/marisa 库与头文件）
- Xcode Command Line Tools（clang++）
- darts.h（已放入本目录，来自 darts-clone）

## 文件说明

| 文件 | 说明 |
|---|---|
| `build_predict` | 已编译工具 (arm64)，从 stdin 读 `key\tvalue\tweight` 生成 predict.db |
| `librime-predict/` | librime-predict 插件源码（tools/build_predict.cc 是生成工具） |
| `librime-src/` | librime 源码头文件（编译依赖，仅用头文件，不编译） |
| `librime-build-config/` | 手动生成的 build_config.h（librime 的 cmake 产物，编译需要） |
| `darts.h` | darts-clone 单头文件（predict_db.h 依赖） |
| `predict_data.txt` | 预测数据：`key\tvalue\tweight`（从 jieba 词库生成二元组，39950 条） |
| `predict.db` | 最终产物：预测数据库（535KB，已打包进 iPhone 的 stroke_zh.zip） |
| `marisa.tar.gz` | marisa-trie 源码头文件包（备用） |

## 重新编译 build_predict

```sh
cd ~/projects/stroke-zh-tools/librime-predict
clang++ -std=c++17 tools/build_predict.cc src/predict_db.cc \
  -I~/projects/stroke-zh-tools/librime-src/src \
  -I~/projects/stroke-zh-tools/librime-build-config \
  -I~/projects/stroke-zh-tools/librime-predict/src \
  -I/opt/homebrew/include \
  -I~/projects/stroke-zh-tools \
  -L/opt/homebrew/lib -lrime -lmarisa \
  -o ~/projects/stroke-zh-tools/build_predict
```

## 生成 predict.db

```sh
~/projects/stroke-zh-tools/build_predict ~/projects/stroke-zh-tools/predict.db < predict_data.txt
```

预测数据（predict_data.txt）更新：在 iPhone 的 Minis 环境跑
`make_predict_data.py`（逻辑复刻 librime-predict/tools/make_predict_data，从 jieba 词库生成二元组）。

## 数据格式（predict_data.txt）

每行 `key\tvalue\tweight`：
- key = 已上屏的词（如「你」），value = 预测的下一个词（如「们」），weight = 权重
- `$\t了\t883634` 表示句子开头预测「了」

## 相关

- RIME 方案：iPhone 上 /var/minis/shared/rime-stroke-zh/（build.py 生成方案，predict.db 打包进 dist/stroke_zh.zip）
- 元书输入法：stroke_zh.schema.yaml 内 predictor 配置（db: predict.db, max_candidates: 5, max_iterations: 1）

## 更新 (2026-08-06)

笔顺主数据源已切换为 **hzbishun 13000.csv**（GB/T 25741 大陆简体标准，GB2312 全覆盖）,
不再用 Conway/台湾码表。Conway 相关文件（librime-predict 源码等）保留作预测库生成工具,
与笔顺数据无关。详见 iPhone 项目 /var/minis/shared/rime-stroke-zh/docs/STROKE_DATA.md。
