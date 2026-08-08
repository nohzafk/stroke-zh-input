#!/bin/sh
# =============================================================================
# stroke-zh 双向同步脚本 — 强制 iSH 工作区 与 Mac 项目目录完全一致
#
# 用法:
#   sh scripts/sync.sh          # push: iSH → Mac (默认; 开发在 iSH, 推到 Mac)
#   sh scripts/sync.sh pull     # pull: Mac → iSH (拉 Mac 独有文件)
#   sh scripts/sync.sh check    # 只对比, 不传输 (列出两边差异)
#
# 规则:
#   - --delete: 目标端多余文件一律删除 (删除 stale 产物/旧代码)
#   - 排除: .git (Mac 仓库保留) / .DS_Store / ._* (AppleDouble 垃圾)
#   - 排除 build/: 构建中间产物 (git 忽略, build.py 可随时重建; 且 Mac 无此目录,
#     pull 时会误删 iSH 的 build/)
#   - 权威源: iSH (/var/minis/shared/rime-stroke-zh) — 代码/产物以 iSH 为准
#   - Mac 项目: randall@192.168.0.243:~/projects/stroke-zh-input
# =============================================================================
set -e

MAC_HOST="randall@192.168.0.243"
MAC_DIR="/Users/randall/projects/stroke-zh-input"
LOCAL_DIR="/var/minis/shared/rime-stroke-zh"

EXCLUDES="--exclude=.git --exclude=.DS_Store --exclude=._* --exclude=*.pyc --exclude=build/"

# 校验 iSH 有 rsync (Alpine 默认无, 需 apk add rsync)
if ! command -v rsync >/dev/null 2>&1; then
  echo "[sync] iSH 缺少 rsync, 安装中..." >&2
  apk add --no-cache rsync >/dev/null 2>&1 || { echo "[sync] rsync 安装失败"; exit 1; }
fi

case "${1:-push}" in
  push)
    echo "[sync] push: iSH → Mac (--delete 强制一致)"
    rsync -av --delete $EXCLUDES "$LOCAL_DIR/" "$MAC_HOST:$MAC_DIR/"
    ;;
  pull)
    echo "[sync] pull: Mac → iSH (--delete 强制一致)"
    rsync -av --delete $EXCLUDES "$MAC_HOST:$MAC_DIR/" "$LOCAL_DIR/"
    ;;
  check)
    echo "[sync] check: 两边差异对比 (iSH 为准)"
    rsync -avn --delete $EXCLUDES "$LOCAL_DIR/" "$MAC_HOST:$MAC_DIR/"
    echo "---"
    rsync -avn --delete $EXCLUDES "$MAC_HOST:$MAC_DIR/" "$LOCAL_DIR/"
    ;;
  *)
    echo "用法: sh scripts/sync.sh [push|pull|check]" >&2
    exit 1
    ;;
esac

echo "[sync] 完成"
