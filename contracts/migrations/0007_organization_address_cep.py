from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contracts", "0006_procurementitem_supplier"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="address",
            field=models.TextField(blank=True, verbose_name="endereço"),
        ),
        migrations.AddField(
            model_name="organization",
            name="cep",
            field=models.CharField(blank=True, max_length=9, verbose_name="CEP"),
        ),
    ]
