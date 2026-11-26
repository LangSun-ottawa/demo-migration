from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase


class SetupDemoApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('setup-user', password='test-pass')

    def test_setup_requires_django_session(self):
        response = self.client.get('/api/demo/secure/setup')

        self.assertEqual(response.status_code, 401)

    def test_setup_requires_feature_group(self):
        self.client.force_login(self.user)

        response = self.client.get('/api/demo/secure/setup')

        self.assertEqual(response.status_code, 403)

    def test_authenticated_user_can_complete_four_step_demo(self):
        group = Group.objects.get(name='feature:demo_setup:readwrite')
        self.user.groups.add(group)
        self.client.force_login(self.user)

        profile = self.client.post(
            '/api/demo/secure/setup/profiles',
            {'name': 'Operations Admin', 'access_level': 'readwrite'},
            content_type='application/json',
        )
        profile_id = profile.json()['result']['profiles'][0]['id']
        user = self.client.post(
            '/api/demo/secure/setup/users',
            {'username': 'ops-admin', 'email': 'ops@example.com', 'profile_id': profile_id},
            content_type='application/json',
        )
        instance = self.client.post(
            '/api/demo/secure/setup/instances',
            {'name': 'Demo Instance', 'environment': 'test'},
            content_type='application/json',
        )
        instance_id = instance.json()['result']['instances'][0]['id']
        adapter = self.client.post(
            '/api/demo/secure/setup/adapters',
            {
                'name': 'Demo Adapter',
                'adapter_type': 'rest',
                'endpoint': 'https://example.invalid/api',
                'instance_id': instance_id,
            },
            content_type='application/json',
        )

        self.assertEqual(profile.status_code, 200)
        self.assertEqual(user.status_code, 200)
        self.assertEqual(instance.status_code, 200)
        self.assertEqual(adapter.status_code, 200)
        self.assertEqual(adapter.json()['result']['adapters'][0]['status'], 'configured')
        for response, resource in [(profile, 'profiles'), (user, 'users'), (instance, 'instances'), (adapter, 'adapters')]:
            result = response.json()['result']
            self.assertEqual(result['created_record']['resource'], resource)
            self.assertIn(result['created_record']['record'], result[resource])
        self.assertEqual(user.json()['result']['created_record']['record']['profile_id'], profile_id)
        self.assertEqual(adapter.json()['result']['created_record']['record']['instance_id'], instance_id)

    def test_authenticated_user_can_edit_and_delete_setup_records(self):
        group = Group.objects.get(name='feature:demo_setup:readwrite')
        self.user.groups.add(group)
        self.client.force_login(self.user)
        created = self.client.post(
            '/api/demo/secure/setup/profiles',
            {'name': 'Original Profile', 'access_level': 'readonly'},
            content_type='application/json',
        )
        profile_id = created.json()['result']['profiles'][0]['id']

        updated = self.client.put(
            f'/api/demo/secure/setup/profiles/{profile_id}',
            {'name': 'Updated Profile', 'access_level': 'readwrite'},
            content_type='application/json',
        )
        deleted = self.client.delete(f'/api/demo/secure/setup/profiles/{profile_id}')

        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()['result']['profiles'][0]['name'], 'Updated Profile')
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()['result']['profiles'], [])

    def test_cannot_delete_profile_still_used_by_admin_user(self):
        group = Group.objects.get(name='feature:demo_setup:readwrite')
        self.user.groups.add(group)
        self.client.force_login(self.user)
        profile = self.client.post(
            '/api/demo/secure/setup/profiles',
            {'name': 'Used Profile', 'access_level': 'readwrite'},
            content_type='application/json',
        )
        profile_id = profile.json()['result']['profiles'][0]['id']
        self.client.post(
            '/api/demo/secure/setup/users',
            {'username': 'linked-user', 'email': 'linked@example.com', 'profile_id': profile_id},
            content_type='application/json',
        )

        response = self.client.delete(f'/api/demo/secure/setup/profiles/{profile_id}')

        self.assertEqual(response.status_code, 409)
        self.assertIn('Delete dependent records first', response.json()['error'][0]['message'])
