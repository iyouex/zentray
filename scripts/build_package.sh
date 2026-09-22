#!/usr/bin/env bash
# ============================================================================
# ZenTray 本地构建「用户安装包」（对齐 GitHub Releases 形态）
#
# 用户安装场景（产品约定）:
#   Linux   → .deb      → sudo apt install ./zentray_*.deb
#   Windows → .exe      → 双击安装向导
#   macOS   → .dmg      → 拖入 Applications
#
# 本机为 Ubuntu 时完整支持 linux(.deb)；windows/macos 在本机仅作
# 交叉说明或在对应 OS/CI 上构建。可用 --target 选择环境。
#
# 用法:
#   ./scripts/build_package.sh                       # 默认 linux deb
#   ./scripts/build_package.sh --target linux
#   ./scripts/build_package.sh --target windows
#   ./scripts/build_package.sh --target macos
#   ./scripts/build_package.sh --target all          # 当前 OS 能构建的都做
#   ./scripts/build_package.sh --target linux --clean
#   ./scripts/build_package.sh --target linux --install   # 构建后 apt 安装（需 sudo）
#   ./scripts/build_package.sh -h
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib_common.sh
source "${SCRIPT_DIR}/lib_common.sh"

TARGET="linux"
CLEAN=false
INSTALL_AFTER=false
SKIP_PYINSTALLER=false

usage() {
    cat <<EOF
用法: $0 [选项]

构建 GitHub Release 形态的安装包。

选项:
  --target, -t <env>   目标环境: linux | windows | macos | all
                       默认: linux
  --clean              清理 build/ 后重新 PyInstaller
  --install            (仅 linux) 构建后 sudo apt install 本机 deb
  --skip-binary        跳过 PyInstaller（仅当前端未变化时复用 dist/ZenTray 快速重打包；
                       若 web/dist 已更新会自动强制重建，避免旧 UI 进包）
  -h, --help           显示帮助

产物目录: dist/releases/

示例（Ubuntu 反复测安装）:
  ./scripts/build_package.sh --target linux --clean
  sudo apt install -y ./dist/releases/zentray_*_amd64.deb
  # 测完
  ./scripts/uninstall.sh --purge --yes
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --target|-t)
            TARGET="${2:-}"
            shift
            ;;
        --clean) CLEAN=true ;;
        --install) INSTALL_AFTER=true ;;
        --skip-binary) SKIP_PYINSTALLER=true ;;
        -h|--help) usage; exit 0 ;;
        *) err "未知选项: $1"; usage; exit 1 ;;
    esac
    shift
done

TARGET="$(echo "$TARGET" | tr '[:upper:]' '[:lower:]')"
case "$TARGET" in
    linux|windows|macos|all|win|mac) ;;
    *) err "无效 --target: $TARGET（应为 linux|windows|macos|all）"; exit 1 ;;
esac
[[ "$TARGET" == "win" ]] && TARGET="windows"
[[ "$TARGET" == "mac" ]] && TARGET="macos"

VERSION="$(get_version)"
RELEASES_DIR="${PROJECT_DIR}/dist/releases"
mkdir -p "$RELEASES_DIR"
VENV_PYTHON="${PROJECT_DIR}/venv/bin/python"
DIST_BIN="${PROJECT_DIR}/dist/ZenTray"
HOST_OS="$(uname -s | tr '[:upper:]' '[:lower:]')"

section "构建参数"
echo "  版本:     ${VERSION}"
echo "  目标:     ${TARGET}"
echo "  主机:     ${HOST_OS}"
echo "  清理:     ${CLEAN}"
echo "  产物目录: ${RELEASES_DIR}"

need_venv() {
    if [[ ! -x "$VENV_PYTHON" ]]; then
        err "未找到 venv: $VENV_PYTHON"
        echo "  请先: python3 -m venv venv && venv/bin/pip install -e '.[dev]' pyinstaller"
        exit 1
    fi
}

