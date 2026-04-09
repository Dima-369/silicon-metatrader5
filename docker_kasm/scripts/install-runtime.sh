#!/bin/bash
set -euo pipefail

cd /siliconmt5

/siliconmt5/scripts/prepare-prefix.sh

mt5file="$WINEPREFIX/drive_c/Program Files/MetaTrader 5/terminal64.exe"
mt5_installer='/tmp/mt5setup.exe'

if [ -f "$mt5file" ]; then
  echo "[runtime] MT5 already installed"
  exit 0
fi

echo "[runtime] installing MetaTrader 5"
wine reg add 'HKEY_CURRENT_USER\Software\Wine' /v Version /t REG_SZ /d 'win10' /f >/dev/null 2>&1 || true
curl -L "$MT5_URL" -o "$mt5_installer"
wine "$mt5_installer" /auto || true
rm -f "$mt5_installer"

for i in $(seq 1 90); do
  if [ -f "$mt5file" ]; then
    echo "[runtime] MT5 installation detected"
    exit 0
  fi
  sleep 2
done

echo "[runtime] ERROR: terminal64.exe not found after MT5 runtime install"
find "$WINEPREFIX/drive_c" -iname 'terminal64.exe' -o -iname 'metatrader*.exe' | sort || true
exit 1
