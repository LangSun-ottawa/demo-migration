import json

from django.http import QueryDict
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views import View

from demoapp.definitions.fdc_http import ERROR_CODE, HTTP_STATUS_CODE
from demoapp.fdc_frame.fdc_type import (
    FdcBool,
    FdcInt,
    FdcStr,
    RequestValidationError,
    SchemaDefinitionError,
)
from demoapp.fdc_frame.response import FdcJsonResponse


@method_decorator(csrf_exempt, name='dispatch')
class FdcView(View):
    """
    Minimal request validator inspired by the legacy Django API layer.
    Views declare `param_schemas`, and typed request data is exposed on `request.fdc`.
    """

    param_schemas = {}
    schema_name = 'NO_PARAMS'

    def dispatch(self, request, *args, **kwargs):
        self._trace(request, 'dispatch', f'{type(self).__name__}.dispatch')
        try:
            request.fdc = self.validate_request(request)
            self._trace(request, 'validation', f'{self.schema_name} accepted the request')
        except RequestValidationError as exc:
            self._trace(request, 'validation', f'{self.schema_name} rejected the request')
            return FdcJsonResponse(
                False,
                errors=[{'message': str(exc), 'code': ERROR_CODE.VALIDATION.value}],
                http_code=HTTP_STATUS_CODE.VALIDATION_ERROR.value,
                result={'trace': request.fdc_trace, 'contract': self.contract_metadata(request)},
            )
        except SchemaDefinitionError as exc:
            self._trace(request, 'schema', f'{self.schema_name} is invalid')
            return FdcJsonResponse(
                False,
                errors=[{'message': str(exc), 'code': ERROR_CODE.SYSTEM.value}],
                http_code=HTTP_STATUS_CODE.SYSTEM_ERROR.value,
                result={'trace': request.fdc_trace, 'contract': self.contract_metadata(request)},
            )
        except Exception:
            self._trace(request, 'validation', 'Unhandled validation error')
            return FdcJsonResponse(
                False,
                errors=[{'message': 'Unhandled request validation error.', 'code': ERROR_CODE.SYSTEM.value}],
                http_code=HTTP_STATUS_CODE.SYSTEM_ERROR.value,
                result={'trace': request.fdc_trace, 'contract': self.contract_metadata(request)},
            )
        return super().dispatch(request, *args, **kwargs)

    def contract_metadata(self, request):
        method = request.method.lower()
        method_schema = self.param_schemas.get(method, {})
        return {
            'view_class': type(self).__name__,
            'schema_name': self.schema_name,
            'http_method': request.method,
            'schema_modes': list(method_schema.keys()),
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

    def validate_request(self, request):
        method = request.method.lower()
        if method not in self.param_schemas:
            if request.GET or request.POST or request.FILES or self._has_raw_body(request):
                raise RequestValidationError('Unexpected request data for this endpoint.')
            return {'query_string': {}, 'raw_post': None, 'files': {}}

        schema = self.param_schemas[method]
        validated = {'query_string': {}, 'raw_post': None, 'files': {}}

        if 'query_string' in schema:
            validated['query_string'] = self._validate_mapping(request.GET, schema['query_string'])
        elif request.GET:
            raise RequestValidationError('Unexpected query string parameters.')

        if 'raw_post' in schema:
            if not self._has_raw_body(request):
                raise RequestValidationError('JSON request body is required.')
            try:
                parsed_body = json.loads(request.body.decode('utf-8'))
            except json.JSONDecodeError as exc:
                raise RequestValidationError(f'JSON body is invalid: {exc.msg}.') from exc
            validated['raw_post'] = self._validate_value(parsed_body, schema['raw_post'], 'body')
        elif self._has_raw_body(request):
            raise RequestValidationError('Unexpected JSON request body.')

        if 'files' in schema:
            validated['files'] = self._validate_files(request.FILES, schema['files'])
        elif request.FILES:
            raise RequestValidationError('Unexpected uploaded files.')

        return validated

    def _validate_mapping(self, data, schema):
        if not isinstance(schema, dict):
            raise SchemaDefinitionError('Object schema must be a dictionary.')
        if isinstance(data, QueryDict):
            source = {key: data.get(key) for key in data.keys()}
        else:
            source = data
        if not isinstance(source, dict):
            raise RequestValidationError('Expected an object.')

        result = {}
        for raw_key, child_schema in schema.items():
            optional = raw_key.endswith('?')
            key = raw_key[:-1] if optional else raw_key
            if key not in source:
                if optional:
                    continue
                raise RequestValidationError(f'{key} is required.')
            result[key] = self._validate_value(source[key], child_schema, key)

        allowed_keys = {raw_key[:-1] if raw_key.endswith('?') else raw_key for raw_key in schema.keys()}
        for key in source.keys():
            if key not in allowed_keys:
                raise RequestValidationError(f'Unexpected key: {key}.')
        return result

    def _validate_value(self, value, schema, context):
        if isinstance(schema, (FdcStr, FdcInt, FdcBool)):
            return schema.validate(self._coerce_scalar(value, schema))
        if isinstance(schema, dict):
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError as exc:
                    raise RequestValidationError(f'{context} must be a JSON object.') from exc
            return self._validate_mapping(value, schema)
        if isinstance(schema, list):
            if len(schema) != 1:
                raise SchemaDefinitionError('List schema must contain exactly one child schema.')
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError as exc:
                    raise RequestValidationError(f'{context} must be a JSON array.') from exc
            if not isinstance(value, list):
                raise RequestValidationError(f'{context} must be an array.')
            return [self._validate_value(item, schema[0], f'{context}[{index}]') for index, item in enumerate(value)]
        raise SchemaDefinitionError(f'Unsupported schema for {context}.')

    def _coerce_scalar(self, value, schema):
        if isinstance(schema, FdcStr):
            return value
        if isinstance(schema, FdcInt):
            if isinstance(value, str):
                try:
                    return int(value)
                except ValueError as exc:
                    raise RequestValidationError(f'{schema._display_name()} must be an integer.') from exc
            return value
        if isinstance(schema, FdcBool):
            if isinstance(value, str):
                lowered = value.lower()
                if lowered in ('true', '1', 'yes'):
                    return True
                if lowered in ('false', '0', 'no'):
                    return False
                raise RequestValidationError(f'{schema._display_name()} must be true or false.')
            return value
        return value

    def _validate_files(self, files, schema):
        result = {}
        allowed_keys = set()
        for raw_key, file_schema in schema.items():
            optional = raw_key.endswith('?')
            key = raw_key[:-1] if optional else raw_key
            allowed_keys.add(key)
            uploaded = files.get(key)
            if uploaded is None:
                if optional:
                    continue
                raise RequestValidationError(f'{key} file is required.')
            if not isinstance(file_schema, dict):
                raise SchemaDefinitionError(f'File schema for {key} must be a dictionary.')
            name_validator = file_schema.get('name')
            maxsize = file_schema.get('maxsize')
            if not isinstance(name_validator, FdcStr) or not isinstance(maxsize, int):
                raise SchemaDefinitionError(f'File schema for {key} must declare name validator and integer maxsize.')
            name_validator.validate(uploaded.name)
            if uploaded.size > maxsize:
                raise RequestValidationError(f'{key} exceeds the maximum size of {maxsize} bytes.')
            content_types = file_schema.get('content_types')
            if content_types and uploaded.content_type not in content_types:
                raise RequestValidationError(f'{key} has an unsupported content type.')
            result[key] = uploaded

        for key in files.keys():
            if key not in allowed_keys:
                raise RequestValidationError(f'Unexpected file: {key}.')
        return result

    def _has_raw_body(self, request):
        content_type = request.content_type or ''
        if content_type.startswith('multipart/form-data'):
            return False
        return bool(request.body)
