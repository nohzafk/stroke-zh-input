# 上屏后预测（predict.db）— 原理与生成流程

本方案支持「上屏后预测下一个词」：打「你」上屏 → 候选栏出现「们/好/家」。
基于 librime-predict 插件（元书已内置编译支持）。

## 原理

- librime-predict 插件：`predictor` processor + `predict_translator` translator
- 方案 schema 配置：`predictor: {db: predict.db, max_candidates: 9, max_iterations: 3}`
- **predict.db**：二进制预测库（key=已上屏词 → value=预测词 列表+权重）
- 数据从雾凇词库（rime-ice）生成二元组：词「你好」→ key=「你」value=「好」；句子开始用 `$`：`$ 了`

## 文件

| 文件 | 说明 |
|---|---|
| `scripts/make_predict_data.py` | 生成预测文本数据（GB2312 过滤，62188 条） |
| `predict.db` | 最终预测库（842KB，已打包进 stroke_zh.zip） |
| Mac 端 `~/projects/stroke-zh-tools/` | build_predict 工具 + librime-predict 源码 + README |

## 重新生成 predict.db 流程

predict.db 的构建工具（build_predict）依赖 librime C++ 环境，**在 iSH 上编译/运行会崩溃**（模拟层限制），必须在**远程 Mac**（`randall@192.168.0.243`，brew 已装 librime/marisa）上做：

```sh
# 1. iSH: 生成预测数据 (GB2312 过滤, 只保留常用字词)
python3 -B scripts/make_predict_data.py > /tmp/predict_data.txt

# 2. 传到 Mac
scp /tmp/predict_data.txt randall@192.168.0.243:/tmp/predict_data.txt

# 3. Mac: 生成 predict.db
ssh randall@192.168.0.243 \
  "~/projects/stroke-zh-tools/build_predict /tmp/predict.db < /tmp/predict_data.txt"

# 4. 传回并更新项目
scp randall@192.168.0.243:/tmp/predict.db ./predict.db

# 5. 重新打包 stroke_zh.zip (含 predict.db)
cd /tmp && mkdir -p zb && cd zb
cp /var/minis/shared/rime-stroke-zh/build/*.yaml .
cp /var/minis/shared/rime-stroke-zh/predict.db .
zip -r /var/minis/shared/rime-stroke-zh/dist/stroke_zh.zip .
```

## Mac 端工具（~/projects/stroke-zh-tools/）

- `build_predict`：已编译工具（arm64），从 stdin 读 `key\tvalue\tweight` 生成 predict.db
- `librime-predict/`：插件源码（tools/build_predict.cc）
- `librime-src/`、`librime-build-config/`、`darts.h`：编译依赖（头文件）
- README.md：完整编译/生成文档

重新编译 build_predict（Mac 上）：

```sh
cd ~/projects/stroke-zh-tools/librime-predict
clang++ -std=c++17 tools/build_predict.cc src/predict_db.cc \
  -I~/projects/stroke-zh-tools/librime-src/src \
  -I~/projects/stroke-zh-tools/librime-build-config \
  -I~/projects/stroke-zh-tools/librime-predict/src \
  -I/opt/homebrew/include -I~/projects/stroke-zh-tools \
  -L/opt/homebrew/lib -lrime -lmarisa \
  -o ~/projects/stroke-zh-tools/build_predict
```

## 注意事项

- **iSH 限制**：不要在 iSH 上编译/运行任何 librime 相关程序（会带崩 Minis 宿主）——C++ 编译任务走远程 Mac
- **数据过滤**：make_predict_data.py 已过滤生僻字（GB2312 常用字 + 词频≥50）——预测候选干净
- **预测参数**：max_candidates 9（与 page_size 一致）、max_iterations 3（连续预测）——在 build.py schema 模板里，改后需重建方案
