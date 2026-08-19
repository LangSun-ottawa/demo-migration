from django.core.validators import FileExtensionValidator
from django.utils.html import escape
from rest_framework import serializers

from demoapp.api.base import EmptySerializer, StrictSerializer


class MetadataSerializer(StrictSerializer):
    source = serializers.CharField(max_length=30, allow_blank=False)


class EchoSerializer(StrictSerializer):
    name = serializers.CharField(
        max_length=60,
        allow_blank=False,
        trim_whitespace=False,
    )
    age = serializers.IntegerField(min_value=18, max_value=99)
    active = serializers.BooleanField()
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)
    metadata = MetadataSerializer()
    tags = serializers.ListField(
        child=serializers.CharField(max_length=20, allow_blank=False),
    )


class LoginSerializer(StrictSerializer):
    username = serializers.RegexField(
        regex=r'\A[A-Za-z0-9_.-]+\Z',
        max_length=30,
        allow_blank=False,
    )
    password = serializers.CharField(
        max_length=128,
        allow_blank=False,
        trim_whitespace=False,
        write_only=True,
    )


class SecurityInspectionSerializer(StrictSerializer):
    display_name = serializers.CharField(max_length=120, allow_blank=False)
    lookup_term = serializers.CharField(max_length=80, allow_blank=False)
    safe_identifier = serializers.RegexField(
        regex=r'\A[A-Za-z0-9_-]+\Z',
        max_length=40,
        allow_blank=False,
    )

    def validate_display_name(self, value):
        return escape(value)


class ModelComparisonQuerySerializer(StrictSerializer):
    term = serializers.CharField(max_length=80, allow_blank=False)


class VmAssociationContextQuerySerializer(StrictSerializer):
    record_id = serializers.IntegerField(min_value=1)


class SearchQuerySerializer(StrictSerializer):
    term = serializers.CharField(max_length=40, allow_blank=False)
    limit = serializers.IntegerField(min_value=1, max_value=10, required=False)
    active = serializers.BooleanField(required=False)


class UploadSerializer(StrictSerializer):
    attachment = serializers.FileField(
        validators=[FileExtensionValidator(['txt', 'md', 'json'])],
    )

    def validate_attachment(self, value):
        if value.size > 1024 * 1024:
            raise serializers.ValidationError('File exceeds the 1 MiB limit.')
        if value.content_type not in ('text/plain', 'application/json', 'text/markdown'):
            raise serializers.ValidationError('Unsupported content type.')
        return value


class SystemOperationStatusQuerySerializer(StrictSerializer):
    operation = serializers.ChoiceField(choices=['demo-reboot'])


__all__ = [
    'EchoSerializer',
    'EmptySerializer',
    'LoginSerializer',
    'ModelComparisonQuerySerializer',
    'SearchQuerySerializer',
    'SecurityInspectionSerializer',
    'SystemOperationStatusQuerySerializer',
    'UploadSerializer',
    'VmAssociationContextQuerySerializer',
]
