# AGENTS.md — stroke-zh 项目 AI 协作入口

> **任何 AI agent（Minis / Claude Code / Codex / Cursor 等）进入本项目，先读本文件。**
> 本文件是唯一入口，按任务路由到对应文档。README.md 是给人看的用户手册。

## 项目是什么

简体笔画输入方案（RIME/元书）+ 两套元书皮肤。
产物：`dist/*.zip`（输入方案）+ `dist/*.cskin`（皮肤，元书导入用）。

## 任务路由表

| 我要做什么 | 先读 | 改完必做 |
|---|---|---|
| **改皮肤**（cskin/、dist/*.cskin） | **docs/SKIN_MODIFICATION.md**（必读，含打包纪律） | `python3 scripts/verify_skin.py`（pre-commit 自动拦） |
| 改方案/词库（scripts/build.py、data/） | docs/REGRESSION.md | `python3 scripts/validate.py` |
| 改笔顺数据（data/） | docs/STROKE_DATA.md | `python3 scripts/validate.py` |
| 重装/换机部署 | docs/SETUP.md | — |
| 看迭代历史/布局铁律 | docs/OPTIMIZATIONS.md | — |

## 铁律（最高优先级，违反 = 破坏用户调好的成果）

1. **皮肤是用户花大量时间调好的成果。优先级：①不弄坏已有的 ②才做新功能。**
2. **`cskin/` 源目录只对应 stroke_zh_pinyin**；stroke_zh（笔画增强）**无源**（pinyin 特制版、无 t9pinyin、config name=笔画增强）——改它必须**解包旧包增量更新**，**禁止**源目录全量覆盖。
3. **改完皮肤必须跑 `verify_skin.py`**（对比 git HEAD 内部 md5：除预期新增 + config.yaml 外零差异）。提交时 pre-commit hook 自动执行，`--no-verify` 仅在确认破坏性变更时用。
4. **同步纪律**：用户**实测确认后**才 push；Mac git / GitHub / iSH 快照三方 md5 必须一致。
5. **小步、可验证**：先脚本校验，再回归清单（docs/REGRESSION.md），最后用户实测。

## 常用命令

```sh
python3 scripts/build.py                 # 构建方案（数据源 → yaml → zip，含 predict.db 硬检查）
python3 scripts/validate.py              # 方案离线校验 + 冷启动排名回归
python3 scripts/verify_skin.py           # 皮肤包完整性校验（工作区 vs HEAD）；--cached 看暂存区
python3 scripts/build_pinyin.py          # 拼音方案产物
python3 scripts/gen_symbolic.py          # 重新生成 symbolic 键盘布局（4 yaml + config patch）
python3 scripts/make_predict_data_ice.py # 预测数据生成（Mac 上跑）
git config core.hooksPath .githooks      # 新 clone 后安装 pre-commit hook（皮肤提交自动校验）
```

## 项目现状速览

- 双皮肤：**笔画增强**（无源包，纯笔画）/ **笔画拼音**（有源，笔画+T9 拼音）
- 词汇：雾凇词库（词组，词频策略见 scripts/build.py 注释与 docs/OPTIMIZATIONS.md 三）
- 验证工具链：build.py → validate.py → verify_skin.py（皮肤）→ REGRESSION.md 清单 → 用户实测
