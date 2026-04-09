#!/bin/bash
set -euo pipefail

mkdir -p /config/.cache/openbox/sessions /siliconmt5/logs
chown -R abc:abc /config/.cache /siliconmt5/logs 2>/dev/null || true
chmod -R u+rwX /config/.cache /siliconmt5/logs 2>/dev/null || true
