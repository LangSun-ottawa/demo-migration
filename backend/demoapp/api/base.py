from collections.abc import Mapping

from rest_framework import serializers
from rest_framework.exceptions import ParseError, ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.schemas.openapi import AutoSchema
from rest_framework.views import APIView

from demoapp.definitions.fdc_http import ERROR_CODE, HTTP_STATUS_CODE
from demoapp.fdc_frame.response import FdcJsonResponse


class StrictSerializer(serializers.Serializer):
    """Serializer base that keeps the legacy contract's unknown-field rejection."""

    def to_internal_value(self, data):
        if isinstance(data, Mapping) or hasattr(data, 'keys'):
            unknown = sorted(set(data.keys()) - set(self.fields.keys()))
            if unknown:
                raise ValidationError(
                    {name: ['Unexpected field.'] for name in unknown}
                )
        return super().to_internal_value(data)


class EmptySerializer(StrictSerializer):
    """Explicit contract for handlers that accept no input."""


class ContractAutoSchema(AutoSchema):
    """Teach DRF's OpenAPI generator about method-scoped input serializers."""

    def get_serializer(self, path, method):
        serializer_class = self.view.get_input_serializer_class(method.lower())
        return serializer_class(context={'request': getattr(self.view, 'request', None)})

    def get_response_serializer(self, path, method):
        # Responses retain the legacy FDC envelope and are not represented by
        # the request serializer.
        return None

    def get_operation_id(self, path, method):
        view_name = self.view.__class__.__name__
        if view_name.endswith('View'):
            view_name = view_name[:-4]
        return f'{method.lower()}{view_name}'

    def get_responses(self, path, method):
        return {
            str(status): {'description': description}
            for status, description in self.view.get_response_descriptions(
                method.lower()
            ).items()
        }

    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        if self.view.get_input_source(method.lower()) != 'query':
            return operation

        serializer = self.get_serializer(path, method)
        for name, field in serializer.fields.items():
            parameter = {
                'name': name,
                'in': 'query',
                'required': field.required,
                'schema': self.map_field(field),
            }
            if field.help_text:
                parameter['description'] = str(field.help_text)
            operation['parameters'].append(parameter)
        return operation


def _flatten_validation_errors(detail, prefix=''):
    if isinstance(detail, dict):
        messages = []
        for key, value in detail.items():
            path = f'{prefix}.{key}' if prefix else str(key)
            messages.extend(_flatten_validation_errors(value, path))
        return messages
    if isinstance(detail, list):
        messages = []
        for value in detail:
            messages.extend(_flatten_validation_errors(value, prefix))
        return messages
    return [f'{prefix}: {detail}' if prefix else str(detail)]


class ContractAPIView(APIView):
    """
    DRF APIView with a method-scoped input contract.

    DRF keeps ownership of ``dispatch`` and request parsing. Validation runs in
    ``initial()``, after DRF has created its Request object and before the HTTP
    method handler is selected. Handlers consume ``request.validated_data``.
    """

    serializer_classes = {}
    input_sources = {}
    response_statuses = {}
    parser_classes = [JSONParser]
    schema = ContractAutoSchema()

    def get_input_serializer_class(self, method=None):
        method = method or self.request.method.lower()
        return self.serializer_classes.get(method, EmptySerializer)

    def get_input_source(self, method=None):
        method = method or self.request.method.lower()
        return self.input_sources.get(method, 'query' if method in ('get', 'head') else 'body')

    def get_response_descriptions(self, method=None):
        method = method or self.request.method.lower()
        return self.response_statuses.get(
            method,
            {
                200: 'Legacy-compatible {status, result, error} envelope.',
                444: 'Serializer validation failed before the handler ran.',
            },
        )

    def get_serializer(self, *args, method=None, **kwargs):
        serializer_class = self.get_input_serializer_class(method)
        kwargs.setdefault('context', {'request': getattr(self, 'request', None)})
        return serializer_class(*args, **kwargs)

    def initial(self, request, *args, **kwargs):
        self._trace(request, 'dispatch', f'DRF APIView.dispatch initialized {type(self).__name__}')
        super().initial(request, *args, **kwargs)

        source = self.get_input_source()
        serializer_class = self.get_input_serializer_class()
        if source == 'body' and request.query_params:
            raise ValidationError({'query': ['Unexpected query parameters.']})
        if serializer_class is EmptySerializer:
            # Django's test client and some browsers attach a content type to an
            # empty POST. Do not invoke a parser unless input actually exists.
            django_request = request._request
            if django_request.POST or django_request.FILES:
                raw_input = request.data
            elif (
                int(django_request.META.get('CONTENT_LENGTH') or 0) > 0
                and request.content_type == 'application/json'
            ):
                raw_input = request.data
            else:
                raw_input = {}
        else:
            raw_input = request.query_params if source == 'query' else request.data
        serializer = self.get_serializer(data=raw_input)
        serializer.is_valid(raise_exception=True)
        request.validated_data = dict(serializer.validated_data)
        self._trace(
            request,
            'validation',
            f'{type(serializer).__name__} accepted {source} input',
        )

    def handle_exception(self, exc):
        if isinstance(exc, (ValidationError, ParseError)):
            self._trace(
                self.request,
                'validation',
                f'{self.get_input_serializer_class().__name__} rejected the request',
            )
            details = getattr(exc, 'detail', str(exc))
            return FdcJsonResponse(
                False,
                message='Request validation failed.',
                errors=[
                    {'message': message, 'code': ERROR_CODE.VALIDATION.value}
                    for message in _flatten_validation_errors(details)
                ],
                result=self.request_context(self.request),
                http_code=HTTP_STATUS_CODE.VALIDATION_ERROR.value,
            )
        return super().handle_exception(exc)

    def contract_metadata(self, request):
        serializer_class = self.get_input_serializer_class(request.method.lower())
        serializer = serializer_class()
        return {
            'view_class': type(self).__name__,
            'serializer_class': serializer_class.__name__,
            'http_method': request.method,
            'input_source': self.get_input_source(request.method.lower()),
            'fields': list(serializer.fields.keys()),
        }

    def request_context(self, request):
        return {
            'contract': self.contract_metadata(request),
            'trace': request.fdc_trace,
        }

    def _trace(self, request, stage, detail):
        if not hasattr(request, 'fdc_trace'):
            request.fdc_trace = []
        request.fdc_trace.append({'stage': stage, 'detail': detail})
