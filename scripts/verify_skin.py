#!/usr/bin/env python3
"""皮肤包修改校验 — SKIN_MODIFICATION.md 金律 3 的可执行化。

对比 git HEAD 与 工作区/暂存区 的 dist/*.cskin 内部文件 md5。
规则（--strict 默认开启）：
  - 删除 (removed) 必须为空：皮肤文件不应被删
  - 内容变化 (changed) 只允许 config.yaml（键盘映射/皮肤名变化只应发生在这）
  - 新增 (added) 任意：新文件（如新键盘布局）是合理变更

用法:
  python3 scripts/verify_skin.py             # 工作区 dist vs HEAD
  python3 scripts/verify_skin.py --cached    # 暂存区 vs HEAD (pre-commit hook 用)
  python3 scripts/verify_skin.py --allow-config-changed  # 临时放行非 config.yaml 变化 (谨慎, 需人工确认)

返回码: 0=通过  1=存在非预期变化
"""
import argparse
import hashlib
import io
import subprocess
import sys
import zipfile

SKINS = ["dist/stroke_zh.cskin", "dist/stroke_zh_pinyin.cskin"]


def md5zip(data):
    zf = zipfile.ZipFile(io.BytesIO(data))
    return {n: hashlib.md5(zf.read(n)).hexdigest() for n in zf.namelist() if "/" in n}


def read_ref(prefix, path):
    """prefix: 'HEAD:' 或 ':'（暂存区）"""
    r = subprocess.run(["git", "show", f"{prefix}{path}"], capture_output=True)
    return r.stdout if r.returncode == 0 else None


def read_worktree(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cached", action="store_true", help="对比暂存区 (pre-commit hook 用)")
    ap.add_argument("--allow-config-changed", action="store_true",
                    help="放行非 config.yaml 文件的内容变化 (谨慎，需人工确认破坏性变更)")
    args = ap.parse_args()

    ref = ":" if args.cached else "HEAD"
    label = "暂存区" if args.cached else "工作区"
    problems = []
    for skin in SKINS:
        new = read_ref(":", skin) if args.cached else read_worktree(skin)
        old = read_ref("HEAD:", skin)
        if new is None:
            continue  # 暂存区/工作区无此文件 = 未改动
        if old is None:
            print(f"== {skin}: 新增皮肤包 (HEAD 无此文件) ==")
            continue
        om, nm = md5zip(old), md5zip(new)
        added = sorted(set(nm) - set(om))
        removed = sorted(set(om) - set(nm))
        changed = sorted(n for n in set(om) & set(nm) if om[n] != nm[n])
        print(f"== {skin} ({label} vs HEAD) ==")
        print("  新增:", ", ".join(added) if added else "无")
        print("  删除:", ", ".join(removed) if removed else "无")
        print("  变化:", ", ".join(changed) if changed else "无")
        if removed:
            problems.append(f"{skin}: 删除了文件 {removed}")
        bad = [c for c in changed if c != "config.yaml"]
        if bad and not args.allow_config_changed:
            problems.append(f"{skin}: 非预期内容变化 {bad} (只允许 config.yaml)")
    if problems:
        print("\n✗ 皮肤校验失败:")
        for p in problems:
            print("  -", p)
        print("  处理: 按 docs/SKIN_MODIFICATION.md 回退或修复后重试;")
        print("        确属必要破坏性变更时加 --allow-config-changed 并人工核对清单。")
        return 1
    print("\n✓ 皮肤包校验通过 (新增文件 + config.yaml 变更，无其他变化)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
