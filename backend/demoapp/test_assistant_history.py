import json
from datetime import timedelta
from io import StringIO
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from demoapp.api.permissions import FEATURE_DEMO_SETUP, FeaturePrivilege, feature_group_name
from demoapp.models import AssistantConversation, AssistantTurn, AssistantToolCall


@override_settings(ASSISTANT_HISTORY_TOKEN='test-history-service')
class AssistantHistoryTests(TestCase):
    base = '/api/demo/secure/assistant/'

    def setUp(self):
        self.user = get_user_model().objects.create_user('history-owner', password='test-password')
        self.other = get_user_model().objects.create_superuser('other-owner', 'other@example.com', 'test-password')
        group, _ = Group.objects.get_or_create(name=feature_group_name(FEATURE_DEMO_SETUP, FeaturePrivilege.READONLY))
        self.user.groups.add(group)
        self.client.force_login(self.user)

    def post(self, path, data, credential=True):
        headers = {'HTTP_X_ASSISTANT_HISTORY_TOKEN': 'test-history-service'} if credential else {}
        return self.client.post(self.base + 'internal/' + path, data=json.dumps(data),
            content_type='application/json', **headers)

    def start(self, conversation_id=None):
        run = str(uuid4())
        response = self.post('turns', {'run_id': run, 'request_id': str(uuid4()),
            'question': 'Create my profile', 'conversation_id': conversation_id})
        self.assertEqual(response.status_code, 200, response.content)
        return run, response.json()['result']

    def finish(self, run):
        response = self.post(f'turns/{run}/finish', {'assistant_text': 'Created profile 42', 'status': 'completed'})
        self.assertEqual(response.status_code, 200, response.content)

    def test_reload_and_next_turn_include_authoritative_tools_not_only_prose(self):
        run, created = self.start()
        call = {'call_id': 'pi-call-1', 'name': 'create_admin_profile'}
        args = {'name': 'Ops', 'access_level': 'readonly'}
        record = {'resource': 'profiles', 'record': {'id': 42, **args}}
        for data in [
            {**call, 'phase': 'started', 'arguments': args},
            {**call, 'phase': 'finished', 'result': {'ok': True, 'result': {'created_record': record, 'profiles': [args]}}},
        ]:
            response = self.post(f'turns/{run}/tools', data)
            self.assertEqual(response.status_code, 200, response.content)
        self.finish(run)
        restored = self.client.get(self.base + 'conversations/latest').json()['result']
        self.assertEqual(restored['conversation_id'], created['conversation_id'])
        tool = restored['turns'][0]['tools'][0]
        self.assertEqual(tool['arguments'], args)
        self.assertEqual(tool['status'], 'succeeded')
        self.assertEqual(tool['result']['result'], {'created_record': record})
        _, resumed = self.start(created['conversation_id'])
        self.assertEqual(resumed['history'], restored['turns'])
        self.assertNotIn('sessionid', json.dumps(resumed))

    def test_ownership_and_service_credential_even_for_superusers(self):
        run, created = self.start()
        self.finish(run)
        denied = self.post('turns', {'run_id': str(uuid4()), 'request_id': str(uuid4()), 'question': 'Forged'}, False)
        self.assertEqual(denied.status_code, 403)
        self.client.force_login(self.other)
        detail = self.client.get(self.base + 'conversations/' + created['conversation_id'])
        self.assertEqual(detail.status_code, 404)
        self.assertIsNone(self.client.get(self.base + 'conversations/latest').json()['result']['conversation_id'])
        denied = self.post('turns', {'run_id': str(uuid4()), 'request_id': str(uuid4()),
            'question': 'Stolen', 'conversation_id': created['conversation_id']})
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(self.post(f'turns/{run}/finish', {'assistant_text': 'Forged', 'status': 'failed'}).status_code, 404)

    def test_expired_session_and_expired_conversation_are_denied(self):
        _, created = self.start()
        AssistantConversation.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(self.base + 'conversations/' + created['conversation_id']).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.base + 'conversations/latest').status_code, 401)
        self.assertEqual(self.post('turns', {'run_id': str(uuid4()), 'request_id': str(uuid4()), 'question': 'Hi'}).status_code, 401)

    def test_active_lease_duplicate_tools_and_immutable_results(self):
        run, created = self.start()
        data = {'conversation_id': created['conversation_id'], 'run_id': str(uuid4()),
            'request_id': str(uuid4()), 'question': 'Concurrent turn'}
        self.assertEqual(self.post('turns', data).status_code, 409)
        call = {'call_id': 'one', 'name': 'query_setup_state', 'phase': 'started'}
        self.assertEqual(self.post(f'turns/{run}/tools', call).status_code, 200)
        self.assertEqual(self.post(f'turns/{run}/tools', call).status_code, 409)
        call.update(phase='finished', result={'ok': False, 'error': {'code': 'django_forbidden'}})
        self.assertEqual(self.post(f'turns/{run}/tools', call).status_code, 200)
        self.assertEqual(self.post(f'turns/{run}/tools', call).status_code, 409)
        self.assertEqual(AssistantToolCall.objects.get().status, 'failed')
        AssistantConversation.objects.update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.post('turns', data).status_code, 200)
        self.assertEqual(AssistantTurn.objects.get(run_id=run).status, 'interrupted')

    def test_context_limits_and_retention_cleanup(self):
        run, created = self.start()
        turn = AssistantTurn.objects.get(run_id=run)
        AssistantToolCall.objects.create(turn=turn, call_id='large', name='query_setup_state',
            result={'ok': True, 'result': {'profiles': ['x' * 9000]}}, status='succeeded')
        self.finish(run)
        for index in range(12):
            AssistantTurn.objects.create(conversation=turn.conversation, run_id=uuid4(), request_id=uuid4(),
                question=str(index), assistant_text='x' * 100, status='completed')
        latest = self.client.get(self.base + 'conversations/latest').json()['result']
        self.assertEqual(len(latest['turns']), 10)
        self.assertLess(len(json.dumps(latest)), 64000)
        AssistantTurn.objects.exclude(id=turn.id).delete()
        tool = self.client.get(self.base + 'conversations/latest').json()['result']['turns'][0]['tools'][0]
        self.assertTrue(tool['result']['result']['history_truncated'])
        AssistantConversation.objects.update(expires_at=timezone.now() - timedelta(days=1))
        call_command('purge_assistant_history', stdout=StringIO())
        self.assertFalse(AssistantTurn.objects.exists())
        self.assertFalse(AssistantToolCall.objects.exists())

    def test_internal_writes_still_require_csrf(self):
        from django.test import Client
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.user)
        response = browser.post(self.base + 'internal/turns', data=json.dumps({
            'run_id': str(uuid4()), 'request_id': str(uuid4()), 'question': 'Hi'}),
            content_type='application/json', HTTP_X_ASSISTANT_HISTORY_TOKEN='test-history-service')
        self.assertEqual(response.status_code, 403)
