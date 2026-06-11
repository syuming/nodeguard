"""持續監控背景執行緒。

狀態封裝在模組內，外部一律透過 start() / stop() / is_running() 操作。
全域監控間隔存於 MonitorConfig（DB），每輪迴圈重新讀取，修改即時生效。
"""
import threading

DEFAULT_INTERVAL = 3   # MonitorConfig 尚未建立時的後備值

_thread = None
_stop = threading.Event()


def get_global_interval() -> int:
    """讀取全域監控間隔（秒）。"""
    try:
        from .models import MonitorConfig
        return MonitorConfig.get_config().interval
    except Exception:
        return DEFAULT_INTERVAL


def _loop():
    from .models import Device
    from .utils import check_device

    while not _stop.is_set():
        for d in list(Device.objects.all()):
            if _stop.is_set():
                break
            try:
                # only_due：各監控項目依自身間隔（空值跟隨全域）判斷是否到期
                check_device(d, only_due=True)
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
