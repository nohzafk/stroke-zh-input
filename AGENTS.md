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
| 改方案/词库/编码（scripts/build.py、data/） | docs/DESIGN.md（v1.4 编码方案）+ docs/REGRESSION.md | `python3 scripts/validate.py` + **`typing_test.py`（打字效果回归）** |
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
uv run --with pyyaml python3 scripts/typing_test.py   # 打字效果回归（44 用例，改编码后必跑）
python3 scripts/verify_skin.py           # 皮肤包完整性校验（工作区 vs HEAD）；--cached 看暂存区
python3 scripts/build_pinyin.py          # 拼音方案产物
python3 scripts/gen_symbolic.py          # 重新生成 symbolic 键盘布局（4 yaml + config patch）
python3 scripts/make_predict_data_ice.py # 预测数据生成（Mac 上跑）
git config core.hooksPath .githooks      # 新 clone 后安装 pre-commit hook（皮肤提交自动校验）
```

## 项目现状速览

- 双皮肤：**笔画增强**（无源包，纯笔画）/ **笔画拼音**（有源，笔画+T9 拼音）
- **v1.4 编码方案（视觉块输入）**：单字 1~7 笔任意笔数精确匹配（简码配额器）；词组 = 每字**自然码连续串**（我们 = `phshpsnsz`，我 4 笔+们 5 笔），自然码由首部件决定（3~5 笔部件打全 / >5 笔或独体前 4 笔），数据源 `data/chaizi-jt.txt` + BUSHOU 偏旁表。码 <6 笔词组不收、6-7 笔权重 ×0.001、8+ 笔正常；自动造词走 4 笔制（stem=全码）。详见 docs/DESIGN.md §v1.4
- 词汇：雾凇词库（词组，jieba 词频，词频策略见 scripts/build.py 注释与 docs/OPTIMIZATIONS.md）
- 验证工具链：build.py → validate.py → **typing_test.py（打字效果回归）** → verify_skin.py（皮肤）→ REGRESSION.md 清单 → 用户实测
