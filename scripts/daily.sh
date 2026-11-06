#!/bin/bash
# 每日 19:00：抓取 → 渲染 → 提交推送。失败即退出并打印原因。
set -euo pipefail
cd "$(dirname "$0")/.."

TODAY=$(date +%F)
if [ -f "data/$TODAY.json" ]; then
  echo "今日（${TODAY}）数据已存在，跳过抓取（幂等）"
  exit 0
fi

if ! pgrep -f "Tabbit Browser.app/Contents/MacOS/Tabbit Browser" >/dev/null 2>&1; then
  echo "Tabbit 未运行，尝试启动…"
  open -a "Tabbit Browser" || true
  sleep 8
fi

python3 scripts/scrape.py
python3 scripts/render.py

git add -A
if git diff --cached --quiet; then
  echo "无变化，跳过提交"
  exit 0
fi

git -c user.name=lilei0311 -c user.email=lilei0311@users.noreply.github.com \
    commit -m "data: $(date +%F) 官翻库存快照" >/dev/null
git push origin HEAD
echo "已推送 $(date +%F) 数据"
