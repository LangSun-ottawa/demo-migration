import time

from django.contrib.auth import authenticate
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.core.cache import cache
from rest_framework.parsers import MultiPartParser

from demoapp.api.base import ContractAPIView
from demoapp.api.serializers import (
    EchoSerializer,
    EmptySerializer,
    LoginSerializer,
    ModelComparisonQuerySerializer,
    SearchQuerySerializer,
    SecurityInspectionSerializer,
    SystemOperationStatusQuerySerializer,
    UploadSerializer,
    VmAssociationContextQuerySerializer,
)
from demoapp.definitions.fdc_http import ERROR_CODE, HTTP_STATUS_CODE
from demoapp.fdc_frame.response import FdcJsonResponse
from demoapp.models import DeviceRecord
from demoapp.sqlalchemy_models import search_audit_records

MOCK_RECORDS = [
    {'id': 101, 'name': 'Alpha Sensor', 'active': True, 'category': 'legacy'},
    {'id': 102, 'name': 'Beta Gateway', 'active': False, 'category': 'edge'},
    {'id': 103, 'name': 'Gamma Token', 'active': True, 'category': 'api'},
    {'id': 104, 'name': 'Delta Archive', 'active': True, 'category': 'legacy'},
]

SYSTEM_OPERATION_CACHE_PREFIX = 'demo-system-operation:'
SIMULATED_REBOOT_SECONDS = 8

VM_ASSOCIATIONS_BY_CATEGORY = {
    'legacy': [
        {
            'id': 'legacy-telemetry',
            'type': 'application',
            'name': 'Telemetry Agent',
            'status': 'associated',
        },
        {
            'id': 'legacy-powershell',
            'type': 'extension',
            'name': 'PowerShell Activity Profile',
            'status': 'review',
        },
    ],
    'edge': [
        {
            'id': 'edge-network',
            'type': 'extension',
            'name': 'Network Discovery Profile',
            'status': 'associated',
        },
        {
            'id': 'edge-syslog',
            'type': 'application',
            'name': 'Syslog Forwarder',
            'status': 'associated',
        },
    ],
    'report': [
        {
            'id': 'report-archive',
            'type': 'extension',
            'name': 'Archive Inspection Profile',
            'status': 'blocked',
        },
    ],
}


def build_operation_cache_key(operation: str) -> str:
    return f'{SYSTEM_OPERATION_CACHE_PREFIX}{operation}'


class EchoView(ContractAPIView):
    serializer_classes = {'post': EchoSerializer}

    def post(self, request):
        payload = request.validated_data
        result = {
            'sanitized_name': payload['name'].strip(),
            'submitted': payload,
            'summary': f"{payload['name'].strip()} is a {'currently active' if payload['active'] else 'currently inactive'} demo user.",
        }
        return FdcJsonResponse(True, message='JSON body validated successfully.', result=result)


class SearchView(ContractAPIView):
    serializer_classes = {'get': SearchQuerySerializer}

    def get(self, request):
        query = request.validated_data
        term = query['term'].strip().lower()
        limit = query.get('limit', 5)
        active = query.get('active')

        filtered = [
            record for record in MOCK_RECORDS
            if term in record['name'].lower()
            and (active is None or record['active'] is active)
        ][:limit]

        return FdcJsonResponse(
            True,
            message='Query string validated successfully.',
            result={'items': filtered, 'count': len(filtered)},
        )


class UploadView(ContractAPIView):
    serializer_classes = {'post': UploadSerializer}
    parser_classes = [MultiPartParser]

    def post(self, request):
        uploaded = request.validated_data['attachment']
        result = {
            'filename': uploaded.name,
            'content_type': uploaded.content_type,
            'size': uploaded.size,
        }
        return FdcJsonResponse(True, message='File metadata validated successfully.', result=result)


class TemporaryRedirectView(ContractAPIView):
    serializer_classes = {'post': EmptySerializer}
    response_statuses = {
        'post': {
            303: 'Temporary redirect expressed in the legacy response envelope.',
            444: 'Serializer validation failed before the handler ran.',
        }
    }

    def post(self, request):
        redirect = '/new/demo/form?banner=temp-redirect'
        return FdcJsonResponse(
            False,
            message='Temporary redirect requested by the API.',
            errors=[{'message': 'Follow the provided redirect.', 'code': ERROR_CODE.BUSINESS.value}],
            http_code=HTTP_STATUS_CODE.SEE_OTHER_REDIRECT.value,
            redirect=redirect,
        )


