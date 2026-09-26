#!/usr/bin/env bash
# ZenTray 脚本公共库（被其他 scripts 源入）
# shellcheck disable=SC2034

set -euo pipefail

# ---- 颜色 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

APP_NAME="ZenTray"
PKG_NAME="zentray"   # deb 包名（小写）

# 用户级安装 / 数据路径（与 installer + config 对齐）
USER_INSTALL_DIR="${HOME}/.local/bin/${APP_NAME}"
USER_DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/${APP_NAME}"
USER_DATA_DIR_LEGACY="${XDG_DATA_HOME:-$HOME/.local/share}/zentray"
USER_AUTOSTART="${HOME}/.config/autostart/${APP_NAME}.desktop"
USER_DESKTOP_FILE=""
# 桌面目录（兼容中文「桌面」）
for d in "${HOME}/Desktop" "${HOME}/桌面"; do
    if [[ -d "$d" ]]; then
        USER_DESKTOP_FILE="${d}/${APP_NAME}.desktop"
        break
    fi
done
USER_APPS_DESKTOP="${HOME}/.local/share/applications/${APP_NAME}.desktop"
USER_APPS_DESKTOP_LC="${HOME}/.local/share/applications/${PKG_NAME}.desktop"

# deb 系统路径（packaging 约定）
DEB_OPT_DIR="/opt/${PKG_NAME}"
DEB_BIN_LINK="/usr/bin/${PKG_NAME}"
DEB_DESKTOP="/usr/share/applications/${PKG_NAME}.desktop"
DEB_ICON_DIR="/usr/share/icons/hicolor/256x256/apps"

section() {
    echo ""
    echo -e "${BOLD}${CYAN}━━━ $1 ━━━${NC}"
}

info()  { echo -e "  ${GREEN}✓${NC} $*"; }
warn()  { echo -e "  ${YELLOW}→${NC} $*"; }
err()   { echo -e "  ${RED}✗${NC} $*" >&2; }

get_version() {
    local py="${PROJECT_DIR}/venv/bin/python"
    if [[ -x "$py" ]]; then
        "$py" -c "from zentray.config import VERSION; print(VERSION)" 2>/dev/null && return
    fi
    if command -v python3 >/dev/null 2>&1; then
        PYTHONPATH="${PROJECT_DIR}${PYTHONPATH:+:$PYTHONPATH}" \
            python3 -c "from zentray.config import VERSION; print(VERSION)" 2>/dev/null && return
    fi
    echo "0.0.0"
}

is_deb_installed() {
    dpkg -s "$PKG_NAME" &>/dev/null
}

kill_app_processes() {
    # 结束主程序 / 安装器 / 托盘桥：TERM → 等待 → KILL 兜底
    local pid i
    local -a targets=()
    while IFS= read -r pid; do
        [[ -z "$pid" ]] && continue
        targets+=("$pid")
    done < <(
        { pgrep -f '[Zz]enTray'; pgrep -f 'linux_tray_bridge'; pgrep -f 'zentray/main.py'; } 2>/dev/null |
            sort -u || true
    )

    # 排除脚本自身进程链（$$ 及祖先），防止外层命令行含 ZenTray 字样时自杀
    # 链格式 "|pid1|pid2|"，两端定界做整词匹配
    local self_chain p
    self_chain="|$$|"
    p="$$"
    while [[ -n "$p" && "$p" != "1" ]]; do
        # || true：祖先恰好消失时 ps 非零，防 set -e 中断
        p="$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ' || true)"
        [[ -n "$p" && "$p" != "1" ]] && self_chain="${self_chain}${p}|"
    done
    local -a filtered=()
    for pid in "${targets[@]}"; do
        [[ "$self_chain" == *"|${pid}|"* ]] && continue
        filtered+=("$pid")
    done
    targets=("${filtered[@]}")

    if [[ ${#targets[@]} -eq 0 ]]; then
        info "无相关进程在运行"
        return 0
    fi

    # 1) TERM
    for pid in "${targets[@]}"; do
        warn "TERM -> ${pid} $(ps -o args= -p "$pid" 2>/dev/null | cut -c1-80)"
        kill -TERM "$pid" 2>/dev/null || true
    done

    # 2) 等待退出（≤5s）
    for i in 1 2 3 4 5; do
        local -a alive=()
        for pid in "${targets[@]}"; do
            kill -0 "$pid" 2>/dev/null && alive+=("$pid")
        done
        if [[ ${#alive[@]} -eq 0 ]]; then
            info "进程已全部退出"
            return 0
        fi
        targets=("${alive[@]}")
        sleep 1
    done

    # 3) KILL 兜底
    for pid in "${targets[@]}"; do
        warn "KILL -> ${pid}（TERM 未退出，强杀）"
        kill -KILL "$pid" 2>/dev/null || true
    done
    sleep 0.5
    local -a failed=()
    for pid in "${targets[@]}"; do
        kill -0 "$pid" 2>/dev/null && failed+=("$pid")
    done
    if [[ ${#failed[@]} -gt 0 ]]; then
        err "以下进程无法结束: ${failed[*]}"
        return 1
    fi
    info "进程已全部退出"
}
