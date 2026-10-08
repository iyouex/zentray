#!/usr/bin/env bash
# ZenTray macOS 构建（docs/design/mac-interaction-design.md §12.5）
# 产出 dist/ZenTray.app；装有 create-dmg 时加制 dmg；设置 APPLE_* 三变量时公证。
# 前置：macOS 13+；python3 -m venv .venv && .venv/bin/pip install -e ".[mac]" pyinstaller
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m PyInstaller zentray.spec --noconfirm

APP="dist/ZenTray.app"
[[ -d "$APP" ]] || { echo "未生成 $APP（BUNDLE 仅在 macOS 上构建时产出）" >&2; exit 1; }

# 本地自用 ad-hoc 签名即可；分发请改用 Developer ID Application 证书
codesign --force --deep --sign - "$APP"

DMG="dist/ZenTray-macOS.dmg"
if command -v create-dmg >/dev/null 2>&1; then
  create-dmg --volname "ZenTray" --app-drop-link 425 210 "$DMG" "$APP" \
    || echo "create-dmg 失败（不影响 .app 产物）" >&2
fi

if [[ -n "${APPLE_API_KEY:-}" && -n "${APPLE_API_KEY_ID:-}" && -n "${APPLE_API_ISSUER:-}" && -f "$DMG" ]]; then
  xcrun notarytool submit "$DMG" \
    --key "$APPLE_API_KEY" --key-id "$APPLE_API_KEY_ID" --issuer "$APPLE_API_ISSUER" --wait
  xcrun stapler staple "$DMG" || true
fi

echo "产物: $APP$([[ -f $DMG ]] && echo ' + '"$DMG")"
