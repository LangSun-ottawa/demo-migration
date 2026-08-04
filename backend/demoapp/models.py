from django.db import models


class DeviceRecord(models.Model):
    name = models.CharField(max_length=80, db_index=True)
    category = models.CharField(max_length=40)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ('id',)

    def __str__(self):
        return self.name
