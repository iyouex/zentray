#!/usr/bin/env bash
# 参数演示：argv = entry + args + [message, times]（manifest.params 声明顺序）
set -euo pipefail
msg="${1:-你好}"
times="${2:-3}"
echo "PROGRESS 1/2 收到参数"
# 演示插件数据目录（ZENTRAY_PLUGIN_DATA_DIR，zip 重装不丢；旧环境无此变量则跳过）
data_dir="${ZENTRAY_PLUGIN_DATA_DIR:-}"
if [ -n "$data_dir" ]; then
  echo "$(date '+%F %T') message=${msg} times=${times}" >> "$data_dir/history.log" || true
fi
echo "PROGRESS 2/2 完成"
echo "RESULT ok 已记录「${msg}」（times=${times}）"
