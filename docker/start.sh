#!/bin/bash
# macOS Silicon Optimized MT5
# Devoloper: bahadirumutiscimen
cd /siliconmt5
mkdir -p /siliconmt5/logs

# Clear existing display locks to prevent startup errors
rm -rf /tmp/.X100-lock

# Initialize virtual display (Xvfb) and VNC server
export DISPLAY=:100
Xvfb :100 -ac -screen 0 1024x768x16 &
x11vnc -display :100 -forever -rfbport 5901 -nopw -ncache 10 &
/siliconmt5/noVNC-master/utils/novnc_proxy --vnc localhost:5901 --listen 6081 &

# Start Openbox Window Manager (Minimalist) - Uncomment to enable
# openbox &

# Check for MT5 installation and install if missing.
# The MetaQuotes CDN installer URL can return HTTP 403 from Docker/Colima. Keep the
# official installer outside the image and mount it at /siliconmt5/mt5setup.exe.
if [ ! -f "/opt/wineprefix/drive_c/Program Files/MetaTrader 5/terminal64.exe" ]; then
  echo "Installing MetaTrader 5..."
  INSTALLER=/siliconmt5/mt5setup.exe
  if [ ! -s "$INSTALLER" ]; then
    echo "ERROR: valid MT5 installer missing at $INSTALLER"
    exit 1
  fi
  wine "$INSTALLER" /auto
  # Give the installer enough time to complete.
  echo "Waiting for MT5 install..."
  sleep 20
  wine taskkill /IM "terminal64.exe" /F || true
fi

# Locate and launch MetaTrader 5
echo "Locating MT5 installation..."
MT5_EXE=$(find /opt/wineprefix/drive_c -name "terminal64.exe" -print -quit)

if [ -z "$MT5_EXE" ]; then
    echo "ERROR: terminal64.exe not found! Installation failed?"
    exit 1
fi

MT5_DIR=$(dirname "$MT5_EXE")
echo "Found MT5 at: $MT5_DIR"

# mt5cfg sync policy:
# - First boot: seed config.
# - Subsequent boots: overwrite ONLY if image mt5cfg changed (build update).
CFG_SRC="/siliconmt5/mt5cfg.ini"
CFG_DST="$MT5_DIR/mt5cfg.ini"
CFG_HASH_FILE="/opt/wineprefix/.mt5cfg_image.sha256"
CFG_SRC_HASH="$(sha256sum "$CFG_SRC" | awk '{print $1}')"
CFG_LAST_HASH=""
if [ -f "$CFG_HASH_FILE" ]; then
  CFG_LAST_HASH="$(cat "$CFG_HASH_FILE" 2>/dev/null || true)"
fi

if [ ! -f "$CFG_DST" ]; then
  cp "$CFG_SRC" "$CFG_DST"
  echo "$CFG_SRC_HASH" > "$CFG_HASH_FILE"
  echo "Seeded default mt5cfg.ini (first boot)"
elif [ "$CFG_SRC_HASH" != "$CFG_LAST_HASH" ]; then
  cp "$CFG_SRC" "$CFG_DST"
  echo "$CFG_SRC_HASH" > "$CFG_HASH_FILE"
  echo "Applied updated mt5cfg.ini from image (build change detected)"
else
  echo "Keeping existing mt5cfg.ini (no build-time config change detected)"
fi

cd "$MT5_DIR"
wine terminal64.exe /portable /config:mt5cfg.ini >> /siliconmt5/logs/mt5_runtime.log 2>&1 &
MT5_PID=$!
echo "Waiting 15s for MT5 Windows to instantiate..."
sleep 15

# Start the Silicon Bridge (Python Interface) - v1.0 style
cd /siliconmt5
mkdir -p /siliconmt5/logs
wine python -m siliconmetatrader5 "C:/Python/python.exe" --host "$MT5_HOST" -p 8001 >> /siliconmt5/logs/bridge_runtime.log 2>&1 &
BRIDGE_PID=$!
echo "Waiting 30s for MT5 Silicon to instantiate..."
sleep 30
while true
do
  if ! pgrep -f "terminal64.exe" > /dev/null; then
    echo "⚠️ MT5 process not found! Restarting..."
    cd "$MT5_DIR"
    wine terminal64.exe /portable /config:mt5cfg.ini >> /siliconmt5/logs/mt5_runtime.log 2>&1 &
MT5_PID=$!
    echo "✅ MT5 Restarted."
    sleep 10
  fi
  sleep 5
done
