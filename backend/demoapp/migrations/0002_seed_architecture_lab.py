from django.contrib.auth.hashers import make_password
from django.db import migrations


def seed_architecture_lab(apps, schema_editor):
    device_record = apps.get_model('demoapp', 'DeviceRecord')
    user = apps.get_model('auth', 'User')

    device_record.objects.bulk_create(
        [
            device_record(name='Alpha Django Sensor', category='legacy', active=True),
            device_record(name='Beta Django Gateway', category='edge', active=True),
            device_record(name='Gamma Django Archive', category='report', active=False),
        ],
        ignore_conflicts=True,
    )
    user.objects.update_or_create(
        username='demo',
        defaults={
            'password': make_password('DemoPass123!'),
            'is_active': True,
            'is_staff': False,
            'is_superuser': False,
        },
    )


def unseed_architecture_lab(apps, schema_editor):
    apps.get_model('demoapp', 'DeviceRecord').objects.filter(
        name__in=[
            'Alpha Django Sensor',
            'Beta Django Gateway',
            'Gamma Django Archive',
        ]
    ).delete()
    apps.get_model('auth', 'User').objects.filter(username='demo').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('demoapp', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_architecture_lab, unseed_architecture_lab),
    ]