# ========================================================================
build_frontend() {
    section "构建前端 (web/dist)"
    if [[ ! -d "${PROJECT_DIR}/web" ]]; then
        warn "无 web/ 目录，跳过前端构建"
        return
    fi
    if ! command -v npm >/dev/null 2>&1; then
        err "需要 npm 以构建 Vue 前端"
        exit 1
    fi
    (
        cd "${PROJECT_DIR}/web"
        if [[ ! -d node_modules ]]; then
            warn "安装前端依赖（npm install）..."
            npm install
        fi
        npm run build
    ) || {
        err "前端构建失败（npm run build），中止打包。"
        err "请检查 web/ 下源码报错；若 node_modules 过期可先删除后重试。"
        exit 1
    }
    if [[ ! -d "${PROJECT_DIR}/web/dist" ]] || [[ ! -f "${PROJECT_DIR}/web/dist/index.html" ]]; then
        err "前端构建失败：未生成 web/dist/index.html"
        exit 1
    fi
    info "前端产物: ${PROJECT_DIR}/web/dist"
}

# ========================================================================
# 判断现有 dist/ZenTray 是否内嵌了过期前端。
# ZenTray 为 PyInstaller onefile 自包含产物，web/dist 在打包瞬间被固化进二进制；
# 只要 web/dist 中任一文件比二进制新，就说明二进制仍是旧 UI，必须重建。
# 返回 0 = 需重建；1 = 二进制已包含最新前端。
frontend_is_newer_than_binary() {
    [[ -f "$DIST_BIN" ]] || return 0
    [[ -d "${PROJECT_DIR}/web/dist" ]] || return 0
    find "${PROJECT_DIR}/web/dist" -type f -newer "$DIST_BIN" -print -quit | grep -q .
}

# ========================================================================
build_pyinstaller() {
    need_venv
    # 始终先构建前端，保证 web/dist 打入 PyInstaller datas
    build_frontend

    section "PyInstaller 构建主程序"
    if $CLEAN; then
        rm -rf "${PROJECT_DIR}/build" "${PROJECT_DIR}/dist/ZenTray"
        warn "已清理 build/ 与 dist/ZenTray"
    fi
    # --skip-binary 但现有二进制已过期（前端刚重新构建）→ 强制重建，杜绝旧 UI 进包
    if $SKIP_PYINSTALLER && [[ -f "$DIST_BIN" ]] && frontend_is_newer_than_binary; then
        warn "--skip-binary 但 web/dist 已更新，现有二进制仍是旧 UI，强制重新构建主程序"
        SKIP_PYINSTALLER=false
    fi
    if $SKIP_PYINSTALLER && [[ -f "$DIST_BIN" ]]; then
        warn "跳过 PyInstaller，使用已有 $DIST_BIN（前端未变化，二进制已含最新 UI）"
        return
    fi
    if ! "$VENV_PYTHON" -c "import PyInstaller" 2>/dev/null; then
        warn "安装 pyinstaller..."
        "$VENV_PYTHON" -m pip install -q pyinstaller
    fi
    # 语法检查
    local errors=0
    while IFS= read -r -d '' f; do
        if ! "$VENV_PYTHON" -m py_compile "$f" 2>/dev/null; then
            err "语法错误: $f"
            errors=$((errors + 1))
        fi
    done < <(find "${PROJECT_DIR}/zentray" -name "*.py" -print0)
    if [[ $errors -gt 0 ]]; then
        exit 1
    fi
    info "语法检查通过"
    (
        cd "$PROJECT_DIR"
        "$VENV_PYTHON" -m PyInstaller zentray.spec
    )
    if [[ ! -f "$DIST_BIN" ]]; then
        err "未生成 $DIST_BIN"
        exit 1
    fi
    info "主程序: $DIST_BIN ($(du -h "$DIST_BIN" | cut -f1))"
}

