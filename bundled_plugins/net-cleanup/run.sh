#!/usr/bin/env bash
# ZenTray 示例插件：网络清理（Linux 桌面）
# 协议：stdout 输出 PROGRESS / LOG / RESULT；退出码 0=成功
set -u
# 不用 set -e：单步失败记日志后继续，最后汇总

TOTAL=5
STEP=0
FAIL=0

progress() {
  STEP=$((STEP + 1))
  local msg="$1"
  echo "PROGRESS ${STEP}/${TOTAL} ${msg}"
}

log() {
  echo "LOG $*"
}

run_step() {
  # $1=说明  rest=命令
  local title="$1"
  shift
  progress "$title"
  if "$@" >>/tmp/zentray-net-cleanup.$$.log 2>&1; then
    log "OK: $title"
    return 0
  else
    local code=$?
    log "SKIP/FAIL ($code): $title — 详见本机权限或是否安装对应工具"
    FAIL=$((FAIL + 1))
    return 0
  fi
}

cleanup_log() {
  rm -f /tmp/zentray-net-cleanup.$$.log 2>/dev/null || true
}
trap cleanup_log EXIT

log "开始网络清理（示例插件 net-cleanup）"
log "用户=$(id -un) host=$(hostname 2>/dev/null || echo unknown)"

# 1) systemd-resolved / resolvectl
if command -v resolvectl >/dev/null 2>&1; then
  run_step "刷新 DNS (resolvectl flush-caches)" resolvectl flush-caches
elif command -v systemd-resolve >/dev/null 2>&1; then
  run_step "刷新 DNS (systemd-resolve --flush-caches)" systemd-resolve --flush-caches
else
  progress "刷新 DNS"
  log "未找到 resolvectl/systemd-resolve，跳过 DNS 刷新"
fi

# 2) nscd / nsncd
if command -v nscd >/dev/null 2>&1; then
  run_step "刷新 nscd 缓存" nscd -i hosts
elif systemctl is-active --quiet nscd 2>/dev/null; then
  run_step "重载 nscd" systemctl reload nscd
else
  progress "nscd"
  log "未检测到 nscd，跳过"
fi

# 3) 路由缓存（部分环境需 root，失败则记 SKIP）
if command -v ip >/dev/null 2>&1; then
  run_step "刷新路由缓存 (ip route flush cache)" ip route flush cache
else
  progress "路由缓存"
  log "未找到 ip 命令，跳过"
fi

# 4) 打印代理相关环境（只读，不修改）
progress "检查代理环境变量"
{
  log "http_proxy=${http_proxy:-<unset>}"
  log "https_proxy=${https_proxy:-<unset>}"
  log "HTTP_PROXY=${HTTP_PROXY:-<unset>}"
  log "HTTPS_PROXY=${HTTPS_PROXY:-<unset>}"
  log "ALL_PROXY=${ALL_PROXY:-<unset>}"
  log "no_proxy=${no_proxy:-<unset>}"
} 

# 5) 提示如何扩展（公司 VPN / Clash 等）
progress "完成"
log "本示例不自动断开 VPN/Clash；请按需在自定义插件中调用你的客户端 CLI。"
log "扩展：复制本目录，在 run.sh 中增加你的脚本步骤即可。"

if [[ "$FAIL" -gt 0 ]]; then
  echo "RESULT fail 有 ${FAIL} 步失败或跳过（常见原因：无 root / 工具未装）"
  # 部分步骤失败仍 exit 0，避免「示例清理」因权限在托盘显示为硬失败；
  # 若你希望严格失败，改为 exit 1。
  exit 0
fi

echo "RESULT ok"
exit 0
