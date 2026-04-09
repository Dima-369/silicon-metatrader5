#!/bin/bash
set -euo pipefail

WIN_PYTHON="C:/Program Files/Python313/python.exe"
exec wine python -m siliconmetatrader5 "$WIN_PYTHON" --host 0.0.0.0 -p 8001