# ========================================================================
build_linux_deb() {
    section "打包 Linux .deb"
    if [[ ! -f "$DIST_BIN" ]]; then
        err "缺少主程序，请先成功执行 PyInstaller"
        exit 1
    fi
    if ! command -v dpkg-deb >/dev/null 2>&1; then
        err "需要 dpkg-deb（Ubuntu 自带）"
        exit 1
    fi

    local stage arch deb_name branch safe_branch pack_order
    arch="$(dpkg --print-architecture 2>/dev/null || echo amd64)"
    stage="${PROJECT_DIR}/build/deb_stage"

    # 命名规范：
    #   main/master → zentray_<VERSION>_<arch>.deb
    #   功能分支   → zentray_<VERSION>_feature-<branch>-<N>_<arch>.deb
    branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
    if [[ "$branch" != "main" && "$branch" != "master" ]]; then
        # feature/optimization → optimization；其它非 feature 前缀保留清洗后全名
        safe_branch="${branch//\//-}"
        safe_branch="${safe_branch//[^a-zA-Z0-9-]/-}"
        safe_branch="$(echo "$safe_branch" | sed -E 's/-+/-/g; s/^-|-$//g')"
        if [[ "$safe_branch" == feature-* ]]; then
            safe_branch="${safe_branch#feature-}"
        fi
        pack_order="$(cat "${RELEASES_DIR}/.latest_branch_packings" 2>/dev/null || echo 0)"
        # 仅统计当前分支的次序：用独立文件避免跨分支串号
        local order_file="${RELEASES_DIR}/.pack_order_${safe_branch}"
        if [[ -f "$order_file" ]]; then
            pack_order="$(cat "$order_file" 2>/dev/null || echo 0)"
        else
            pack_order=0
        fi
        pack_order=$((pack_order + 1))
        deb_name="${PKG_NAME}_${VERSION}_feature-${safe_branch}-${pack_order}_${arch}.deb"
        echo "$pack_order" > "$order_file"
        # 兼容旧计数器
        echo "$pack_order" > "${RELEASES_DIR}/.latest_branch_packings"
    else
        deb_name="${PKG_NAME}_${VERSION}_${arch}.deb"
    fi
    info "包名: ${deb_name}"
    rm -rf "$stage"
    mkdir -p \
        "${stage}/DEBIAN" \
        "${stage}/opt/${PKG_NAME}" \
        "${stage}/usr/bin" \
        "${stage}/usr/share/applications" \
        "${stage}/usr/share/icons/hicolor/256x256/apps" \
        "${stage}/usr/share/doc/${PKG_NAME}"

    # 主二进制
    cp -a "$DIST_BIN" "${stage}/opt/${PKG_NAME}/ZenTray"
    chmod 755 "${stage}/opt/${PKG_NAME}/ZenTray"

    # 防线：二进制必须已包含最新前端，否则静默产出「旧 UI 的 deb」
    if frontend_is_newer_than_binary; then
        err "中止打包：$DIST_BIN 内嵌的 web/dist 已过期（前端构建晚于二进制）"
        err "请重新构建主程序后再打 deb：./scripts/build_package.sh --target linux"
        exit 1
    fi
    info "校验: $DIST_BIN 已包含最新前端（web/dist 无更新文件）"

    # 图标
    local icon_src="${PROJECT_DIR}/resources/icons/app_icon.png"
    if [[ -f "$icon_src" ]]; then
        cp -a "$icon_src" "${stage}/usr/share/icons/hicolor/256x256/apps/${PKG_NAME}.png"
        mkdir -p "${stage}/opt/${PKG_NAME}/resources/icons"
        # 同步 pie 图标供运行时拷贝到用户数据目录
        if [[ -d "${PROJECT_DIR}/resources/icons" ]]; then
            cp -a "${PROJECT_DIR}/resources/icons/." "${stage}/opt/${PKG_NAME}/resources/icons/" || true
        fi
    fi

    # 启动包装：已在运行则直连单实例 socket 激活（免 182MB onefile 解压+导入，
    # 实测任务栏再点击 3.2s → ~0.2s）；未运行/激活失败则冷启动完整应用。
    cat > "${stage}/usr/bin/${PKG_NAME}" <<'WRAP'
#!/bin/sh
if command -v /usr/bin/python3 >/dev/null 2>&1; then
    if /usr/bin/python3 - "$@" <<'PY'
import os, socket, sys


def _activate():
    # 与 SingleInstanceGuard（QLocalServer "ZenTray_SingleInstance"）同名；
    # Linux 下 Qt 把 socket 建在 $XDG_RUNTIME_DIR 或 /tmp
    for d in (os.environ.get("XDG_RUNTIME_DIR") or "", "/tmp"):
        try:
            s = socket.socket(socket.AF_UNIX)
            s.settimeout(2)
            s.connect(os.path.join(d, "ZenTray_SingleInstance"))
            s.sendall(b"activate")
            s.close()
            return True
        except OSError:
            continue
    return False


if not _activate():
    os.execv("/opt/zentray/ZenTray", ["/opt/zentray/ZenTray"] + sys.argv[1:])
PY
    then
        exit 0
    fi
fi
exec /opt/zentray/ZenTray "$@"
WRAP
    chmod 755 "${stage}/usr/bin/${PKG_NAME}"

    # desktop
    sed "s|__VERSION__|${VERSION}|g" \
        "${PROJECT_DIR}/packaging/debian/zentray.desktop.in" \
        > "${stage}/usr/share/applications/${PKG_NAME}.desktop"
    # control
    sed "s|__VERSION__|${VERSION}|g" \
        "${PROJECT_DIR}/packaging/debian/control.in" \
        > "${stage}/DEBIAN/control"
    # 若 architecture 非 amd64 则替换
    if [[ "$arch" != "amd64" ]]; then
        sed -i "s/^Architecture: .*/Architecture: ${arch}/" "${stage}/DEBIAN/control"
    fi

    # 权限
    chmod 755 "${stage}/DEBIAN"
    # 文档
    if [[ -f "${PROJECT_DIR}/LICENSE" ]]; then
        cp -a "${PROJECT_DIR}/LICENSE" "${stage}/usr/share/doc/${PKG_NAME}/copyright"
    fi
    echo "ZenTray ${VERSION}" > "${stage}/usr/share/doc/${PKG_NAME}/changelog"
    gzip -9 -f "${stage}/usr/share/doc/${PKG_NAME}/changelog" 2>/dev/null || true

    # postinst: 更新桌面数据库
    cat > "${stage}/DEBIAN/postinst" <<'POST'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q /usr/share/icons/hicolor 2>/dev/null || true
fi
exit 0
POST
    chmod 755 "${stage}/DEBIAN/postinst"

    cat > "${stage}/DEBIAN/postrm" <<'POSTRM'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
exit 0
POSTRM
    chmod 755 "${stage}/DEBIAN/postrm"

    local out_deb="${RELEASES_DIR}/${deb_name}"
    dpkg-deb --root-owner-group --build "$stage" "$out_deb"
    info "deb: $out_deb ($(du -h "$out_deb" | cut -f1))"

    # 校验
    dpkg-deb -I "$out_deb" | head -20 || true
    echo "$out_deb" > "${RELEASES_DIR}/.latest_linux_deb"
}

