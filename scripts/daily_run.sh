#!/bin/bash
# 股票初级预测验证系统每日跑批：快照 → 预测 → 到期结算 → git commit 防篡改
set -e
cd "$(dirname "$0")/.."  # 从 scripts/ 回到 validation/
PY=python3
export STOCK_PREDICT_MODEL=deepseek/deepseek-chat
LOG=/tmp/stock_predict_daily_$(date +%Y%m%d_%H%M%S).log
{
  echo "=== $(date '+%F %T') fetch_snapshots ==="
  env -u PYTHONPATH $PY scripts/fetch_snapshots.py
  echo "=== predict_batch ==="
  env -u PYTHONPATH $PY scripts/predict_batch.py
  echo "=== settle ==="
  env -u PYTHONPATH $PY scripts/settle.py
  echo "=== git commit 防篡改时间戳 ==="
  cd ..
  git add validation/logs/ validation/pool/ validation/rules.yaml
  if ! git diff --cached --quiet; then
    git -c user.email=your-email@example.com -c user.name="Your Name" \
      commit -m "daily: $(date +%Y-%m-%d) snapshots+predictions+settle"
  else
    echo "无变更，跳过 commit"
  fi
  echo "=== DONE ==="
} 2>&1 | tee "$LOG"
echo "LOG: $LOG"
