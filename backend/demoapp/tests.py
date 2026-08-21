from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase

from demoapp.api.permissions import (
    FEATURE_MODEL_COMPARISON,
    FEATURE_SECURITY_INSPECTION,
    FeaturePrivilege,
    feature_group_name,
)
from demoapp.definitions.fdc_http import ERROR_CODE, HTTP_STATUS_CODE, RETURN_CODE
from demoapp.api.views import build_operation_cache_key


class DemoApiTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_legacy_report_renders(self):
        response = self.client.get('/legacy/report/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Legacy server-rendered report')
        self.assertEqual(response.headers['X-Frame-Options'], 'SAMEORIGIN')

    def test_spa_shell_renders(self):
        response = self.client.get('/new/demo/form')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<app-root>', html=False)
        self.assertContains(response, '<base href="/new/">', html=False)
        content = response.content.decode('utf-8')
        self.assertLess(content.index('polyfills-'), content.index('main-'))

    def test_echo_success(self):
        payload = {
            'name': '  Demo User  ',
            'age': 29,
            'active': True,
            'metadata': {'source': 'legacy-demo'},
            'tags': ['alpha', 'beta'],
        }
        response = self.client.post('/api/demo/echo', data=payload, content_type='application/json')
        self.assertEqual(response.status_code, HTTP_STATUS_CODE.SUCCESS.value)
        data = response.json()
        self.assertEqual(data['status']['return_code'], RETURN_CODE.SUCCESS.value)
        self.assertEqual(data['result']['sanitized_name'], 'Demo User')

    def test_echo_validation_failure(self):
        payload = {
            'name': '',
            'age': 'abc',
            'active': True,
            'metadata': {'source': 'legacy-demo'},
            'tags': ['alpha'],
        }
        response = self.client.post('/api/demo/echo', data=payload, content_type='application/json')
        self.assertEqual(response.status_code, HTTP_STATUS_CODE.VALIDATION_ERROR.value)
        data = response.json()
        self.assertEqual(data['error'][0]['code'], ERROR_CODE.VALIDATION.value)

    def test_search_validation_failure(self):
        response = self.client.get('/api/demo/search', {'term': 'alpha', 'limit': 100})
        self.assertEqual(response.status_code, HTTP_STATUS_CODE.VALIDATION_ERROR.value)
        self.assertEqual(response.json()['error'][0]['code'], ERROR_CODE.VALIDATION.value)

    def test_valid_upload(self):
        uploaded = SimpleUploadedFile('notes.txt', b'hello world', content_type='text/plain')
        response = self.client.post('/api/demo/upload', {'attachment': uploaded})
        self.assertEqual(response.status_code, HTTP_STATUS_CODE.SUCCESS.value)
        self.assertEqual(response.json()['result']['filename'], 'notes.txt')

    def test_invalid_upload_name(self):
        uploaded = SimpleUploadedFile('notes.exe', b'nope', content_type='application/octet-stream')
        response = self.client.post('/api/demo/upload', {'attachment': uploaded})
        self.assertEqual(response.status_code, HTTP_STATUS_CODE.VALIDATION_ERROR.value)
        self.assertEqual(response.json()['error'][0]['code'], ERROR_CODE.VALIDATION.value)

    def test_temporary_redirect_endpoint(self):
        response = self.client.post('/api/demo/redirect/temp')
        self.assertEqual(response.status_code, HTTP_STATUS_CODE.SEE_OTHER_REDIRECT.value)
        self.assertEqual(response.json()['status']['redirect'], '/new/demo/form?banner=temp-redirect')

    def test_error_redirect_endpoint(self):
        response = self.client.post('/api/demo/redirect/error')
        self.assertEqual(response.status_code, HTTP_STATUS_CODE.REDIRECT.value)
        self.assertEqual(response.json()['status']['redirect'], '/new/error?reason=redirected-from-api')

    def test_reboot_redirect_endpoint(self):
        response = self.client.post('/api/demo/system/reboot')
        self.assertEqual(response.status_code, HTTP_STATUS_CODE.SEE_OTHER_REDIRECT.value)
        self.assertEqual(response.json()['status']['redirect'], '/new/system/redirect?type=reboot&operation=demo-reboot')

    def test_system_operation_status_transitions_to_ready(self):
        self.client.post('/api/demo/system/reboot')

        in_progress = self.client.get('/api/demo/system/status', {'operation': 'demo-reboot'})
        self.assertEqual(in_progress.status_code, HTTP_STATUS_CODE.SERVICE_UNAVAILABLE.value)

        cache.set(build_operation_cache_key('demo-reboot'), {'ready_at': 0}, timeout=30)
        ready = self.client.get('/api/demo/system/status', {'operation': 'demo-reboot'})
        self.assertEqual(ready.status_code, HTTP_STATUS_CODE.SUCCESS.value)
        self.assertTrue(ready.json()['result']['ready'])