install_linux_deb() {
    section "安装 deb 到本机"
    local deb
    if [[ -f "${RELEASES_DIR}/.latest_linux_deb" ]]; then
        deb="$(cat "${RELEASES_DIR}/.latest_linux_deb")"
    else
        deb="$(ls -1t "${RELEASES_DIR}/${PKG_NAME}_"*_*.deb 2>/dev/null | head -1 || true)"
    fi
    if [[ -z "${deb:-}" || ! -f "$deb" ]]; then
        err "未找到 deb 产物"
        exit 1
    fi
    warn "sudo apt install -y $deb"
    if [[ "$(id -u)" -eq 0 ]]; then
        apt-get install -y "$deb"
    else
        sudo apt-get install -y "$deb"
    fi
    info "安装完成。启动: zentray   或从应用菜单打开 ZenTray"
}

# ========================================================================
build_windows_exe() {
    section "Windows .exe 安装包"
    if [[ "$HOST_OS" != "mingw"* && "$HOST_OS" != "msys"* && "$HOST_OS" != "cygwin"* && "$HOST_OS" != "windows"* ]]; then
        # 检测 Windows 环境
        if [[ -z "${WINDIR:-}" && "$(uname -o 2>/dev/null || true)" != "Msys" ]]; then
            err "当前主机不是 Windows，无法在本机生成正式 .exe 安装包。"
            echo ""
            echo "  产品约定: 用户从 GitHub Releases 下载 .exe 双击安装。"
            echo "  请在 Windows 机器或 CI runner 上执行:"
            echo "    python -m venv venv && venv\\Scripts\\pip install -e \".[dev]\" pyinstaller"
            echo "    venv\\Scripts\\pyinstaller zentray.spec"
            echo "    venv\\Scripts\\pyinstaller installer.spec"
            echo "    将 dist\\ZenTrayInstaller.exe 上传到 Releases"
            echo ""
            echo "  本机已生成的 Linux 二进制可参考: dist/ZenTray"
            return 1
        fi
    fi
    need_venv
    build_pyinstaller
    (
        cd "$PROJECT_DIR"
        "$VENV_PYTHON" -m PyInstaller installer.spec
    )
    local exe="${PROJECT_DIR}/dist/ZenTrayInstaller.exe"
    if [[ -f "$exe" ]]; then
        cp -a "$exe" "${RELEASES_DIR}/ZenTrayInstaller-${VERSION}-x64.exe"
        info "exe: ${RELEASES_DIR}/ZenTrayInstaller-${VERSION}-x64.exe"
    else
        err "未找到 ZenTrayInstaller.exe"
        return 1
    fi
}