class ErrorRedirectView(ContractAPIView):
    serializer_classes = {'post': EmptySerializer}
    response_statuses = {
        'post': {
            338: 'Application error redirect expressed in the legacy response envelope.',
            444: 'Serializer validation failed before the handler ran.',
        }
    }

    def post(self, request):
        redirect = '/new/error?reason=redirected-from-api'
        return FdcJsonResponse(
            False,
            message='Redirecting to the Angular error page.',
            errors=[{'message': 'This demo endpoint intentionally redirects to an error page.', 'code': ERROR_CODE.BUSINESS.value}],
            http_code=HTTP_STATUS_CODE.REDIRECT.value,
            redirect=redirect,
        )


class RebootRedirectView(ContractAPIView):
    serializer_classes = {'post': EmptySerializer}
    response_statuses = {
        'post': {
            303: 'Transition-page redirect expressed in the legacy response envelope.',
            444: 'Serializer validation failed before the handler ran.',
        }
    }

    def post(self, request):
        operation = 'demo-reboot'
        cache.set(
            build_operation_cache_key(operation),
            {'ready_at': time.time() + SIMULATED_REBOOT_SECONDS},
            timeout=SIMULATED_REBOOT_SECONDS + 30,
        )
        redirect = f'/new/system/redirect?type=reboot&operation={operation}'
        return FdcJsonResponse(
            False,
            message='Simulated reboot requested by the API.',
            errors=[{'message': 'Opening the transition page.', 'code': ERROR_CODE.BUSINESS.value}],
            http_code=HTTP_STATUS_CODE.SEE_OTHER_REDIRECT.value,
            redirect=redirect,
        )


class SystemOperationStatusView(ContractAPIView):
    serializer_classes = {'get': SystemOperationStatusQuerySerializer}
    response_statuses = {
        'get': {
            200: 'The simulated operation is ready.',
            444: 'Serializer validation failed before the handler ran.',
            503: 'The simulated operation is still in progress.',
        }
    }

    def get(self, request):
        operation = request.validated_data['operation']
        cache_key = build_operation_cache_key(operation)
        state = cache.get(cache_key)

        if not state:
            return FdcJsonResponse(
                True,
                message='The simulated system operation is complete.',
                result={'operation': operation, 'ready': True},
            )

        remaining_seconds = state.get('ready_at', 0) - time.time()
        if remaining_seconds <= 0:
            cache.delete(cache_key)
            return FdcJsonResponse(
                True,
                message='The simulated system operation is complete.',
                result={'operation': operation, 'ready': True},
            )

        return FdcJsonResponse(
            False,
            message='The simulated reboot is still in progress.',
            errors=[{'message': 'Demo system is not back yet.', 'code': ERROR_CODE.BUSINESS.value}],
            http_code=HTTP_STATUS_CODE.SERVICE_UNAVAILABLE.value,
        )


def search_django_records(term):
    queryset = DeviceRecord.objects.filter(name__icontains=term).order_by('id')
    sql_template, bound_params = queryset.query.sql_with_params()
    return {
        'model': 'DeviceRecord(models.Model)',
        'database': 'db.sqlite3',
        'sql_template': sql_template,
        'bound_params': list(bound_params),
        'items': [
            {
                'id': record.id,
                'name': record.name,
                'category': record.category,
                'active': record.active,
            }
            for record in queryset
        ],
    }


def build_model_comparison(term):
    return {
        'search_term_preserved': term,
        'django_orm': search_django_records(term),
        'sqlalchemy': search_audit_records(term),
        'security_conclusion': (
            'The input is preserved as data. Both ORMs emit a SQL template plus '
            'separate bound parameters, so quotes are not treated as SQL syntax.'
        ),
    }


def build_vm_association_context(record):
    records = list(DeviceRecord.objects.order_by('id').values('id', 'name', 'category', 'active'))
    associations = VM_ASSOCIATIONS_BY_CATEGORY.get(record.category, [])
    warnings = []
    if not record.active:
        warnings.append('The selected VM is inactive, so association changes should be reviewed.')
    if any(item['status'] in ('review', 'blocked') for item in associations):
        warnings.append('One or more associations require operator attention.')

    return {
        'page': {
            'id': 'vm-association',
            'title': 'VM Association',
            'route': '/new/context-assistant',
            'source': 'Django ORM context API',
        },
        'selection': {
            'record_id': record.id,
            'name': record.name,
            'category': record.category,
            'active': record.active,
        },
        'records': records,
        'associations': associations,
        'warnings': warnings,
        'assistant_scope': [
            'Explain the selected VM state',
            'Summarize visible associations',
            'Highlight review or blocked items',
        ],
    }


