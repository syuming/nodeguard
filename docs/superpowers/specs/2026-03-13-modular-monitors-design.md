# Modular Monitor Design

**Date:** 2026-03-13
**Project:** netmonitor
**Status:** Approved

## Overview

Refactor the current monolithic per-device check into a flexible, per-monitor architecture. Each device can have multiple independent monitors (Ping, SSH, Port, etc.), each with its own interval, status, logs, and pause control. New monitor types can be added by registering a single class.

---

## Data Model

### New: `DeviceMonitor`

| Field         | Type               | Notes                                         |
|---------------|--------------------|-----------------------------------------------|
| `device`      | ForeignKey(Device) | Cascade delete                                |
| `monitor_type`| CharField          | `"ping"` / `"ssh"` / `"port"` / ...          |
| `name`        | CharField          | User-defined label, e.g. "主線路 Ping"        |
| `config`      | JSONField          | Type-specific parameters (see below)          |
| `interval`    | IntegerField       | Polling interval in seconds                   |
| `enabled`     | BooleanField       | Individual pause/resume (default True)        |
| `status`      | CharField          | `online` / `offline` / `warning` / `unknown` |
| `last_checked`| DateTimeField      | Nullable                                      |

**Meta:** `ordering = ["device", "monitor_type"]`, `__str__` returns `"{device.name} – {name}"`

**config examples:**
```json
// ping
{"count": 3, "timeout": 2}

// ssh
{"username": "admin", "password": "secret", "port": 22}

// port (future)
{"port": 443, "timeout": 3}
```

> **Security note:** `config` stores SSH passwords in plaintext (same as the current `Device.ssh_password` field). This is a known risk deferred to a future `EncryptedJSONField` implementation.

### New: `MonitorLog`

| Field        | Type                      | Notes                                          |
|--------------|---------------------------|------------------------------------------------|
| `monitor`    | ForeignKey(DeviceMonitor) | Cascade delete                                 |
| `level`      | CharField                 | `success` / `error` / `warning` / `info`      |
| `message`    | TextField                 |                                                |
| `raw_output` | TextField                 | Optional raw command output                    |
| `created_at` | DateTimeField             | Auto                                           |

**Meta:** `ordering = ["-created_at"]`, `__str__` returns `"[{level}] {monitor} – {created_at}"`

> **Log retention:** No pruning is implemented in this iteration. Views will limit queries to the most recent 100 log entries. A pruning job should be added in a future iteration.

### Modified: `Device`

- **Remove:** `ssh_username`, `ssh_password`, `ssh_port`, `monitor_interval`
- **Remove:** `last_checked` (replaced by per-monitor `last_checked` on `DeviceMonitor`)
- **Add:** `monitoring_paused` BooleanField (default False) — pauses all monitors for this device

### Retained: `DowntimeRecord`

`DowntimeRecord` is retained unchanged. The `run_monitor()` function replicates the transition logic from the current `check_device()`:
- Device transitions to `offline` → create a new `DowntimeRecord(started_at=now)`
- Device transitions from `offline` → close the most recent open `DowntimeRecord` (set `recovered_at` and `duration_seconds`)

The device detail template's downtime section remains unchanged.

### Removed: `DeviceLog`

Replaced entirely by `MonitorLog`.

### Device Status Aggregation

After every `run_monitor()` call, device `status` is recalculated from all **enabled** `DeviceMonitor` statuses:

1. Any monitor `offline` → device `offline`
2. Any monitor `warning` → device `warning`
3. All monitors `online` → device `online`
4. No enabled monitors, or all `unknown` → device `unknown`

Device `status` is the only device-level status field. There is no `Device.last_checked`; the dashboard displays the earliest `DeviceMonitor.last_checked` among a device's monitors, or "—" if none.

---

## Migration Strategy

The schema change removes fields that currently hold live data. The migration must be split into two steps:

**Step 1 – Data migration** (before removing old fields):
- For every `Device` that has `ssh_username` set: create a `SSHMonitor` with config `{"username": ssh_username, "password": ssh_password, "port": ssh_port}` and `interval = monitor_interval`.
- For every `Device`: create a `PingMonitor` with default config `{"count": 3, "timeout": 2}` and `interval = monitor_interval` (or 60 if null).

**Step 2 – Schema migration**: remove `ssh_username`, `ssh_password`, `ssh_port`, `monitor_interval`, `last_checked` from `Device`.

`DeviceForm` is updated to remove those four fields. No transitional form is needed.

---

## Monitor Execution Architecture

### File Structure

```
monitor/
  monitors/
    __init__.py
    base.py       # BaseMonitor abstract class
    ping.py       # PingMonitor
    ssh.py        # SSHMonitor
    registry.py   # REGISTRY dict + run_monitor()
```

### BaseMonitor Interface

