from uuid import uuid4
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase, TransactionTestCase
from demoapp.models import AdminProfile, CreateOperation


class CreateIdempotencyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('idempotent-user')
        self.user.groups.add(Group.objects.get(name='feature:demo_setup:readwrite'))
        self.client.force_login(self.user)
        self.key = str(uuid4())
        self.args = {'name': 'Retry profile', 'access_level': 'readonly'}

    def send(self, args=None):
        return self.client.post('/api/demo/secure/setup/profiles', args or self.args,
            content_type='application/json', HTTP_IDEMPOTENCY_KEY=self.key)

    def test_retry_after_lost_response_returns_exact_created_id(self):
        first = self.send()
        replay = self.send()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(first.json()['result']['created_record'], replay.json()['result']['created_record'])
        self.assertTrue(replay.json()['result']['operation_replayed'])
        self.assertEqual(AdminProfile.objects.filter(name='Retry profile').count(), 1)
        self.assertEqual(CreateOperation.objects.count(), 1)

    def test_key_cannot_be_reused_for_different_arguments(self):
        self.send()
        conflict = self.send({**self.args, 'access_level': 'readwrite'})
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(AdminProfile.objects.get(name='Retry profile').access_level, 'readonly')

    def test_replay_still_checks_current_permission_and_session(self):
        self.send()
        readonly, _ = Group.objects.get_or_create(name='feature:demo_setup:readonly')
        self.user.groups.set([readonly])
        self.assertEqual(self.send().status_code, 403)
        self.client.logout()
        self.assertEqual(self.send().status_code, 401)

    def test_validation_failure_does_not_reserve_key(self):
        self.assertEqual(self.send({'name': 'Retry profile', 'access_level': 'wrong'}).status_code, 444)
        self.assertFalse(CreateOperation.objects.exists())
        self.assertEqual(self.send().status_code, 200)

    def test_another_user_cannot_replay_my_operation(self):
        self.send()
        other = get_user_model().objects.create_user('other-writer')
        other.groups.add(Group.objects.get(name='feature:demo_setup:readwrite'))
        self.client.force_login(other)
        response = self.send()
        self.assertEqual(response.status_code, 444)  # Ordinary duplicate name, not a cached success for a foreign owner.
        self.assertNotIn('created_record', response.json().get('result', {}))
        self.assertFalse(CreateOperation.objects.filter(owner=other).exists())


class ConcurrentCreateTests(TransactionTestCase):
    def test_concurrent_retries_cannot_create_two_rows(self):
        from concurrent.futures import ThreadPoolExecutor
        from django.db import close_old_connections
        user = get_user_model().objects.create_user('concurrent-writer')
        group, _ = Group.objects.get_or_create(name='feature:demo_setup:readwrite')
        user.groups.add(group)
        browsers = [Client(), Client()]
        for browser in browsers:
            browser.force_login(user)
        key = str(uuid4())
        def send(browser):
            close_old_connections()
            try:
                response = browser.post('/api/demo/secure/setup/profiles',
                    {'name': 'Concurrent profile', 'access_level': 'readonly'},
                    content_type='application/json', HTTP_IDEMPOTENCY_KEY=key)
                return response.status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(send, browsers))
        self.assertTrue(all(status in (200, 409) for status in statuses), statuses)
        # Contention may reject both attempts; the caller then retries the same operation key.
        for _ in range(2):
            if 200 in statuses:
                break
            statuses.append(send(browsers[0]))
        self.assertIn(200, statuses)
        self.assertEqual(AdminProfile.objects.filter(name='Concurrent profile').count(), 1)
        self.assertEqual(CreateOperation.objects.filter(owner=user, key=key).count(), 1)
