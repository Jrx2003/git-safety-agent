#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEMO_DIR="$ROOT_DIR/.gsa_demo_repo"

rm -rf "$DEMO_DIR"
mkdir -p "$DEMO_DIR"
cd "$DEMO_DIR"

git init >/dev/null

echo "print('hello gsa')" > app.py
mkdir -p docs
printf "# 示例项目\n\n这是一个 demo。\n" > README.md

git add README.md app.py

git commit -m "初始化示例" >/dev/null || true

cd "$ROOT_DIR"

echo "=== 场景1：只读状态 ==="
python -m gsa.cli plan --workspace "$DEMO_DIR" --input "看看当前仓库状态"

echo "=== 场景2：危险拦截 ==="
python -m gsa.cli plan --workspace "$DEMO_DIR" --input "请 reset --hard"

echo "=== 场景3：追问（缺少提交信息） ==="
python -m gsa.cli plan --workspace "$DEMO_DIR" --input "提交代码"

echo "=== 场景4：写操作确认（暂存所有改动） ==="
# 制造改动
echo "print('changed')" >> "$DEMO_DIR/app.py"
python -m gsa.cli run --workspace "$DEMO_DIR" --input "暂存所有改动"
# 需要显式 YES 才会真正执行
python -m gsa.cli run --workspace "$DEMO_DIR" --input "暂存所有改动" --yes

echo "=== 场景5：索引搜索与目录总结 ==="
python -m gsa.cli index-build --workspace "$DEMO_DIR"
python -m gsa.cli run --workspace "$DEMO_DIR" --input "总结目录并给整理建议"

echo "全部 demo 执行完成。"
