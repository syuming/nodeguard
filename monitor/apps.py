import sys
from django.apps import AppConfig

_SKIP_CMDS = {"migrate", "makemigrations", "collectstatic", "shell", "createsuperuser"}


class MonitorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "monitor"

    def ready(self):
        if set(sys.argv) & _SKIP_CMDS:
            return
        from . import monitoring
        monitoring.start()
