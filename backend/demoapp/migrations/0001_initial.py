from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='DeviceRecord',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('name', models.CharField(db_index=True, max_length=80)),
                ('category', models.CharField(max_length=40)),
                ('active', models.BooleanField(default=True)),
            ],
            options={'ordering': ('id',)},
        ),
    ]
