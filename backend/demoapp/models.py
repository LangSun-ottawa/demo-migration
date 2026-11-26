from django.db import models


class DeviceRecord(models.Model):
    name = models.CharField(max_length=80, db_index=True)
    category = models.CharField(max_length=40)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ('id',)

    def __str__(self):
        return self.name


class AdminProfile(models.Model):
    name = models.CharField(max_length=80, unique=True)
    access_level = models.CharField(
        max_length=20,
        choices=(('readonly', 'Read only'), ('readwrite', 'Read/write')),
    )

    def __str__(self):
        return self.name


class AdminUserRecord(models.Model):
    username = models.CharField(max_length=80, unique=True)
    email = models.EmailField()
    profile = models.ForeignKey(AdminProfile, on_delete=models.PROTECT, related_name='users')

    def __str__(self):
        return self.username


class ManagedInstance(models.Model):
    name = models.CharField(max_length=80, unique=True)
    environment = models.CharField(
        max_length=20,
        choices=(('dev', 'Development'), ('test', 'Test'), ('prod', 'Production')),
    )
    status = models.CharField(max_length=20, default='ready')

    def __str__(self):
        return self.name


class AdapterConfig(models.Model):
    name = models.CharField(max_length=80, unique=True)
    adapter_type = models.CharField(
        max_length=30,
        choices=(('rest', 'REST'), ('syslog', 'Syslog'), ('custom', 'Custom')),
    )
    endpoint = models.CharField(max_length=200)
    instance = models.ForeignKey(ManagedInstance, on_delete=models.CASCADE, related_name='adapters')
    status = models.CharField(max_length=20, default='configured')

    def __str__(self):
        return self.name
