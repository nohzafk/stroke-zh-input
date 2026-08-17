# 皮肤修改操作规程（SKIN_MODIFICATION.md）

> **改皮肤前必读。** 任何对 `cskin/`、`dist/*.cskin` 的修改，先读完本文件再动手。
> 由仓库根 **AGENTS.md**（AI 协作入口）路由至此；改完必跑 `scripts/verify_skin.py`（金律 3）。

## 0. 为什么必须有这份文档（血泪史，先读）

用户原话（2026-08-17）：

> 「每次我让你调整皮肤，你就必然会修了一个东西然后破坏掉另一个东西，就像修复一个 bug 然后将以前修好的 bug 的代码又破坏了。」

这不是偶然事故，是**模式**。三次皮肤任务的破坏记录：

| 日期 | 任务 | 破坏 |
|---|---|---|
| 2026-08-11 | 英文键盘去逗号/问号 | scp 多文件到不同目录路径错乱，**dark 覆盖 light** |
| 2026-08-11 | 英文键盘底部行对齐 | 宽度用 percentage 相对容器理解错，布局跳变 |
| 2026-08-17 | 自定义 symbolic 标点键盘 | 拿源目录全量覆盖 `stroke_zh.cskin`，**破坏了它的特制 pinyin 布局、多塞 4 个 t9pinyin、皮肤名被改成"笔画拼音"** |

**三条根因**（每个都是方法缺陷，不是运气）：

1. **认知默认错误**：默认 `cskin/` 源目录 = 所有皮肤的真相。实际 `stroke_zh.cskin` 是历史特制版，**在仓库没有源**，只有 dist 里的包。拿源目录重建它 = 用"笔画拼音"的布局覆盖"笔画增强"的布局。
2. **验证方法错误**：拿"源目录 vs 新 zip"比对——这是**自己和自己比**，只能证明"新包 = 源目录"，证明不了"新包 = 旧包 + 预期变更"。破坏在包里发生了也检测不到。
3. **修改方式激进**：全量重建/覆盖式修改，而不是最小侵入（只增、只精确 patch）。修改面越大，破坏已调好布局的概率越高。

**教训一句话**：皮肤是用户花了大量时间调好的成果。**任何皮肤修改的第一原则是"别弄坏已有的"，第二原则才是"实现新功能"。**

## 1. 皮肤全貌（先看清再动手）

| | stroke_zh.cskin | stroke_zh_pinyin.cskin |
|---|---|---|
| 皮肤名（config.yaml `name:`） | **笔画增强** | **笔画拼音** |
| 仓库有无源 | **无**（只有 dist 里的包） | **有**（`cskin/` 源目录即此皮肤） |
| pinyin 布局 | **特制版**（与源目录内容不同！） | 源目录版 |
| t9pinyin（九键拼音） | **无**（config 无 `t9pinyin:` 节） | 有（4 个文件） |
| config.yaml 键盘节 | pinyin/alphabetic/numeric | pinyin/alphabetic/numeric/t9pinyin |

**推论**：
- 两皮肤的 alphabetic / numeric 布局文件**内容一致**（14 个公共文件），pinyin 4 个文件各自定制，t9pinyin 仅笔画拼音有。
- **`cskin/` 源目录 ≠ 全部真相**。它只是"笔画拼音"的源；"笔画增强"的 pinyin 特制版只存在于旧包里。
- 想重建 `stroke_zh.cskin` 的任何文件，**先解包旧包看它里面是什么**，不要假设它和源目录一样。

## 2. 金律（按优先级，全部必须遵守）

### 金律 1：最小侵入
- **只增不改**：新增按键/文件直接加，不动现有内容。
- 必须修改现有文件时，用**精确 patch**（在旧内容上替换最小片段），**绝不整体重建、绝不批量覆盖**。
- 每次修改问自己：这个改动会影响哪些已有的键/布局/样式？影响面之外的东西一个字节都不能变。

### 金律 2：动手前建基线
修改前先把当前发布版解包、记录内部文件 md5：

```sh
cd ~/projects/stroke-zh-input
git show HEAD:dist/stroke_zh.cskin > /tmp/base_sz.cskin
git show HEAD:dist/stroke_zh_pinyin.cskin > /tmp/base_szp.cskin
# 记录每个内部文件的 md5，或干脆保留 /tmp/base_*.cskin 备用
```

同时确认：**源目录 `cskin/` 与旧包里同名文件是否一致**？不一致的（如 stroke_zh 的 pinyin 4 文件）就是"无源特制版"，碰都不能碰。

