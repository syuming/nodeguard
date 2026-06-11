"""既有 interval=3 的 ping 檢查原本就是跟著寫死的全域 3 秒跑，
轉為 NULL（跟隨持續監控）；其他自訂值（如 60）保留不動。
"""
from django.db import migrations


def to_follow(apps, schema_editor):
    MonitorCheck = apps.get_model("monitor", "MonitorCheck")
    MonitorCheck.objects.filter(check_type="ping", interval=3).update(interval=None)


def to_fixed(apps, schema_editor):
    MonitorCheck = apps.get_model("monitor", "MonitorCheck")
    MonitorCheck.objects.filter(check_type="ping", interval__isnull=True).update(interval=3)


class Migration(migrations.Migration):

    dependencies = [
        ("monitor", "0012_monitorconfig_alter_monitorcheck_interval"),
    ]

    operations = [
        migrations.RunPython(to_follow, to_fixed),
    ]
