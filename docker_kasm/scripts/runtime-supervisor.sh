#!/bin/bash
set -euo pipefail

export WINEPREFIX=/config/.wine
cd /siliconmt5
mkdir -p /siliconmt5/logs

/siliconmt5/scripts/install-runtime.sh

launch_mt5_bg() {
  /siliconmt5/scripts/launch-mt5.sh >> /siliconmt5/logs/mt5_runtime.log 2>&1 &
  echo $!
}

launch_bridge_bg() {
  /siliconmt5/scripts/launch-bridge.sh >> /siliconmt5/logs/bridge_runtime.log 2>&1 &
  echo $!
}

MT5_PID="$(launch_mt5_bg)"
echo "[runtime] MT5 pid=$MT5_PID"
sleep 15
BRIDGE_PID="$(launch_bridge_bg)"
echo "[runtime] bridge pid=$BRIDGE_PID"
sleep 10

while true; do
  if ! pgrep -f 'terminal64.exe' >/dev/null; then
    echo "[runtime] MT5 not running, restarting"
    MT5_PID="$(launch_mt5_bg)"
    echo "[runtime] MT5 pid=$MT5_PID"
    sleep 15
  fi
  if ! pgrep -f 'python.exe.*-m siliconmetatrader5.*8001' >/dev/null; then
    echo "[runtime] bridge process missing, restarting"
    pkill -f 'python.exe.*-m siliconmetatrader5.*8001' >/dev/null 2>&1 || true
    pkill -f 'start.exe /exec python -m siliconmetatrader5' >/dev/null 2>&1 || true
    BRIDGE_PID="$(launch_bridge_bg)"
    echo "[runtime] bridge pid=$BRIDGE_PID"
    sleep 10
  fi
  sleep 5
done
