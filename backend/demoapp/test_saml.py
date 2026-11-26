import time
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase, override_settings

from demoapp.models import SamlIdentity, SamlReplay
from demoapp.saml import provision


class SamlTests(TestCase):
    def test_session_metadata_reports_current_authority_without_granting_access(self):
        self.assertEqual(self.client.get('/api/demo/auth/session').json()['result']['setup_access'], 'none')
        user = provision('issuer', 'reader', {'groups': ['demo-readonly']})
        self.client.force_login(user)
        result = self.client.get('/api/demo/auth/session').json()['result']
        self.assertEqual(result['setup_access'], 'readonly')
        self.assertIn('saml_enabled', result)
        user.groups.clear()
        self.assertEqual(self.client.get('/api/demo/auth/session').json()['result']['setup_access'], 'none')
        self.assertEqual(self.client.get('/api/demo/secure/setup').status_code, 403)

    def test_disabled_and_unsolicited_rejected(self):
        with override_settings(SAML_ENABLED=False):
            self.assertEqual(self.client.get('/api/demo/auth/saml/login/').status_code, 503)
        with override_settings(SAML_ENABLED=True), patch('pathlib.Path.exists', return_value=True):
            self.assertEqual(self.client.post('/api/demo/auth/saml/acs/', {}).status_code, 400)

    def test_identity_is_stable_not_email_linked_and_groups_sync(self):
        local = get_user_model().objects.create_user('sso-reader', email='reader@example.invalid')
        user = provision('issuer', 'stable-subject', {'email': [local.email], 'groups': ['demo-readwrite', 'superuser']})
        self.assertNotEqual(user.pk, local.pk)
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertEqual(list(user.groups.values_list('name', flat=True)), ['feature:demo_setup:readwrite'])
        again = provision('issuer', 'stable-subject', {'groups': ['demo-readonly']})
        self.assertEqual(user.pk, again.pk)
        self.assertEqual(list(again.groups.values_list('name', flat=True)), ['feature:demo_setup:readonly'])
        provision('issuer', 'stable-subject', {'groups': ['unrecognized']})
        self.assertFalse(user.groups.exists())
        self.assertEqual(SamlIdentity.objects.count(), 1)
        self.assertNotEqual(provision('another-issuer', 'stable-subject', {}).pk, user.pk)

    def test_disabled_identity_rejected(self):
        user = provision('issuer', 'subject', {})
        user.is_active = False
        user.save()
        with self.assertRaises(ValueError):
            provision('issuer', 'subject', {'groups': ['demo-readwrite']})

    def test_sso_users_obey_business_permissions_and_csrf(self):
        reader = provision('issuer', 'reader', {'groups': ['demo-readonly']})
        writer = provision('issuer', 'writer', {'groups': ['demo-readwrite']})
        self.client.force_login(reader)
        self.assertEqual(self.client.get('/api/demo/secure/setup').status_code, 200)
        self.assertEqual(self.client.post('/api/demo/secure/setup/profiles', {'name': 'denied', 'access_level': 'readonly'}, content_type='application/json').status_code, 403)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(writer)
        self.assertEqual(strict.post('/api/demo/secure/setup/profiles', {'name': 'csrf', 'access_level': 'readonly'}, content_type='application/json').status_code, 403)

    def test_missing_response_and_expired_attempt_fail_closed(self):
        with override_settings(SAML_ENABLED=True), patch('pathlib.Path.exists', return_value=True):
            session = self.client.session
            session['saml_pending'] = {'id': 'test', 'started': time.time() - 301}
            session.save()
            self.assertEqual(self.client.post('/api/demo/auth/saml/acs/', {}).status_code, 400)

    @override_settings(SAML_ENABLED=True)
    def test_persistent_assertion_replay_guard_and_fixed_redirect(self):
        auth = MagicMock()
        auth.get_errors.return_value = []
        auth.is_authenticated.return_value = True
        auth.get_last_response_in_response_to.return_value = 'request-id'
        auth.get_nameid.return_value = 'subject'
        auth.get_last_assertion_id.return_value = 'same-assertion'
        auth.get_last_assertion_not_on_or_after.return_value = time.time() + 300
        auth.get_attributes.return_value = {'groups': ['demo-readonly']}
        with patch('pathlib.Path.exists', return_value=True), patch('demoapp.saml.toolkit', return_value=auth), patch('demoapp.saml.saml_settings', return_value={'idp': {'entityId': 'issuer'}}):
            for expected_status in [302, 400]:
                client = Client()
                session = client.session
                session['saml_pending'] = {'id': 'request-id', 'started': time.time()}
                session.save()
                response = client.post('/api/demo/auth/saml/acs/', {'RelayState': 'https://attacker.invalid'})
                self.assertEqual(response.status_code, expected_status)
                if expected_status == 302:
                    self.assertEqual(response.url, 'http://127.0.0.1:4200/setup')
        self.assertEqual(SamlReplay.objects.count(), 1)

    @override_settings(SAML_ENABLED=True)
    def test_malformed_response_returns_controlled_error(self):
        from demoapp.saml import acs
        from django.test import RequestFactory
        from onelogin.saml2.errors import OneLogin_Saml2_Error
        request = RequestFactory().post('/api/demo/auth/saml/acs/')
        request.session = {'saml_pending': {'id': 'request', 'started': time.time()}}
        auth = MagicMock()
        auth.process_response.side_effect = OneLogin_Saml2_Error('malformed')
        with patch('pathlib.Path.exists', return_value=True), patch('demoapp.saml.toolkit', return_value=auth):
            self.assertEqual(acs(request).status_code, 400)