### 金律 3：修改后铁律验证（防"修 A 破坏 B"的关键一步）
**禁止**拿"源目录 vs 新 zip"比对（自己和自己比，无意义）。

**可执行化（首选，已内置防呆）**：
```sh
python3 scripts/verify_skin.py             # 工作区 dist vs git HEAD
python3 scripts/verify_skin.py --cached    # 暂存区 vs HEAD（pre-commit hook 自动跑）
```
规则：删除文件 = 失败；非 config.yaml 内容变化 = 失败；新增文件 = 通过。
**pre-commit hook 已安装**（`.githooks/pre-commit`，`git config core.hooksPath .githooks`）：
暂存 dist/*.cskin 时自动运行校验，非预期变化直接阻止提交。
绕过 = `git commit --no-verify`（仅在确认破坏性变更必要时，需人工核对清单）。

**手工核对（脚本通过后仍应看一眼）**：

**验收标准**：除预期新增文件 + 预期修改的 config.yaml 外，`变化` 必须为空。出现任何非预期变化 = 破坏了旧布局，回退重做。

### 金律 4：样式复用
新键盘的样式名（`alphabeticButtonBackgroundStyle`、`systemButtonBackgroundStyle`、候选栏、preedit 等）**一律引用现有定义**，从现有布局文件抽取模板，保证视觉一致。不要新造一套颜色/圆角/字号。

### 金律 5：同步纪律
- 用户**实测确认后**才 push + 同步 iSH 快照（Mac git / GitHub / iSH 三方 md5 必须一致）。
- 用户没确认前，commit 留在本地即可。

## 3. 打包操作规范（有源 vs 无源）

### stroke_zh_pinyin.cskin（有源，可整体重建）
```sh
# cskin/ 源目录 → 重新打包
python3 - <<'EOF'
import zipfile, os
with zipfile.ZipFile("dist/stroke_zh_pinyin.cskin", "w", zipfile.ZIP_DEFLATED) as z:
    for root, _, files in os.walk("cskin"):
        for fn in sorted(files):
            p = os.path.join(root, fn)
            z.write(p, arcname=os.path.join("stroke_zh_pinyin", os.path.relpath(p, "cskin")))
EOF
```

### stroke_zh.cskin（无源，**必须**解包旧包增量更新）
```sh
# 1) 解包 git HEAD 的旧包
git show HEAD:dist/stroke_zh.cskin > /tmp/sz.cskin && cd /tmp && rm -rf fix_sz && mkdir fix_sz && cd fix_sz && unzip -q ../sz.cskin
# 2) 只复制新增文件进解包目录（用源目录的，仅限新增文件）
# 3) config.yaml 在旧包版本上 patch（保留 name=笔画增强、不引入 t9pinyin 节）
# 4) 重新打包，然后按金律 3 验证
```

**绝对禁止**：把 `cskin/` 源目录全量覆盖到 `stroke_zh` 解包目录（会把特制 pinyin 换掉、塞进 t9pinyin、改名）。

## 4. 修改后必查清单

0. **金律 3 自动校验**：`python3 scripts/verify_skin.py` 通过（pre-commit hook 也会拦）；**校验脚本本身改过时，必须用"故意破坏"场景验证它能失败**（2026-08-17 教训：verify_skin.py 初版有 bug，篡改包测不出来，靠构造破坏案例才暴露）
1. **REGRESSION.md 皮肤清单**（#11~#21）：布局行高、右列渲染、切换空白、dark 配色、皮肤名冲突、长按变体等逐项过。
2. **validate.py**（涉及方案时才需要）：`uv run --with py3-yaml python3 scripts/validate.py`。
3. **YAML 合法性**：新布局文件用 `uv run --with pyyaml python3 -c "import yaml; yaml.safe_load(open('...'))"` 确认无语法错误；颜色值必须带引号（`#1C1C1E` 不带引号会被 YAML 当注释解析成 null，样式静默失效）。
4. **键引用完整性**：布局 `Cell:` 引用的按键名必须都在同文件定义（缺失 = 空白键）。

## 5. 参考资料

- 元书官方文档（改前查）：`https://ihsiao.com/apps/hamster/v3/docs/guides/skins/`（structure / layout / styles / action / parameters）
- 本项目的皮肤迭代史：`docs/OPTIMIZATIONS.md` 五（皮肤迭代）与五·七（布局铁律）
- 回归清单：`docs/REGRESSION.md`
