#!/usr/bin/env bash
# ============================================================================
# ZenTray 卸载脚本（面向 Ubuntu 手动测试 / 模拟用户卸载）
#
# 覆盖：
#   1) apt/dpkg 安装的 .deb（系统包 zentray）
#   2) 旧版安装器写入的用户目录 ~/.local/bin/ZenTray
#   3) 桌面快捷方式、开机自启、.desktop 入口
#
# 默认不删除用户数据（任务/设置）。若要一并清空配置，加 --purge 或运行 clean_config.sh
#
# 用法:
#   ./scripts/uninstall.sh              # 卸载应用，保留配置
#   ./scripts/uninstall.sh --purge      # 卸载 + 清理配置/缓存
#   ./scripts/uninstall.sh --yes        # 跳过确认
#   ./scripts/uninstall.sh -h
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_common.sh
source "${SCRIPT_DIR}/lib_common.sh"

PURGE=false
YES=false

usage() {
    cat <<EOF
用法: $0 [选项]

卸载 ZenTray 应用（deb 包 + 本地安装残留 + 快捷方式）。

选项:
  --purge     同时删除用户数据目录（等价再跑 clean_config.sh）
  --yes, -y   不询问确认
  -h, --help  显示帮助

典型测试流程:
  ./scripts/build_package.sh
  sudo apt install -y ./dist/releases/zentray_*_amd64.deb
  # ... 手动测功能 ...
  ./scripts/uninstall.sh --yes
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --purge) PURGE=true ;;
        --yes|-y) YES=true ;;
        -h|--help) usage; exit 0 ;;
        *) err "未知选项: $1"; usage; exit 1 ;;
    esac
    shift
done

section "ZenTray 卸载"
echo "  包名:       ${PKG_NAME}"
echo "  用户安装:   ${USER_INSTALL_DIR}"
echo "  用户数据:   ${USER_DATA_DIR}"
echo "  清除配置:   ${PURGE}"

if ! $YES; then
    echo ""
    read -r -p "确认卸载? [y/N] " ans
    case "$ans" in
        y|Y|yes|YES) ;;
        *) echo "已取消"; exit 0 ;;
    esac
fi

# ------------------------------------------------------------------------
section "1. 结束进程"
# ------------------------------------------------------------------------
kill_app_processes
info "已尝试结束相关进程"

# ------------------------------------------------------------------------
section "2. 卸载 deb 系统包（若已安装）"
# ------------------------------------------------------------------------
if command -v dpkg >/dev/null 2>&1 && is_deb_installed; then
    warn "检测到 dpkg 包 ${PKG_NAME}，执行 apt/dpkg 移除..."
    if [[ "$(id -u)" -eq 0 ]]; then
        apt-get remove -y "$PKG_NAME" || dpkg -r "$PKG_NAME" || true
        if $PURGE; then
            apt-get purge -y "$PKG_NAME" 2>/dev/null || dpkg -P "$PKG_NAME" 2>/dev/null || true
        fi
    else
        if command -v sudo >/dev/null 2>&1; then
            sudo apt-get remove -y "$PKG_NAME" || sudo dpkg -r "$PKG_NAME" || true
            if $PURGE; then
                sudo apt-get purge -y "$PKG_NAME" 2>/dev/null || sudo dpkg -P "$PKG_NAME" 2>/dev/null || true
            fi
        else
            err "需要 root/sudo 才能卸载系统 deb，请手动: sudo apt remove ${PKG_NAME}"
        fi
    fi
    info "deb 包处理完成"
else
    warn "未检测到 dpkg 包 ${PKG_NAME}，跳过 apt 卸载"
fi

# ------------------------------------------------------------------------
section "3. 删除用户级安装目录（安装器 / 手动拷贝）"
# ------------------------------------------------------------------------
if [[ -e "$USER_INSTALL_DIR" ]]; then
    rm -rf "$USER_INSTALL_DIR"
    info "已删除 ${USER_INSTALL_DIR}"
else
    warn "不存在 ${USER_INSTALL_DIR}"
fi

# 旧路径兼容
for p in \
    "${HOME}/.local/share/applications/ZenTray.desktop" \
    "${HOME}/.local/bin/zentray" \
    "/opt/ZenTray" \
    ; do
    if [[ -e "$p" ]]; then
        if [[ -w "$(dirname "$p")" ]] || [[ -w "$p" ]]; then
            rm -rf "$p" 2>/dev/null && info "已删除 $p" || warn "无法删除 $p（权限）"
        else
            if command -v sudo >/dev/null 2>&1; then
                sudo rm -rf "$p" && info "已删除 $p (sudo)" || true
            fi
        fi
    fi
done

# ------------------------------------------------------------------------
section "4. 桌面快捷方式 / 应用菜单 / 开机自启"
# ------------------------------------------------------------------------
for f in \
    "$USER_AUTOSTART" \
    "$USER_DESKTOP_FILE" \
    "$USER_APPS_DESKTOP" \
    "$USER_APPS_DESKTOP_LC" \
    "${HOME}/Desktop/${APP_NAME}.desktop" \
    "${HOME}/桌面/${APP_NAME}.desktop" \
    ; do
    if [[ -n "$f" && -e "$f" ]]; then
        rm -f "$f"
        info "已删除 $f"
    fi
done

# ------------------------------------------------------------------------
section "5. 用户配置"
# ------------------------------------------------------------------------
if $PURGE; then
    "${SCRIPT_DIR}/clean_config.sh" --yes
else
    warn "保留用户数据: ${USER_DATA_DIR}"
    warn "如需清理: ./scripts/clean_config.sh  或  $0 --purge"
fi

section "卸载完成"
echo ""
echo -e "  可重新安装:"
echo -e "    ${CYAN}sudo apt install -y ./dist/releases/${PKG_NAME}_*_amd64.deb${NC}"
echo ""
