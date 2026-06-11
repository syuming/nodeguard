"""持續監控背景執行緒。

狀態封裝在模組內，外部一律透過 start() / stop() / is_running() 操作。
"""
import threading

MONITOR_INTERVAL = 3   # 每隔幾秒檢查一次（預設 3 秒）

_thread = None
_stop = threading.Event()


def _loop():
    from django.utils import timezone as tz

    from .models import Device
    from .utils import check_device

    while not _stop.is_set():
        now = tz.now()
        for d in list(Device.objects.all()):
            if _stop.is_set():
                break
            if d.last_checked is None or (now - d.last_checked).total_seconds() >= MONITOR_INTERVAL:
                try:
                    check_device(d)
                except Exception:
                    pass
        _stop.wait(1)   # 每 1 秒輪詢一次，支援最低 1 秒間隔


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()


def start() -> None:
    global _thread
    if is_running():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True)
    _thread.start()


def stop() -> None:
    global _thread
    _stop.set()
    _thread = None
