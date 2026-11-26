"""Real Gateway/Broker/Django integration; only the model's tool selection is scripted.

ASGI transports replace TCP, not authentication, permissions, views or the database.
Run with: python backend/manage.py test demoapp.test_assistant_authorization
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.asgi import get_asgi_application
from django.test import Client, TestCase, override_settings

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assistant_gateway.app import (
    app, get_assistant_provider, get_history_client, get_run_store, get_tool_broker,
)
from assistant_gateway.conversations import ConversationClient
from assistant_gateway.protocol import AgentEvent
from assistant_gateway.run_store import InMemoryAgentRunStore
from assistant_gateway.tools import DjangoApiClient, ToolBrokerService
from demoapp.models import (
    AdapterConfig, AdminProfile, AdminUserRecord, AssistantToolCall, ManagedInstance,
)


@override_settings(ALLOWED_HOSTS=['testserver'], ASSISTANT_HISTORY_TOKEN='authorization-test-service')
class AssistantAuthorizationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('broker-reader', password='test-password')
        self.readonly, _ = Group.objects.get_or_create(name='feature:demo_setup:readonly')
        self.readwrite = Group.objects.get(name='feature:demo_setup:readwrite')
        self.user.groups.add(self.readonly)
        self.profile = AdminProfile.objects.create(name='Existing profile', access_level='readwrite')
        self.instance = ManagedInstance.objects.create(name='Existing instance', environment='test')

    def counts(self):
        return tuple(model.objects.count() for model in (
            AdminProfile, AdminUserRecord, ManagedInstance, AdapterConfig))

    def login_cookie(self):
        browser = Client(enforce_csrf_checks=True)
        browser.get('/api/demo/auth/session')
        response = browser.post('/api/demo/auth/login',
            {'username': 'broker-reader', 'password': 'test-password'},
            content_type='application/json', HTTP_X_CSRFTOKEN=browser.cookies['csrftoken'].value)
        self.assertEqual(response.status_code, 200)
        return '; '.join(f'{key}={browser.cookies[key].value}' for key in ('sessionid', 'csrftoken'))

    def exercise(self, tool_name, args, *, downgrade=False, conversation_id=None, drop_committed_response=False):
        cookie = self.login_cookie()
        store = InMemoryAgentRunStore(30)
        history = ConversationClient('http://testserver', settings.ASSISTANT_HISTORY_TOKEN)
        broker = ToolBrokerService(store, DjangoApiClient('http://testserver'), history)
        real_client = httpx.AsyncClient
        django_app = get_asgi_application()
        django_responses, provider_results = [], []

        class DjangoTransport(httpx.ASGITransport):
            async def handle_async_request(transport, request):
                response = await super().handle_async_request(request)
                django_responses.append((request.url.path, response.status_code))
                if drop_committed_response and request.url.path.startswith('/api/demo/secure/setup/') and response.status_code == 200:
                    await response.aread()
                    raise httpx.ReadTimeout('Injected response loss AFTER Django committed the create.', request=request)
                if request.url.path.startswith('/api/demo/secure/setup/') and response.status_code == 403:
                    await response.aread()
                    self.assertEqual(response.json()['result']['contract']['permission'], {
                        'feature_key': 'demo_setup', 'required': 'readwrite', 'actual': 'readonly',
                    })  # Prove this is feature denial, not an accidental CSRF 403.
                return response

        def django_http_client(*positional, **kwargs):
            kwargs.setdefault('transport', DjangoTransport(app=django_app))
            return real_client(*positional, **kwargs)

        async def revoke_write():
            await sync_to_async(self.user.groups.set)([self.readonly])

        class ScriptedToolProvider:
            async def stream(provider, request):
                # Deliberately attempt the write regardless of privilege: no prompt-based protection.
                if downgrade:
                    await revoke_write()
                call_id = 'forced-model-call'
                yield AgentEvent(type='tool_start', data={'call_id': call_id, 'name': tool_name})
                async with real_client(transport=httpx.ASGITransport(app=app), base_url='http://gateway.test') as agent:
                    response = await agent.post(
                        f'/internal/agent-runs/{request.run_id}/tools/{tool_name}',
                        headers={'Authorization': f'Bearer {request.tool_broker.execution_token}'},
                        json={'call_id': call_id, 'args': args})
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                provider_results.append(result)  # The actual payload delivered back to the agent.
                yield AgentEvent(type='tool_result', data={
                    'call_id': call_id, 'name': tool_name, 'ok': result['ok'],
                    'summary': 'Completed' if result['ok'] else result['error']['message'],
                    'result': result['result'], 'error': result['error'],
                })
                yield AgentEvent(type='delta', data={'text': 'Completed' if result['ok'] else 'Django denied this operation.'})

        async def send():
            async with real_client(transport=httpx.ASGITransport(app=app), base_url='http://gateway.test') as browser:
                return await browser.post('/assistant/stream', headers={'Cookie': cookie}, json={
                    'question': 'Attempt this registered tool', 'conversation_id': conversation_id,
                    'page_state': {'route': '/new/setup'}})

        overrides = {
            get_run_store: lambda: store, get_history_client: lambda: history,
            get_tool_broker: lambda: broker, get_assistant_provider: lambda: ScriptedToolProvider(),
        }
        with patch.dict(app.dependency_overrides, overrides), patch('httpx.AsyncClient', side_effect=django_http_client):
            response = async_to_sync(send)()
        self.assertEqual(response.status_code, 200, response.text)
        events = []
        for block in response.text.strip().split('\n\n'):
            event, data = block.splitlines()
            events.append((event.removeprefix('event: '), json.loads(data.removeprefix('data: '))))
        self.assertTrue(any(kind == 'done' for kind, _ in events), response.text)
        self.assertFalse(any(kind == 'error' for kind, _ in events), response.text)
        self.assertEqual(len(provider_results), 1, response.text)
        meta = next(data for kind, data in events if kind == 'meta')
        self.assertFalse(async_to_sync(store.contains)(meta['run_id']))
        stored = AssistantToolCall.objects.get(turn__run_id=meta['run_id'], call_id='forced-model-call')
        self.assertEqual({k: v for k, v in stored.arguments.items() if k != 'operation_id'}, args)
        if tool_name.startswith('create_'):
            self.assertIn('operation_id', stored.arguments)
        self.assertEqual(stored.result, provider_results[0])
        return provider_results[0], events, django_responses, stored

    def assert_forbidden(self, result, events, responses, stored, path):
        self.assertIn((path, 403), responses)  # A real Django response, not a fabricated ToolResult.
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'django_forbidden')
        self.assertEqual(result['error']['status_code'], 403)
        self.assertIsNone(result['result'])
        self.assertEqual(stored.status, 'failed')
        tool_event = next(data for kind, data in events if kind == 'tool_result')
        self.assertFalse(tool_event['ok'])
        self.assertEqual(tool_event['error']['status_code'], 403)
        self.assertIsNone(tool_event['result'])  # No successful result/card for the UI.

    def test_readonly_agent_cannot_create_any_of_four_resources(self):
        cases = [
            ('create_admin_profile', 'profiles', {'name': 'Forbidden profile', 'access_level': 'readwrite'}),
            ('create_admin_user', 'users', {'username': 'forbidden-user', 'email': 'user@example.com', 'profile_id': self.profile.id}),
            ('create_instance', 'instances', {'name': 'Forbidden instance', 'environment': 'test'}),
            ('create_adapter', 'adapters', {'name': 'Forbidden adapter', 'adapter_type': 'rest',
                'endpoint': 'https://example.invalid/api', 'instance_id': self.instance.id}),
        ]
        before = self.counts()
        for name, resource, args in cases:
            with self.subTest(tool=name):
                result = self.exercise(name, args)
                self.assert_forbidden(*result, f'/api/demo/secure/setup/{resource}')
                self.assertEqual(self.counts(), before)

    def test_readonly_agent_can_query_setup(self):
        result, _, responses, stored = self.exercise('query_setup_state', {})
        self.assertTrue(result['ok'])
        self.assertIn(('/api/demo/secure/setup', 200), responses)
        self.assertEqual(stored.status, 'succeeded')

    def test_readwrite_same_agent_and_csrf_flow_can_create(self):
        self.user.groups.set([self.readwrite])
        result, _, responses, stored = self.exercise('create_admin_profile',
            {'name': 'Allowed profile', 'access_level': 'readonly'})
        self.assertTrue(result['ok'])
        self.assertIn(('/api/demo/secure/setup/profiles', 200), responses)
        self.assertEqual(stored.status, 'succeeded')
        record = result['result']['created_record']['record']
        self.assertEqual(AdminProfile.objects.get(name='Allowed profile').id, record['id'])

    def test_downgrade_after_run_start_is_reauthorized_by_django(self):
        self.user.groups.set([self.readwrite])
        before = self.counts()
        result = self.exercise('create_admin_profile',
            {'name': 'Revoked profile', 'access_level': 'readwrite'}, downgrade=True)
        self.assert_forbidden(*result, '/api/demo/secure/setup/profiles')
        self.assertEqual(self.counts(), before)

    def test_response_lost_after_commit_can_retry_new_run_without_duplicate(self):
        self.user.groups.set([self.readwrite])
        args = {'name': 'Uncertain commit profile', 'access_level': 'readonly'}
        first, _, _, first_call = self.exercise('create_admin_profile', args, drop_committed_response=True)
        self.assertFalse(first['ok'])
        self.assertEqual(first['error']['code'], 'django_unavailable')
        committed = AdminProfile.objects.get(name=args['name'])
        conversation_id = str(first_call.turn.conversation_id)
        retry, _, _, retry_call = self.exercise('create_admin_profile', args, conversation_id=conversation_id)
        self.assertTrue(retry['ok'])
        self.assertTrue(retry['result']['operation_replayed'])
        self.assertEqual(retry['result']['created_record']['record']['id'], committed.id)
        self.assertEqual(first_call.arguments['operation_id'], retry_call.arguments['operation_id'])
        self.assertNotEqual(first_call.turn.run_id, retry_call.turn.run_id)
        self.assertEqual(AdminProfile.objects.filter(name=args['name']).count(), 1)
