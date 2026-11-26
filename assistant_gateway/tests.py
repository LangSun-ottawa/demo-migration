import os
import unittest
from unittest.mock import patch

from assistant_gateway.app import stream_gateway_events
from assistant_gateway.config import AssistantSettings
from assistant_gateway.protocol import (
    AgentRunRequest,
    AssistantRequest,
    ChatTurn,
    PageState,
    SetupPageState,
    ToolBrokerDescriptor,
)
from assistant_gateway.providers import DeterministicAssistantProvider
from assistant_gateway.run_store import (
    InMemoryAgentRunStore,
    InvalidExecutionTokenError,
)
from assistant_gateway.tools import (
    CREATE_ADMIN_PROFILE,
    QUERY_SETUP_STATE,
    SETUP_TOOLS,
    QUERY_VM_CONTEXT,
    QueryVmContextArguments,
    ToolBrokerService,
)


SAMPLE_CONTEXT = {
    'page': {'source': 'Django ORM context API'},
    'selection': {
        'record_id': 1,
        'name': 'Alpha Django Sensor',
        'category': 'legacy',
        'active': True,
    },
    'associations': [
        {
            'id': 'legacy-powershell',
            'type': 'extension',
            'name': 'PowerShell Activity Profile',
            'status': 'review',
        },
    ],
    'warnings': ['One or more associations require operator attention.'],
}


class FakeDjangoClient:
    def __init__(self):
        self.seen_cookie = None

    async def query_vm_context(self, args: QueryVmContextArguments, cookie: str):
        from assistant_gateway.protocol import ToolResult

        self.seen_cookie = cookie
        result = dict(SAMPLE_CONTEXT)
        result['selection'] = {**SAMPLE_CONTEXT['selection'], 'record_id': args.record_id}
        return ToolResult(ok=True, name=QUERY_VM_CONTEXT, result=result)

    async def execute_setup_tool(self, tool_name, args, cookie):
        from assistant_gateway.protocol import ToolResult

        self.seen_cookie = cookie
        if tool_name == QUERY_SETUP_STATE:
            return ToolResult(ok=True, name=tool_name, result={'profiles': [], 'instances': []})
        return ToolResult(ok=True, name=tool_name, result={'created': args.model_dump()})


class ConnectedBrowserRequest:
    async def is_disconnected(self):
        return False


def make_browser_request(question='Which associations need review?'):
    return AssistantRequest(
        question=question,
        page_state=PageState(
            route='/new/context-assistant',
            selected_record_id=1,
            active_panel='associations',
            visible_filter='all',
        ),
    )


def make_agent_request(execution_token: str):
    payload = make_browser_request()
    return AgentRunRequest(
        **payload.model_dump(),
        request_id='request-123',
        run_id='run-123',
        allowed_tools=[QUERY_VM_CONTEXT],
        tool_broker=ToolBrokerDescriptor(
            run_id='run-123',
            base_url='http://tool-broker.internal',
            execution_token=execution_token,
        ),
    )


class AgentArchitectureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = InMemoryAgentRunStore(ttl_seconds=30)
        self.token = await self.store.create(
            request_id='request-123',
            run_id='run-123',
            django_cookie='sessionid=secret-session',
            allowed_tools={QUERY_VM_CONTEXT},
        )
        self.django = FakeDjangoClient()
        self.broker = ToolBrokerService(self.store, self.django)

    async def test_deterministic_provider_uses_broker_and_yields_agent_events(self):
        provider = DeterministicAssistantProvider(self.broker)
        events = [event async for event in provider.stream(make_agent_request(self.token))]

        self.assertEqual(events[0].type, 'tool_start')
        self.assertEqual(events[1].type, 'tool_result')
        self.assertTrue(events[1].data['ok'])
        self.assertIn('delta', [event.type for event in events])
        self.assertEqual(self.django.seen_cookie, 'sessionid=secret-session')

    async def test_gateway_owns_meta_done_and_deletes_run_context(self):
        provider = DeterministicAssistantProvider(self.broker)
        chunks = [
            chunk
            async for chunk in stream_gateway_events(
                browser_request=ConnectedBrowserRequest(),
                agent_request=make_agent_request(self.token),
                provider=provider,
                run_store=self.store,
            )
        ]
        stream = ''.join(chunks)

        self.assertTrue(stream.startswith('event: meta'))
        self.assertIn('event: tool_start', stream)
        self.assertIn('event: tool_result', stream)
        self.assertIn('event: delta', stream)
        self.assertIn('event: done', stream)
        self.assertFalse(await self.store.contains('run-123'))

    async def test_broker_enforces_allowlist_and_argument_model(self):
        denied = await self.broker.execute(
            run_id='run-123',
            execution_token=self.token,
            tool_name='arbitrary_http',
            raw_args={'url': 'http://example.test'},
        )
        invalid = await self.broker.execute(
            run_id='run-123',
            execution_token=self.token,
            tool_name=QUERY_VM_CONTEXT,
            raw_args={'record_id': 1, 'url': 'http://example.test'},
        )

        self.assertFalse(denied.ok)
        self.assertEqual(denied.error.code, 'tool_not_allowed')
        self.assertFalse(invalid.ok)
        self.assertEqual(invalid.error.code, 'invalid_tool_arguments')
        self.assertIsNone(self.django.seen_cookie)

    async def test_broker_rejects_invalid_execution_token(self):
        with self.assertRaises(InvalidExecutionTokenError):
            await self.broker.execute(
                run_id='run-123',
                execution_token='wrong-token',
                tool_name=QUERY_VM_CONTEXT,
                raw_args={'record_id': 1},
            )

    async def test_agent_payload_does_not_contain_django_cookie(self):
        serialized = make_agent_request(self.token).model_dump_json()

        self.assertNotIn('secret-session', serialized)
        self.assertNotIn('sessionid', serialized)

    async def test_setup_chat_collects_required_fields_before_calling_tool(self):
        setup_store = InMemoryAgentRunStore(ttl_seconds=30)
        token = await setup_store.create(
            request_id='setup-request',
            run_id='setup-run',
            django_cookie='sessionid=setup-secret; csrftoken=csrf-secret',
            allowed_tools=set(SETUP_TOOLS),
        )
        provider = DeterministicAssistantProvider(ToolBrokerService(setup_store, self.django))
        first_request = AgentRunRequest(
            question='Create an Admin Profile',
            conversation=[],
            page_state=SetupPageState(route='/new/setup'),
            request_id='setup-request',
            run_id='setup-run',
            allowed_tools=list(SETUP_TOOLS),
            tool_broker=ToolBrokerDescriptor(
                run_id='setup-run', base_url='http://tool-broker.internal', execution_token=token,
            ),
        )

        first_events = [event async for event in provider.stream(first_request)]
        self.assertEqual(first_events[0].type, 'delta')
        self.assertIn('called', first_events[0].data['text'])
        self.assertIsNone(self.django.seen_cookie)

        request = AgentRunRequest(
            question='readwrite',
            conversation=[
                ChatTurn(role='user', content='Create an Admin Profile'),
                ChatTurn(role='assistant', content='What should the Admin Profile be called?'),
                ChatTurn(role='user', content='Audit Admin'),
                ChatTurn(role='assistant', content='Which access level should it use: readonly or readwrite?'),
            ],
            page_state=SetupPageState(route='/new/setup'),
            request_id='setup-request',
            run_id='setup-run',
            allowed_tools=list(SETUP_TOOLS),
            tool_broker=ToolBrokerDescriptor(
                run_id='setup-run', base_url='http://tool-broker.internal', execution_token=token,
            ),
        )
        events = [event async for event in provider.stream(request)]

        self.assertEqual(events[0].data['name'], CREATE_ADMIN_PROFILE)
        self.assertTrue(events[1].data['ok'])
        self.assertEqual(self.django.seen_cookie, 'sessionid=setup-secret; csrftoken=csrf-secret')


class AssistantSettingsTests(unittest.TestCase):
    def test_settings_read_gateway_and_pi_configuration(self):
        environment = {
            'ASSISTANT_PROVIDER': 'pi',
            'ASSISTANT_API_KEY': 'test-secret',
            'ASSISTANT_BASE_URL': 'https://api.example.test/v1',
            'ASSISTANT_MODEL': 'example-model',
            'DJANGO_BASE_URL': 'http://django.test:9000',
            'PI_AGENT_BASE_URL': 'http://pi-agent.test:8010',
            'PI_AGENT_SERVICE_TOKEN': 'pi-service-secret',
            'TOOL_BROKER_BASE_URL': 'http://broker.test:8002',
        }
        with patch.dict(os.environ, environment, clear=True):
            settings = AssistantSettings(_env_file=None)

        self.assertEqual(settings.assistant_provider, 'pi')
        self.assertEqual(settings.django_base_url, 'http://django.test:9000')
        self.assertEqual(settings.pi_agent_base_url, 'http://pi-agent.test:8010')
        self.assertEqual(settings.tool_broker_base_url, 'http://broker.test:8002')
        self.assertEqual(settings.require_pi_service_token(), 'pi-service-secret')
        self.assertNotIn('pi-service-secret', repr(settings))

    def test_missing_tokens_fail_only_when_requested(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = AssistantSettings(_env_file=None)

        with self.assertRaisesRegex(RuntimeError, 'ASSISTANT_API_KEY'):
            settings.require_api_key()
        with self.assertRaisesRegex(RuntimeError, 'PI_AGENT_SERVICE_TOKEN'):
            settings.require_pi_service_token()


if __name__ == '__main__':
    unittest.main()