class LoginView(ContractAPIView):
    serializer_classes = {'post': LoginSerializer}
    response_statuses = {
        'post': {
            200: 'The Django session was created.',
            401: 'The credentials were rejected.',
            444: 'Serializer validation failed before authentication ran.',
        }
    }

    def post(self, request):
        credentials = request.validated_data
        user = authenticate(
            request,
            username=credentials['username'],
            password=credentials['password'],
        )
        if user is None:
            self._trace(request, 'authentication', 'Django authenticate() rejected credentials')
            return FdcJsonResponse(
                False,
                message='Authentication failed.',
                errors=[
                    {
                        'message': 'Username or password is incorrect.',
                        'code': ERROR_CODE.VALIDATION.value,
                    }
                ],
                result=self.request_context(request),
                http_code=HTTP_STATUS_CODE.UNAUTHORIZED.value,
            )

        django_login(request, user)
        self._trace(request, 'authentication', 'Django login() persisted the user in the session')
        return FdcJsonResponse(
            True,
            message='Session login succeeded.',
            result={
                'authenticated': True,
                'username': user.username,
                **self.request_context(request),
            },
        )


class LogoutView(ContractAPIView):
    serializer_classes = {'post': EmptySerializer}

    def post(self, request):
        username = request.user.username if request.user.is_authenticated else None
        django_logout(request)
        self._trace(request, 'authentication', 'Django logout() flushed the session')
        return FdcJsonResponse(
            True,
            message='Session logout succeeded.',
            result={
                'authenticated': False,
                'username': username,
                **self.request_context(request),
            },
        )


class SessionView(ContractAPIView):
    serializer_classes = {'get': EmptySerializer}

    def get(self, request):
        return FdcJsonResponse(
            True,
            message='Django session state resolved.',
            result={
                'authenticated': request.user.is_authenticated,
                'username': request.user.username if request.user.is_authenticated else None,
                **self.request_context(request),
            },
        )


class ContractCatalogView(ContractAPIView):
    serializer_classes = {'get': EmptySerializer}

    def get(self, request):
        return FdcJsonResponse(
            True,
            message='Each APIView owns a method-scoped DRF Serializer.',
            result={
                'contracts': [
                    {
                        'view_class': 'LoginView',
                        'serializer_class': 'LoginSerializer',
                        'method': 'POST',
                        'fields': ['username: strict identifier', 'password: bounded string'],
                    },
                    {
                        'view_class': 'SecurityInspectionView',
                        'serializer_class': 'SecurityInspectionSerializer',
                        'method': 'POST',
                        'fields': [
                            'display_name: trim + HTML escape',
                            'lookup_term: trim + parameter binding',
                            'safe_identifier: regex allowlist',
                        ],
                    },
                    {
                        'view_class': 'ModelComparisonView',
                        'serializer_class': 'ModelComparisonQuerySerializer',
                        'method': 'GET',
                        'fields': ['term: typed query string'],
                    },
                ],
                'models': [
                    {
                        'class': 'DeviceRecord',
                        'base': 'django.db.models.Model',
                        'session': 'Django connection + QuerySet',
                    },
                    {
                        'class': 'AuditRecord',
                        'base': 'sqlalchemy.orm.DeclarativeBase',
                        'session': 'SQLAlchemy Engine + Session',
                    },
                ],
                **self.request_context(request),
            },
        )


class VmAssociationContextView(ContractAPIView):
    serializer_classes = {'get': VmAssociationContextQuerySerializer}

    def get(self, request):
        record_id = request.validated_data['record_id']
        record = DeviceRecord.objects.filter(id=record_id).first()
        if record is None:
            return FdcJsonResponse(
                False,
                message='The selected VM record does not exist.',
                errors=[
                    {
                        'message': f'No DeviceRecord exists for id {record_id}.',
                        'code': ERROR_CODE.BUSINESS.value,
                    }
                ],
                http_code=HTTP_STATUS_CODE.BUSINESS_ERROR.value,
            )

        self._trace(request, 'context', 'Django ORM assembled canonical VM Association context')
        return FdcJsonResponse(
            True,
            message='VM Association page context loaded.',
            result={
                **build_vm_association_context(record),
                **self.request_context(request),
            },
        )


class SecurityInspectionView(ContractAPIView):
    serializer_classes = {'post': SecurityInspectionSerializer}

    def post(self, request):
        payload = request.validated_data
        self._trace(request, 'handler', 'Handler received only DRF serializer.validated_data')
        return FdcJsonResponse(
            True,
            message='Input normalization and injection defenses completed.',
            result={
                'validated_payload': payload,
                'processing': [
                    'display_name was trimmed and HTML-escaped',
                    'safe_identifier passed a strict allowlist',
                    'lookup_term remained data and was sent as a bound SQL parameter',
                ],
                'model_comparison': build_model_comparison(payload['lookup_term']),
                **self.request_context(request),
            },
        )


class ModelComparisonView(ContractAPIView):
    serializer_classes = {'get': ModelComparisonQuerySerializer}

    def get(self, request):
        term = request.validated_data['term']
        self._trace(request, 'handler', 'Both ORM adapters received the validated term')
        return FdcJsonResponse(
            True,
            message='Django ORM and SQLAlchemy queries completed.',
            result={
                **build_model_comparison(term),
                **self.request_context(request),
            },
        )
