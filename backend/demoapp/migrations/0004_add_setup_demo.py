from django.db import migrations, models
import django.db.models.deletion


DEMO_SETUP_GROUP = 'feature:demo_setup:readwrite'


def grant_demo_setup(apps, schema_editor):
    group_model = apps.get_model('auth', 'Group')
    user_model = apps.get_model('auth', 'User')
    group, _ = group_model.objects.get_or_create(name=DEMO_SETUP_GROUP)
    demo_user = user_model.objects.filter(username='demo').first()
    if demo_user is not None:
        demo_user.groups.add(group)


def revoke_demo_setup(apps, schema_editor):
    group_model = apps.get_model('auth', 'Group')
    group_model.objects.filter(name=DEMO_SETUP_GROUP).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('demoapp', '0003_seed_feature_permissions'),
    ]

    operations = [
        migrations.CreateModel(
            name='AdminProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=80, unique=True)),
                ('access_level', models.CharField(choices=[('readonly', 'Read only'), ('readwrite', 'Read/write')], max_length=20)),
            ],
        ),
        migrations.CreateModel(
            name='ManagedInstance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=80, unique=True)),
                ('environment', models.CharField(choices=[('dev', 'Development'), ('test', 'Test'), ('prod', 'Production')], max_length=20)),
                ('status', models.CharField(default='ready', max_length=20)),
            ],
        ),
        migrations.CreateModel(
            name='AdminUserRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('username', models.CharField(max_length=80, unique=True)),
                ('email', models.EmailField(max_length=254)),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='users', to='demoapp.adminprofile')),
            ],
        ),
        migrations.CreateModel(
            name='AdapterConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=80, unique=True)),
                ('adapter_type', models.CharField(choices=[('rest', 'REST'), ('syslog', 'Syslog'), ('custom', 'Custom')], max_length=30)),
                ('endpoint', models.CharField(max_length=200)),
                ('status', models.CharField(default='configured', max_length=20)),
                ('instance', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='adapters', to='demoapp.managedinstance')),
            ],
        ),
        migrations.RunPython(grant_demo_setup, revoke_demo_setup),
    ]
