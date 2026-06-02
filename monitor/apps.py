import sys
from django.apps import AppConfig

_SKIP_CMDS = {"migrate", "makemigrations", "collectstatic", "shell", "createsuperuser"}


class MonitorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "monitor"

    def ready(self):
        if set(sys.argv) & _SKIP_CMDS:
            return
        from . import views
        import threading
        views._monitor_stop.clear()
        views._monitor_thread = threading.Thread(target=views._monitor_loop, daemon=True)
        views._monitor_thread.start()
