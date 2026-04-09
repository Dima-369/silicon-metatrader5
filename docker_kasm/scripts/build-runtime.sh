#!/bin/bash
set -euo pipefail

export WINEPREFIX=/opt/wineprefix-base
mkdir -p "$WINEPREFIX"

python_installer='/tmp/python-installer.exe'

XVFB_DISPLAY=:99
Xvfb "$XVFB_DISPLAY" -screen 0 1024x768x24 >/tmp/build-xvfb.log 2>&1 &
XVFB_PID=$!
trap 'kill "$XVFB_PID" >/dev/null 2>&1 || true' EXIT
export DISPLAY=$XVFB_DISPLAY
sleep 2

echo "[build] initializing base wine prefix"
WINEDLLOVERRIDES="mscoree=d" wineboot --init >/dev/null 2>&1 || true
wineserver -w || true

echo "[build] installing Windows Python"
curl -L "$PYTHON_URL" -o "$python_installer"
wine "$python_installer" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
rm -f "$python_installer"

echo "[build] installing VC runtime"
winetricks --unattended vcrun2019 >/dev/null 2>&1 || true

echo "[build] upgrading pip in wine"
wine python -m pip install --upgrade --no-cache-dir pip

echo "[build] installing siliconmetatrader5 requirements in wine"
wine python -m pip install --no-cache-dir -r /siliconmt5/requirements.txt

echo "[build] validating runtime"
wine python --version >/dev/null 2>&1
wine python -c "import siliconmetatrader5; print('siliconmetatrader5 ok')" >/dev/null 2>&1

touch "$WINEPREFIX/.runtime_baked"
