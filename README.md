# SiliconMetaTrader5 🍏📈
**MetaTrader 5 solution for macOS Apple Silicon**

🇹🇷 **[Türkçe Oku](README_TR.md)**

**Developer:** Bahadir Umut Iscimen

> [!NOTE]
> Clarification: This project does **NOT** replace the native MetaTrader 5 application installed on your computer.
> It runs a separate, headless MT5 instance via Docker to enable Python communication and algorithmic trading on macOS.
> This project is an end-to-end solution developed to run MetaTrader 5 seamlessly on macOS Silicon devices (Docker) and to perform professional algorithmic trading with Python (client).

> [!CAUTION]
> Important usage purpose: This infrastructure is designed to make strategy development, backtesting, and forward-testing comfortable in the macOS environment.
> For live (production) trading that requires millisecond precision, is critical, or involves high capital, using a physical PC or server with native Windows (no emulation layer) is recommended.

---

## What this repo contains

- `docker/`: MT5 runtime on Wine + QEMU
- `client/`: Python client package (`siliconmetatrader5`)
- `tests/`: validation scripts

---


## System Workflow Diagram

![System Architecture](assets/system-arch.png)

### Screenshots
**Running on Localhost (VNC):**
![Localhost VNC](assets/localhost.png)

**Python Data Fetching:**
![Data Fetch](assets/fetch_data.png)

---

## Data methods: choose by use case

| Use case | Recommended method |
|---|---|
| Live monitor / fresh bars | `copy_rates_from_pos()` |
| Backtest/history by date range | `copy_rates_from()` / `copy_rates_range()` |

```python
# live
live_rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M5, 0, 500)

# backtest/history
hist_rates = mt5.copy_rates_range("EURUSD", mt5.TIMEFRAME_M5, dt_from, dt_to)
```

---

## Zero-to-Hero Setup

We proceed assuming nothing is installed on your computer.

### 1) Preparation

Open Terminal and install required tools:

```bash
# 1) Install Homebrew (skip if already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2) Install required packages
brew install colima docker qemu lima lima-additional-guestagents
```

### 2) Start the engine (Colima)

We use Colima with x86_64 emulation so Docker can run MT5 runtime components correctly on Apple Silicon.

```bash
# Optional reset (only if you previously installed colima for siliconmetatrader5,
# or if your current Colima state looks broken)
# colima delete -f

colima start --arch x86_64 --vm-type=qemu --cpu 4 --memory 8
```

### 3) Install and start MT5 server

```bash
cd docker

# Option 1: Foreground (recommended for first setup, you see live logs)
docker compose up --build

# Option 2: Detached (after system is stable)
# docker compose up --build -d
```

