import uuid
from django.conf import settings
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


class AssistantConversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(db_index=True)
    active_run_id = models.UUIDField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)


class AssistantTurn(models.Model):
    conversation = models.ForeignKey(AssistantConversation, on_delete=models.CASCADE, related_name='turns')
    run_id = models.UUIDField(unique=True)
    request_id = models.UUIDField()
    question = models.CharField(max_length=500)
    assistant_text = models.TextField(blank=True)
    status = models.CharField(max_length=20, default='running')
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ['id']


class AssistantToolCall(models.Model):
    turn = models.ForeignKey(AssistantTurn, on_delete=models.CASCADE, related_name='tools')
    call_id = models.CharField(max_length=256)
    name = models.CharField(max_length=80)
    arguments = models.JSONField(default=dict)
    result = models.JSONField(null=True)
    status = models.CharField(max_length=20, default='running')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        constraints = [models.UniqueConstraint(fields=['turn', 'call_id'], name='unique_assistant_tool_call')]


class CreateOperation(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    key = models.UUIDField()
    fingerprint = models.CharField(max_length=64)
    resource = models.CharField(max_length=20)
    result = models.JSONField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['owner', 'key'], name='unique_user_create_operation')]


class SamlIdentity(models.Model):
    issuer = models.CharField(max_length=500)
    subject = models.CharField(max_length=500)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['issuer', 'subject'], name='unique_saml_identity')]


class SamlReplay(models.Model):
    # Hash of issuer + assertion ID; unique across workers and browser sessions.
    digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()


class LogDataset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    simulated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class LogDevice(models.Model):
    dataset = models.ForeignKey(LogDataset, on_delete=models.CASCADE, related_name='devices')
    name = models.CharField(max_length=80)
    device_type = models.CharField(max_length=40)
    ip = models.GenericIPAddressField()


class LogEvent(models.Model):
    dataset = models.ForeignKey(LogDataset, on_delete=models.CASCADE, related_name='events')
    device = models.ForeignKey(LogDevice, on_delete=models.CASCADE, related_name='events')
    occurred_at = models.DateTimeField(db_index=True)
    kind = models.CharField(max_length=20)  # traffic / config_change / threat
    action = models.CharField(max_length=30)
    src_ip = models.GenericIPAddressField(null=True)
    dst_ip = models.GenericIPAddressField(null=True)
    dst_port = models.PositiveIntegerField(null=True)
    session_id = models.CharField(max_length=80, blank=True)
    policy_id = models.CharField(max_length=80, blank=True)
    threat = models.CharField(max_length=120, blank=True)
    message = models.CharField(max_length=1000)
    raw = models.JSONField()

    class Meta:
        ordering = ['occurred_at', 'id']
