"""將既有明文憑證轉為密文。

讀取時 EncryptedCharField 會解密（舊明文原樣回傳），
重新儲存即寫入密文，因此重複執行也安全（冪等）。
"""
from django.db import migrations


def encrypt_existing(apps, schema_editor):
    EmailConfig = apps.get_model("monitor", "EmailConfig")
    MonitorCheck = apps.get_model("monitor", "MonitorCheck")

    for cfg in EmailConfig.objects.exclude(password=""):
        cfg.save(update_fields=["password"])

    for check in MonitorCheck.objects.all():
        fields = []
        if check.ssh_password:
            fields.append("ssh_password")
        if check.snmp_community:
            fields.append("snmp_community")
        if fields:
            check.save(update_fields=fields)


class Migration(migrations.Migration):

    dependencies = [
        ("monitor", "0010_alter_device_device_type_alter_emailconfig_password_and_more"),
    ]

    operations = [
        migrations.RunPython(encrypt_existing, migrations.RunPython.noop),
    ]
