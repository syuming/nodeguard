from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("monitor", "0008_add_snmp_label"),
    ]

    operations = [
        migrations.AddField(
            model_name="downtimerecord",
            name="reason",
            field=models.TextField(blank=True, verbose_name="斷線原因"),
        ),
    ]
