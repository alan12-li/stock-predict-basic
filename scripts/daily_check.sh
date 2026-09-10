#!/bin/bash
# 股票初级预测 — 每日检查+补跑（cron 每 30 分钟运行）
# 逻辑：如果今天没跑过且当前时间 >= 15:30（或已收盘），则执行 daily_run

cd "$(dirname "$0")/.."  # validation/
TODAY=$(date +%Y-%m-%d)
LOGFILE="/tmp/stock_predict_daily_check_$(date +%Y%m%d).log"
DONE_FLAG="/tmp/stock_predict_daily_done_${TODAY}"

# 已跑过则退出
if [ -f "$DONE_FLAG" ]; then
    exit 0
fi

# 检查是否交易日（周一到周五）
WEEKDAY=$(date +%u)  # 1=Mon, 7=Sun
if [ "$WEEKDAY" -gt 5 ]; then
    echo "$(date '+%F %T') 周末，跳过" >> "$LOGFILE"
    exit 0
fi

# 检查时间：15:30 后（A股收盘）
HOUR=$(date +%H)
MIN=$(date +%M)
CURRENT=$((10#$HOUR * 60 + 10#$MIN))
TARGET=$((15 * 60 + 30))  # 15:30

if [ "$CURRENT" -lt "$TARGET" ]; then
    echo "$(date '+%F %T') 未到 15:30，跳过" >> "$LOGFILE"
    exit 0
fi

# 执行 daily_run
echo "$(date '+%F %T') 开始执行 daily_run" >> "$LOGFILE"
bash scripts/daily_run.sh >> "$LOGFILE" 2>&1

# 标记完成
if [ $? -eq 0 ]; then
    touch "$DONE_FLAG"
    echo "$(date '+%F %T') daily_run 完成" >> "$LOGFILE"
else
    echo "$(date '+%F %T') daily_run 失败" >> "$LOGFILE"
fi
