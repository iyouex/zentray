#!/bin/sh
# 任务报告（示例）：任务完成触发，回显注入的任务上下文，并输出写回摘要。
# 协议见 docs/plugins/PLUGIN_SPEC.md（api_version: 2）
set -eu

echo "PROGRESS 1/2 读取任务上下文"
echo "LOG 任务: ${ZENTRAY_TASK_TITLE:-（手动运行，无任务上下文）}"
if [ -n "${ZENTRAY_TASK_CATEGORY:-}" ]; then
  echo "LOG 分类: ${ZENTRAY_TASK_CATEGORY}"
fi
if [ -n "${ZENTRAY_TASK_PRIORITY:-}" ]; then
  echo "LOG 优先级: ${ZENTRAY_TASK_PRIORITY}"
fi
if [ -n "${ZENTRAY_TASK_DEADLINE:-}" ]; then
  echo "LOG 截止: ${ZENTRAY_TASK_DEADLINE}"
fi
if [ -n "${ZENTRAY_TASK_DETAILS:-}" ]; then
  echo "LOG 备注: ${ZENTRAY_TASK_DETAILS}"
fi
echo "LOG 触发方式: ${ZENTRAY_TRIGGER:-manual}"

echo "PROGRESS 2/2 生成摘要"
echo "RESULT ok 已生成任务报告：${ZENTRAY_TASK_TITLE:-手动运行}"
exit 0