```python
class BaseMonitor:
    monitor_type: str = ""

    def __init__(self, monitor: DeviceMonitor):
        self.monitor = monitor
        self.config = monitor.config

    def run(self) -> tuple[str, str, str]:
        """Returns (status, message, raw_output)"""
        raise NotImplementedError
```

### Registry

```python
REGISTRY: dict[str, type[BaseMonitor]] = {
    "ping": PingMonitor,
    "ssh":  SSHMonitor,
}

def run_monitor(monitor: DeviceMonitor) -> str:
    """Execute a monitor, save MonitorLog, update device status and DowntimeRecord.
    Returns new monitor status."""
```

`run_monitor()` responsibilities:
1. Look up monitor class from REGISTRY
2. Call `.run()` to get `(status, message, raw_output)`
3. Write a `MonitorLog` record
4. Update `monitor.status` and `monitor.last_checked`
5. Recalculate and update `device.status` via aggregation logic
6. Apply `DowntimeRecord` transition logic (same as existing `check_device()`)
7. Return new monitor status

### Background Thread

`_monitor_loop()` iterates over `DeviceMonitor` objects instead of `Device` objects:

```
for each DeviceMonitor where enabled=True and device.monitoring_paused=False:
    if last_checked is None or elapsed >= monitor.interval:
        run_monitor(monitor)
```

The global stop/start toggle (`_monitor_stop` event) is preserved unchanged.

### Adding a New Monitor Type

1. Create `monitor/monitors/<type>.py` with a class inheriting `BaseMonitor`
2. Add one line to `REGISTRY` in `registry.py`
3. No migrations needed (type stored as string in `DeviceMonitor.monitor_type`)

---

## URL Routes

### New routes (added to `monitor/urls.py`)

```
POST /device/<pk>/monitor/add/                  # Add a monitor to a device
POST /device/<pk>/monitor/<mid>/delete/         # Remove a monitor (POST only)
POST /device/<pk>/monitor/pause-all/            # Pause/resume all monitors for device
POST /api/monitor/<mid>/toggle/                 # Pause/resume individual monitor
POST /api/monitor/<mid>/check/                  # Manually trigger a single monitor
GET  /api/monitor/<mid>/logs/                   # Fetch recent logs for a monitor
```

All new routes that operate on a `DeviceMonitor` object must call `can_access_device(request.user, monitor.device)` and raise `Http404` on failure, consistent with existing device views.

The existing global toggle at `POST /api/monitor/toggle/` (name: `api_monitor_toggle`) is **unchanged**.

All mutating routes use POST only. No HTTP method override middleware is used.

---

## UI Design

### Device Detail Page (`/device/<pk>/`)

```
┌─────────────────────────────────────────────────────┐
│ 設備：Router-01 (192.168.1.1)              [編輯]   │
│ 整體狀態：● Online      [⏸ 暫停此設備所有監控]     │
├─────────────────────────────────────────────────────┤
│ 監控項目                            [+ 新增監控]    │
│                                                     │
│ ● Ping 監控    Online   30s  [⏸ 暫停] [刪除]       │
│   最後檢查：2 分鐘前，回應 2.3ms                    │
│                                                     │
│ ⏸ SSH 監控    已暫停    5m   [▶ 恢復] [刪除]       │
│   最後檢查：10 分鐘前                               │
├─────────────────────────────────────────────────────┤
│ 最新 Logs   [全部] [Ping] [SSH]                     │
│ 2026-03-13 10:00  Ping  ✓ 回應 2.3ms               │
│ 2026-03-13 09:55  SSH   ✗ 連線失敗                  │
└─────────────────────────────────────────────────────┘
```

### Add Monitor Form

Triggered by "+ 新增監控" button. Rendered as a separate page (`/device/<pk>/monitor/add/`) with server-side form. Two-step approach:

1. User selects monitor type from dropdown.
2. Form reloads (or submits) with type-specific config fields shown.

Type-specific fields per monitor:
- **Ping:** Count (default 3), Timeout (default 2)
- **SSH:** Username, Password, Port (default 22)

No JavaScript dynamic field switching. Type selection triggers a standard form GET with `?type=ping` to show the correct fields server-side.

### Dashboard Page

Global monitor toggle button (existing) is preserved unchanged.

---

## Removed / Changed Code

| Item | Action |
|------|--------|
| `Device.ssh_username/password/port` | Removed (data migrated to SSHMonitor config) |
| `Device.monitor_interval` | Removed (data migrated to DeviceMonitor.interval) |
| `Device.last_checked` | Removed (replaced by per-monitor last_checked) |
| `DeviceLog` model | Removed, replaced by `MonitorLog` |
| `monitor/utils.py` | Replaced by `monitor/monitors/` package |
| `views._monitor_loop()` | Updated to iterate DeviceMonitor |
| `DeviceForm` | Remove ssh/interval fields |
