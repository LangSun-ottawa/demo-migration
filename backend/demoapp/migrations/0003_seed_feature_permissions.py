from django.db import migrations


DEMO_FEATURE_GROUPS = (
    'feature:model_comparison:readonly',
    'feature:security_inspection:readwrite',
    'feature:vm_association:readonly',
)


def seed_feature_permissions(apps, schema_editor):
    group_model = apps.get_model('auth', 'Group')
    user_model = apps.get_model('auth', 'User')
    demo_user = user_model.objects.filter(username='demo').first()

    for group_name in DEMO_FEATURE_GROUPS:
        group, _ = group_model.objects.get_or_create(name=group_name)
        if demo_user is not None:
            demo_user.groups.add(group)


def unseed_feature_permissions(apps, schema_editor):
    group_model = apps.get_model('auth', 'Group')
    group_model.objects.filter(name__in=DEMO_FEATURE_GROUPS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('demoapp', '0002_seed_architecture_lab'),
    ]

    operations = [
        migrations.RunPython(seed_feature_permissions, unseed_feature_permissions),
    ]

