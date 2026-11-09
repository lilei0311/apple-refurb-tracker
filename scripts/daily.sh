#!/bin/bash
# 每日 19:00：抓取 → 渲染 → 提交推送。失败即退出并打印可读原因。
# 环境变量：
#   FORCE=1  忽略"当日已有快照"检查，强制重新抓取一次。
set -euo pipefail
cd "$(/usr/bin/dirname "$0")/.."

TODAY=$(date +%F)
FORCE=${FORCE:-0}

fail() {
  # $1=哪一步  $2=原因摘要  $3=退出码(默认 1)
  echo "FAIL: $1 — $2" >&2
  exit "${3:-1}"
}

# set -e 下未显式守卫的命令失败时，兜底打印位置信息，避免裸 traceback/静默退出
trap 'fail "未捕获错误" "第 ${LINENO} 行命令失败: ${BASH_COMMAND}"' ERR

# push 并校验远端 HEAD == 本地 HEAD；失败按 1s/2s/4s/8s 递增重试，最多 5 次。
# 应对 privoxy 代理 CONNECT 隧道 503 抖动（远端其实已更新、客户端确认阶段报错）。
push_with_retry() {
  local attempt=1 max=5 delay=1 head remote_head
  while :; do
    if /usr/bin/git push origin HEAD; then
      head=$(/usr/bin/git rev-parse HEAD) \
        || fail "校验远端" "git rev-parse HEAD 失败"
      remote_head=$(/usr/bin/git ls-remote origin refs/heads/main 2>&1 | /usr/bin/awk '{print $1}') \
        || fail "校验远端" "git ls-remote 读取远端 HEAD 失败"
      if [ "$head" = "$remote_head" ]; then
        return 0
      fi
      echo "远端校验不一致（本地 ${head} / 远端 ${remote_head:-空}），第 ${attempt} 次，稍后重试" >&2
    else
      echo "git push 失败（第 ${attempt}/${max} 次），${delay}s 后重试" >&2
    fi
    if [ "$attempt" -ge "$max" ]; then
      fail "git push" "重试 ${max} 次后仍失败或远端未同步"
    fi
    sleep "$delay"
    delay=$((delay * 2))
    attempt=$((attempt + 1))
  done
}

SKIP_SCRAPE=0
if [ "$FORCE" != "1" ] && [ -f "data/$TODAY.json" ]; then
  SKIP_SCRAPE=1
  echo "今日（${TODAY}）快照已存在，跳过抓取，仅重渲染并推送"
fi

if [ "$SKIP_SCRAPE" = "0" ]; then
  if ! /usr/bin/pgrep -f "Tabbit Browser.app/Contents/MacOS/Tabbit Browser" >/dev/null 2>&1; then
    echo "Tabbit 未运行，尝试启动…"
    /usr/bin/open -a "Tabbit Browser" || true
    sleep 8
  fi
  /usr/bin/python3 scripts/scrape.py || fail "抓取" "scrape.py 退出码非 0"
fi

/usr/bin/python3 scripts/render.py || fail "渲染" "render.py 退出码非 0"

# 简报落盘：模型回合缺席（如 429 额度耗尽）时，人和脚本都能直接读这份文件。
# 放在"无变化提前 exit 0"分支之前，保证幂等分支（当日快照已存在）也产出简报。
# 简报失败不算致命：打 WARN 到 stderr 后继续提交推送，退出码仍只反映 pipeline 成败。
OUT_DIR="${REFURB_OUT_DIR:-$HOME/.dsh/bot/workspace/pm/refurb/out}"
if report_text=$(/usr/bin/python3 scripts/report.py 2>/dev/null); then
  if ! /bin/mkdir -p "$OUT_DIR"; then
    echo "WARN: 简报生成失败 — 无法创建输出目录 $OUT_DIR" >&2
  else
    {
      echo "# 苹果官翻库存 · 每日简报（${TODAY}）"
      echo "- 生成时间：$(date '+%Y-%m-%d %H:%M:%S')"
      echo
      printf '%s\n' "$report_text"
    } > "$OUT_DIR/latest-report.md" \
      || echo "WARN: 简报生成失败 — 无法写入 $OUT_DIR/latest-report.md" >&2
  fi
else
  echo "WARN: 简报生成失败 — report.py 退出码非 0" >&2
fi

/usr/bin/git add -A || fail "暂存" "git add -A 失败"
if /usr/bin/git diff --cached --quiet; then
  echo "无变化（渲染产物与仓库一致），无需提交推送"
  exit 0
fi

/usr/bin/git -c user.name=lilei0311 -c user.email=lilei0311@users.noreply.github.com \
    commit -m "data: ${TODAY} 官翻库存快照" >/dev/null \
  || fail "提交" "git commit 失败"
push_with_retry
echo "已推送 ${TODAY} 数据（远端校验一致）"