class ArchitectureLabTests(TestCase):
    def setUp(self):
        self.client = Client()

    def login(self):
        return self.client.post(
            '/api/demo/auth/login',
            data={'username': 'demo', 'password': 'DemoPass123!'},
            content_type='application/json',
        )

    def test_feature_permission_rejects_anonymous_user_before_validation(self):
        response = self.client.get('/api/demo/secure/models', {'term': 'Alpha'})

        self.assertEqual(response.status_code, HTTP_STATUS_CODE.UNAUTHORIZED.value)
        data = response.json()
        self.assertEqual(data['result']['trace'][-1]['stage'], 'authentication')
        self.assertEqual(data['error'][0]['code'], ERROR_CODE.PERMISSION.value)
        self.assertNotIn('validation', [step['stage'] for step in data['result']['trace']])

    def test_feature_permission_denies_authenticated_user_without_grant(self):
        user = get_user_model().objects.create_user('no-grants', password='DemoPass123!')
        self.client.force_login(user)

        response = self.client.get('/api/demo/secure/models', {'term': 'Alpha'})

        self.assertEqual(response.status_code, HTTP_STATUS_CODE.FORBIDDEN.value)
        data = response.json()
        self.assertEqual(data['error'][0]['code'], ERROR_CODE.PERMISSION.value)
        permission = data['result']['contract']['permission']
        self.assertEqual(permission['feature_key'], FEATURE_MODEL_COMPARISON)
        self.assertEqual(permission['actual'], FeaturePrivilege.NONE.value)

    def test_readonly_feature_grant_allows_get_but_not_write(self):
        user = get_user_model().objects.create_user('readonly-user', password='DemoPass123!')
        model_group_name = feature_group_name(
            FEATURE_MODEL_COMPARISON,
            FeaturePrivilege.READONLY,
        )
        security_group_name = feature_group_name(
            FEATURE_SECURITY_INSPECTION,
            FeaturePrivilege.READONLY,
        )
        model_group, _ = Group.objects.get_or_create(name=model_group_name)
        security_group, _ = Group.objects.get_or_create(name=security_group_name)
        user.groups.add(model_group, security_group)
        self.client.force_login(user)

        read_response = self.client.get('/api/demo/secure/models', {'term': 'Alpha'})
        write_response = self.client.post(
            '/api/demo/secure/security/inspect',
            data={
                'display_name': 'Demo',
                'lookup_term': 'Alpha',
                'safe_identifier': 'report_2026',
            },
            content_type='application/json',
        )

        self.assertEqual(read_response.status_code, HTTP_STATUS_CODE.SUCCESS.value)
        self.assertEqual(write_response.status_code, HTTP_STATUS_CODE.FORBIDDEN.value)
        self.assertEqual(write_response.json()['error'][0]['code'], ERROR_CODE.PERMISSION.value)

    def test_login_uses_its_own_serializer_and_persists_session(self):
        response = self.login()

        self.assertEqual(response.status_code, HTTP_STATUS_CODE.SUCCESS.value)
        result = response.json()['result']
        self.assertTrue(result['authenticated'])
        self.assertEqual(result['contract']['view_class'], 'LoginView')
        self.assertEqual(result['contract']['serializer_class'], 'LoginSerializer')
        self.assertEqual(result['contract']['input_source'], 'body')

        session_response = self.client.get('/api/demo/auth/session')
        self.assertTrue(session_response.json()['result']['authenticated'])

    def test_login_serializer_rejects_injection_shaped_username(self):
        response = self.client.post(
            '/api/demo/auth/login',
            data={'username': "demo' OR 1=1 --", 'password': 'DemoPass123!'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, HTTP_STATUS_CODE.VALIDATION_ERROR.value)
        result = response.json()['result']
        self.assertEqual(result['contract']['serializer_class'], 'LoginSerializer')
        self.assertEqual(result['trace'][-1]['stage'], 'validation')

    def test_serializer_rejects_unknown_fields_before_handler(self):
        response = self.client.post(
            '/api/demo/auth/login',
            data={
                'username': 'demo',
                'password': 'DemoPass123!',
                'unexpected': 'value',
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, HTTP_STATUS_CODE.VALIDATION_ERROR.value)
        data = response.json()
        self.assertIn('unexpected: Unexpected field.', data['error'][0]['message'])
        self.assertNotIn('authentication', [step['stage'] for step in data['result']['trace'][1:]])

    def test_security_view_normalizes_escapes_and_binds_sql_input(self):
        self.login()
        injection_term = "' OR 1=1 --"
        response = self.client.post(
            '/api/demo/secure/security/inspect',
            data={
                'display_name': '  <script>alert("demo")</script>  ',
                'lookup_term': injection_term,
                'safe_identifier': 'report_2026',
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, HTTP_STATUS_CODE.SUCCESS.value)
        result = response.json()['result']
        self.assertEqual(
            result['validated_payload']['display_name'],
            '&lt;script&gt;alert(&quot;demo&quot;)&lt;/script&gt;',
        )
        self.assertEqual(result['model_comparison']['search_term_preserved'], injection_term)
        self.assertEqual(result['model_comparison']['django_orm']['items'], [])
        self.assertEqual(result['model_comparison']['sqlalchemy']['items'], [])
        self.assertIn(
            f'%{injection_term}%',
            result['model_comparison']['django_orm']['bound_params'],
        )
        self.assertIn(
            f'%{injection_term}%',
            result['model_comparison']['sqlalchemy']['bound_params'].values(),
        )

    def test_security_view_rejects_command_identifier_metacharacters(self):
        self.login()
        response = self.client.post(
            '/api/demo/secure/security/inspect',
            data={
                'display_name': 'Demo',
                'lookup_term': 'Alpha',
                'safe_identifier': 'report;rm-rf',
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, HTTP_STATUS_CODE.VALIDATION_ERROR.value)
        self.assertEqual(response.json()['error'][0]['code'], ERROR_CODE.VALIDATION.value)

    def test_model_comparison_exposes_bound_queries_from_both_orms(self):
        self.login()
        response = self.client.get('/api/demo/secure/models', {'term': 'Alpha'})

        self.assertEqual(response.status_code, HTTP_STATUS_CODE.SUCCESS.value)
        result = response.json()['result']
        self.assertEqual(
            result['contract']['serializer_class'],
            'ModelComparisonQuerySerializer',
        )
        self.assertEqual(result['contract']['input_source'], 'query')
        self.assertEqual(
            result['contract']['permission'],
            {
                'feature_key': FEATURE_MODEL_COMPARISON,
                'required': FeaturePrivilege.READONLY.value,
                'actual': FeaturePrivilege.READONLY.value,
            },
        )
        self.assertEqual(result['django_orm']['model'], 'DeviceRecord(models.Model)')
        self.assertEqual(result['sqlalchemy']['model'], 'AuditRecord(SqlAlchemyBase)')
        self.assertEqual(len(result['django_orm']['items']), 1)
        self.assertEqual(len(result['sqlalchemy']['items']), 1)

    def test_vm_association_context_is_schema_validated_and_orm_backed(self):
        self.login()
        response = self.client.get('/api/demo/secure/page-context', {'record_id': 1})

        self.assertEqual(response.status_code, HTTP_STATUS_CODE.SUCCESS.value)
        result = response.json()['result']
        self.assertEqual(
            result['contract']['serializer_class'],
            'VmAssociationContextQuerySerializer',
        )
        self.assertEqual(result['page']['id'], 'vm-association')
        self.assertEqual(result['selection']['record_id'], 1)
        self.assertGreaterEqual(len(result['records']), 3)
        self.assertEqual(result['trace'][-1]['stage'], 'context')

    def test_vm_association_context_rejects_invalid_record_id(self):
        self.login()
        response = self.client.get('/api/demo/secure/page-context', {'record_id': 'not-an-id'})

        self.assertEqual(response.status_code, HTTP_STATUS_CODE.VALIDATION_ERROR.value)
        self.assertEqual(response.json()['error'][0]['code'], ERROR_CODE.VALIDATION.value)

    def test_vm_association_context_requires_authentication(self):
        response = self.client.get('/api/demo/secure/page-context', {'record_id': 1})

        self.assertEqual(response.status_code, HTTP_STATUS_CODE.UNAUTHORIZED.value)
        self.assertEqual(response.json()['result']['trace'][-1]['stage'], 'authentication')

    def test_contract_catalog_lists_different_view_schemas_and_models(self):
        response = self.client.get('/api/demo/contracts')

        self.assertEqual(response.status_code, HTTP_STATUS_CODE.SUCCESS.value)
        result = response.json()['result']
        self.assertEqual(len(result['contracts']), 3)
        self.assertEqual(
            {model['base'] for model in result['models']},
            {'django.db.models.Model', 'sqlalchemy.orm.DeclarativeBase'},
        )

    def test_logout_flushes_authenticated_session(self):
        self.login()
        response = self.client.post('/api/demo/auth/logout')

        self.assertEqual(response.status_code, HTTP_STATUS_CODE.SUCCESS.value)
        session_response = self.client.get('/api/demo/auth/session')
        self.assertFalse(session_response.json()['result']['authenticated'])
