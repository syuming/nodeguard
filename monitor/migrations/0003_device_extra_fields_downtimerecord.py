from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("monitor", "0002_company_device_company_userprofile"),
    ]

    operations = [
        migrations.AddField(
            model_name="device",
            name="customer_name",
            field=models.CharField(blank=True, max_length=100, verbose_name="客戶名稱"),
        ),
        migrations.AddField(
            model_name="device",
            name="customer_id",
            field=models.CharField(blank=True, max_length=50, verbose_name="客戶編號"),
        ),
        migrations.AddField(
            model_name="device",
            name="circuit_number",
            field=models.CharField(blank=True, max_length=100, verbose_name="電路編號"),
        ),
        migrations.AddField(
            model_name="device",
            name="customer_address",
            field=models.TextField(blank=True, verbose_name="客戶地址"),
        ),
        migrations.AddField(
            model_name="device",
            name="monitor_interval",
            field=models.IntegerField(default=60, verbose_name="監控間隔（秒）"),
        ),
        migrations.CreateModel(
            name="DowntimeRecord",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("started_at", models.DateTimeField(verbose_name="斷線時間")),
                ("recovered_at", models.DateTimeField(blank=True, null=True, verbose_name="恢復時間")),
                ("duration_seconds", models.IntegerField(blank=True, null=True, verbose_name="持續秒數")),
                (
                    "device",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="downtimes",
                        to="monitor.device",
                    ),
                ),
            ],
            options={
                "verbose_name": "斷線記錄",
                "verbose_name_plural": "斷線記錄列表",
                "ordering": ["-started_at"],
            },
        ),
    ]
