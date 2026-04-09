#!/bin/bash
set -euo pipefail

mt5file="$WINEPREFIX/drive_c/Program Files/MetaTrader 5/terminal64.exe"

if [ ! -f "$mt5file" ]; then
  echo "[runtime] ERROR: terminal64.exe not found" >&2
  exit 1
fi

cfg_src=/siliconmt5/mt5cfg.ini
mt5_dir="$(dirname "$mt5file")"
cfg_dst="$mt5_dir/mt5cfg.ini"
cfg_hash_file="$WINEPREFIX/.mt5cfg_image.sha256"
cfg_src_hash="$(sha256sum "$cfg_src" | awk '{print $1}')"
cfg_last_hash="$(cat "$cfg_hash_file" 2>/dev/null || true)"

if [ ! -f "$cfg_dst" ] || [ "$cfg_src_hash" != "$cfg_last_hash" ]; then
  cp "$cfg_src" "$cfg_dst"
  echo "$cfg_src_hash" > "$cfg_hash_file"
  echo "[runtime] mt5cfg.ini synchronized"
fi

cd "$mt5_dir"
exec wine terminal64.exe /portable /config:mt5cfg.ini
