#!/bin/bash
set -euo pipefail

BASE_PREFIX=/opt/wineprefix-base
TARGET_PREFIX=${WINEPREFIX:-/config/.wine}

mkdir -p "$TARGET_PREFIX"
chmod 700 "$TARGET_PREFIX" 2>/dev/null || true
mkdir -p /siliconmt5/logs

if [ ! -f "$TARGET_PREFIX/.runtime_baked" ]; then
  echo "[runtime] seeding persistent prefix from baked runtime"
  rm -rf "$TARGET_PREFIX"
  mkdir -p "$(dirname "$TARGET_PREFIX")"
  cp -a "$BASE_PREFIX" "$TARGET_PREFIX"
  chown -R "$(id -u):$(id -g)" "$TARGET_PREFIX" 2>/dev/null || true
  chmod 700 "$TARGET_PREFIX" 2>/dev/null || true
fi

prefix_marker="$TARGET_PREFIX/.prefix_ready"
if [ -f "$prefix_marker" ]; then
  exit 0
fi

echo "[runtime] preparing persistent wine prefix at $TARGET_PREFIX"
WINEDLLOVERRIDES="mscoree=d" wineboot --init >/dev/null 2>&1 || true
wineserver -w || true
touch "$prefix_marker"
