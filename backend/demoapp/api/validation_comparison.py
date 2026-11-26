import json
from collections.abc import Mapping
from typing import Annotated

from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from rest_framework import serializers, status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


def build_echo_result(payload: dict, validator: str) -> dict:
    """Shared business logic so only parsing and validation differ."""
    return {
        'validator': validator,
        'submitted': payload,
        'summary': (
            f"{payload['name']} is "
            f"{'active' if payload['active'] else 'inactive'} and has "
            f"{len(payload['tags'])} tag(s)."
        ),
    }


def success_payload(result: dict) -> dict:
    return {
        'status': {
            'return_code': 1,
            'message': 'Payload validated successfully.',
        },
        'result': result,
    }


class StrictSerializer(serializers.Serializer):
    """DRF ignores unknown input fields by default; this preserves the demo contract."""

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown_fields = set(data) - set(self.fields)
            if unknown_fields:
                raise serializers.ValidationError(
                    {
                        field: ['Unexpected field.']
                        for field in sorted(unknown_fields)
                    }
                )
        return super().to_internal_value(data)


class DrfMetadataSerializer(StrictSerializer):
    source = serializers.CharField(
        allow_blank=False,
        max_length=30,
        trim_whitespace=True,
    )


class DrfEchoSerializer(StrictSerializer):
    name = serializers.CharField(
        allow_blank=False,
        max_length=60,
        trim_whitespace=True,
    )
    age = serializers.IntegerField(min_value=18, max_value=99)
    active = serializers.BooleanField()
    note = serializers.CharField(required=False, allow_blank=True, max_length=200)
    metadata = DrfMetadataSerializer()
    tags = serializers.ListField(
        child=serializers.CharField(allow_blank=False, max_length=20),
    )


class DrfEchoView(APIView):
    """Full DRF lifecycle: parser, serializer, exception handler, and renderer."""

    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]

    def post(self, request):
        serializer = DrfEchoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = build_echo_result(serializer.validated_data, 'drf')
        return Response(success_payload(result), status=status.HTTP_200_OK)


class PydanticMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    source: Annotated[str, Field(min_length=1, max_length=30)]


class PydanticEchoPayload(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=60)]
    age: Annotated[int, Field(ge=18, le=99)]
    active: bool
    note: Annotated[str, Field(max_length=200)] | None = None
    metadata: PydanticMetadata
    tags: list[Annotated[str, Field(min_length=1, max_length=20)]]


@method_decorator(csrf_exempt, name='dispatch')
class PydanticEchoView(View):
    """Django lifecycle with manual media-type, JSON, validation, and response adapters."""

    request_model = PydanticEchoPayload

    def post(self, request):
        if request.content_type != 'application/json':
            return JsonResponse(
                {
                    'detail': (
                        'Unsupported media type. Expected application/json.'
                    )
                },
                status=415,
            )

        try:
            raw_payload = json.loads(request.body.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return JsonResponse({'detail': 'Malformed JSON.'}, status=400)

        try:
            payload = self.request_model.model_validate(raw_payload)
        except ValidationError as exc:
            return JsonResponse(
                {'errors': exc.errors(include_url=False)},
                status=422,
            )

        result = build_echo_result(payload.model_dump(), 'pydantic')
        return JsonResponse(success_payload(result), status=200)