Notes:
- First build can take about 5-10 minutes.
- During first initialization, transition from black screen to MT5 screen can take 25-30 minutes.
- If you run `docker compose up` in foreground, `Ctrl+C` stops the compose session and containers.
- If you run detached mode, use `docker compose logs -f`; then `Ctrl+C` only exits log streaming.
- Visual access: [http://localhost:6081/vnc.html](http://localhost:6081/vnc.html) (password: `123456`).
- First action: when MT5 opens, go to `File > Open an Account`, find your broker, and log in manually once.
- Warning: even if Colima is still running, if the Docker/MT5 container is stopped, restarting the container may require MT5 login again.
- Keep that terminal open (or continue in a new terminal tab).

### 4) Install Python client

Install/update the client package:

```bash
python3 -m pip install --upgrade "siliconmetatrader5==1.2.0"
```

### 5) Test the connection

```bash
python tests/test_fetch.py
python tests/test_plot.py
```

If terminal outputs show successful connection/data flow, setup is complete.

---

## Challenges Encountered and Solutions

This project is designed to handle practical challenges of running x86 workloads on macOS Silicon.

- Architecture mismatch: crash issues were mitigated by using QEMU-based full x86_64 emulation (Colima) instead of relying on Rosetta-only behavior.
- IPC timeout patterns: Python-to-MT5 disconnections can happen under emulation pressure; the client side includes retry-oriented behavior for stability.
- SSL/TLS compatibility: broker communication reliability was improved by including required Windows/Wine dependencies (such as winbind/certificate-related components).

---

## Advanced Settings (Timezone & Screen)

### Change timezone

Default is `Europe/Istanbul`. To change it, edit `docker/compose.yaml`:

```yaml
# docker/compose.yaml
environment:
  - TZ=America/New_York  # or UTC, Asia/Tokyo, etc.
```

Note: This setting does **not** change your broker server time. It only changes the Linux/container (VNC layer) timezone.

Reference: [Wikipedia Time Zone List](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)

### Screen resolution and window behavior

Edit `docker/start.sh`:

```bash
# docker/start.sh
# Resolution example
Xvfb :100 -ac -screen 0 1366x768x24 &

# Window manager (optional)
# openbox &
```

Performance warning: enabling a window manager (Openbox) adds graphics overhead and may slightly reduce VNC smoothness (higher latency).

Apply changes with:

```bash
cd docker && docker compose up --build -d
```

---

## MT5 History Depth (MaxBars)

File: `docker/mt5cfg.ini`

You can increase:

```ini
MaxBars=5000
```

to one of these values:

- `100000`
- `250000`
- `500000`
- `1000000`

Effect:
- Backtest/history flows can access deeper bar history.
- Live systems that use long lookback calculations can also benefit from wider available history.

Trade-off:
- Higher memory/storage usage and potentially slower startup/sync time.

After changing `MaxBars`, rebuild/restart containers:

```bash
cd docker && docker compose up --build -d
```

## Example usage

```python
from siliconmetatrader5 import MetaTrader5
import pandas as pd

mt5 = MetaTrader5(host="localhost", port=8001, keepalive=True)

if not mt5.initialize():
    raise RuntimeError("MT5 initialize failed")

rates_live = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M15, 0, 150)
print(pd.DataFrame(rates_live).tail())

mt5.close()  # closes only this process connection
```

---

## Client v1.2.0 (Important)

### Install / Upgrade Python client

To receive this release, run:

```bash
python3 -m pip install --upgrade "siliconmetatrader5==1.2.0"
python3 -m pip show siliconmetatrader5
```

Expected: `Version: 1.2.0`

---

### Main behavior changes

1. `close()` vs `shutdown()`
- `close()` only closes this process client connection.
- `shutdown()` / `close(remote_shutdown=True)` stops the remote MT5 terminal globally.

Bot1/Bot2/Bot3 practical scenario:

- Bot1 = monitor
- Bot2 = trade
- Bot3 = history/backtest

Normal exits for Bot1/Bot2/Bot3 must use `close()` only.
Global stop should be done only by an orchestrator process using `shutdown()` (or `close(remote_shutdown=True)`).

2. Timeout semantics
- `timeout` is accepted for backward compatibility.
- Active per-call timeout behavior is removed.
- For long-running bots use `keepalive=True`.

3. Watchdog support
- `start_watchdog(...)`, `stop_watchdog()`, `health_status()`
- Detects frozen/unresponsive bridge conditions.

4. Reliability improvements
- direct remote call dispatch in wrappers
- normalized bridge errors (`TIMEOUT`, `RESULT_EXPIRED`, `CONNECTION_CLOSED`, `RPC_ERROR`)
- `market_book_release(symbol)` forwarding fix

---

## Daily routine

Start:

```bash
if colima status 2>/dev/null | grep -q "colima is running"; then
  echo "Colima already running"
else
  colima start
fi
cd docker && docker compose up -d
```

Stop:

```bash
cd docker && docker compose down
colima stop
```

---

## FAQ

**Q: I rebooted my Mac, what do I run?**

Note: Run the command from the repository root; `cd docker` is a relative path.

```bash
if colima status 2>/dev/null | grep -q "colima is running"; then
  echo "Colima already running"
else
  colima start
fi
cd docker && docker compose up -d
```

**Q: MT5 screen stays black?**

A: Make sure Colima is running in QEMU/x86_64 mode. Also start in foreground debug mode (not detached `-d`) to see startup errors:

```bash
colima status
cd docker && docker compose up --build
```

**Q: How do I stop MT5 safely?**

```bash
cd docker && docker compose down
```
