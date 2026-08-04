import os
import unittest
from unittest.mock import patch

from assistant_gateway.app import (
    AssistantRequest,
    PageState,
    compose_answer,
    stream_answer,
)
from assistant_gateway.config import AssistantSettings


SAMPLE_CONTEXT = {
    'page': {
        'id': 'vm-association',
        'title': 'VM Association',
        'source': 'Django ORM context API',
    },
    'selection': {
        'record_id': 1,
        'name': 'Alpha Django Sensor',
        'category': 'legacy',
        'active': True,
    },
    'associations': [
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
    'warnings': ['One or more associations require operator attention.'],
}


def make_request(question='Summarize the associations'):
    return AssistantRequest(
        question=question,
        page_state=PageState(
            route='/new/context-assistant',
            selected_record_id=1,
            active_panel='associations',
            visible_filter='all',
        ),
    )


class AssistantGatewayTests(unittest.IsolatedAsyncioTestCase):
    def test_compose_answer_uses_django_and_client_context(self):
        answer = compose_answer(make_request(), SAMPLE_CONTEXT)

        self.assertIn('Alpha Django Sensor', answer)
        self.assertIn('Telemetry Agent', answer)
        self.assertIn('associations panel', answer)

    async def test_stream_has_meta_delta_and_done_events(self):
        chunks = [
            chunk
            async for chunk in stream_answer(
                'request-123',
                make_request(),
                SAMPLE_CONTEXT,
                delay_seconds=0,
            )
        ]
        stream = ''.join(chunks)

        self.assertTrue(stream.startswith('event: meta'))
        self.assertIn('event: delta', stream)
        self.assertTrue(stream.endswith('event: done\ndata: {"request_id": "request-123"}\n\n'))


class AssistantSettingsTests(unittest.TestCase):
    def test_settings_read_backend_only_api_configuration(self):
        environment = {
            'ASSISTANT_PROVIDER': 'example-provider',
            'ASSISTANT_API_KEY': 'test-secret',
            'ASSISTANT_BASE_URL': 'https://api.example.test/v1',
            'ASSISTANT_MODEL': 'example-model',
            'DJANGO_BASE_URL': 'http://django.test:9000',
        }
        with patch.dict(os.environ, environment, clear=True):
            settings = AssistantSettings(_env_file=None)

        self.assertEqual(settings.assistant_provider, 'example-provider')
        self.assertEqual(settings.assistant_base_url, 'https://api.example.test/v1')
        self.assertEqual(settings.assistant_model, 'example-model')
        self.assertEqual(settings.django_base_url, 'http://django.test:9000')
        self.assertEqual(settings.require_api_key(), 'test-secret')
        self.assertNotIn('test-secret', repr(settings))

    def test_missing_api_key_fails_only_when_provider_requests_it(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = AssistantSettings(_env_file=None)

        with self.assertRaisesRegex(RuntimeError, 'ASSISTANT_API_KEY'):
            settings.require_api_key()


if __name__ == '__main__':
    unittest.main()