build_macos_dmg() {
    section "macOS .dmg 安装包"
    if [[ "$HOST_OS" != "darwin" ]]; then
        err "当前主机不是 macOS，无法在本机生成 .dmg。"
        echo ""
        echo "  产品约定: 用户从 GitHub Releases 下载 .dmg，拖入 Applications。"
        echo "  请在 macOS 上执行 PyInstaller + create-dmg / hdiutil，或由 CI 构建。"
        echo "  建议产物名: ZenTray-${VERSION}-arm64.dmg / ZenTray-${VERSION}-x86_64.dmg"
        return 1
    fi
    need_venv
    build_pyinstaller
    # 简易 dmg：将 app/二进制放入挂载卷
    local dmg_stage="${PROJECT_DIR}/build/dmg_stage"
    local dmg_out="${RELEASES_DIR}/ZenTray-${VERSION}.dmg"
    rm -rf "$dmg_stage"
    mkdir -p "$dmg_stage"
    cp -a "$DIST_BIN" "${dmg_stage}/ZenTray"
    ln -sf /Applications "${dmg_stage}/Applications"
    hdiutil create -volname "ZenTray" -srcfolder "$dmg_stage" -ov -format UDZO "$dmg_out"
    info "dmg: $dmg_out"
}

# ========================================================================
# 调度
# ========================================================================
FAILED=0

run_linux() {
    build_pyinstaller
    build_linux_deb
    if $INSTALL_AFTER; then
        install_linux_deb
    fi
}

case "$TARGET" in
    linux)
        run_linux
        ;;
    windows)
        build_windows_exe || FAILED=1
        ;;
    macos)
        build_macos_dmg || FAILED=1
        ;;
    all)
        if [[ "$HOST_OS" == "linux" ]]; then
            run_linux
            build_windows_exe || warn "跳过 windows（需 Windows 主机）"
            build_macos_dmg || warn "跳过 macos（需 macOS 主机）"
        elif [[ "$HOST_OS" == "darwin" ]]; then
            build_macos_dmg || FAILED=1
            build_windows_exe || warn "跳过 windows"
        else
            build_windows_exe || FAILED=1
        fi
        ;;
esac

section "构建汇总"
ls -lh "${RELEASES_DIR}" 2>/dev/null | sed 's/^/  /' || true
echo ""
if [[ "$TARGET" == "linux" || "$TARGET" == "all" ]]; then
    echo -e "  ${BOLD}Linux 安装测试:${NC}"
    echo -e "    ${CYAN}sudo apt install -y ./dist/releases/${PKG_NAME}_${VERSION}_*.deb${NC}"
    echo -e "    ${CYAN}zentray${NC}   # 启动"
    echo -e "    ${CYAN}./scripts/uninstall.sh --purge --yes${NC}"
fi
echo ""

exit "$FAILED"
