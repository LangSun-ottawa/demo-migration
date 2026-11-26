import json
import re
from collections.abc import AsyncIterator
from typing import Protocol

import httpx

from assistant_gateway.protocol import AgentEvent, AgentRunRequest
from assistant_gateway.tools import (
    CREATE_ADAPTER,
    CREATE_ADMIN_PROFILE,
    CREATE_ADMIN_USER,
    CREATE_INSTANCE,
    QUERY_SETUP_STATE,
    QUERY_VM_CONTEXT,
    ToolBrokerService,
)


class AssistantProvider(Protocol):
    async def stream(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]:
        """Yield agent-owned tool and text events. Gateway owns meta and done."""
        if False:  # pragma: no cover - documents the async-generator protocol
            yield AgentEvent(type='delta', data={})


def compose_deterministic_answer(request: AgentRunRequest, context: dict) -> str:
    selection = context['selection']
    associations = context.get('associations', [])
    warnings = context.get('warnings', [])
    question = request.question.lower()
    state = request.page_state

    summary = (
        f"You are viewing {selection['name']}. Django reports category "
        f"{selection['category']}, status "
        f"{'active' if selection['active'] else 'inactive'}, and "
        f"{len(associations)} associations. "
    )
    if any(term in question for term in ('warning', 'risk', 'review', 'problem')):
        detail = (
            ' '.join(f'{index + 1}. {warning}' for index, warning in enumerate(warnings))
            if warnings
            else 'Django returned no warnings for the selected VM.'
        )
    elif associations:
        detail = ' '.join(
            f"{item['name']} is a {item['type']} with status {item['status']}."
            for item in associations
        )
    else:
        detail = 'No associations are configured for this VM category.'
    return (
        f'{summary}{detail} The client context says the {state.active_panel} panel '
        f'is open and the {state.visible_filter} filter is selected.'
    )


class DeterministicAssistantProvider:
    """No-key agent loop used locally; it exercises the same broker policy boundary."""

    def __init__(self, tool_broker: ToolBrokerService):
        self.tool_broker = tool_broker

    async def stream(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]:
        if request.page_state.route == '/new/setup':
            async for event in self._stream_setup(request):
                yield event
            return

        call_id = f'{request.run_id}:tool-1'
        yield AgentEvent(
            type='tool_start',
            data={'call_id': call_id, 'name': QUERY_VM_CONTEXT},
        )
        result = await self.tool_broker.execute(
            run_id=request.tool_broker.run_id,
            execution_token=request.tool_broker.execution_token,
            tool_name=QUERY_VM_CONTEXT,
            raw_args={'record_id': request.page_state.selected_record_id},
        )
        yield AgentEvent(
            type='tool_result',
            data={
                'call_id': call_id,
                'name': QUERY_VM_CONTEXT,
                'ok': result.ok,
                'summary': 'VM context loaded' if result.ok else result.error.message,
                'result': result.result,
                'error': result.error.model_dump() if result.error else None,
            },
        )
        if not result.ok or result.result is None:
            yield AgentEvent(
                type='error',
                data={
                    'code': result.error.code if result.error else 'tool_failed',
                    'message': result.error.message if result.error else 'The tool failed.',
                },
            )
            return

        answer = compose_deterministic_answer(request, result.result)
        words = answer.split(' ')
        for index, word in enumerate(words):
            suffix = '' if index == len(words) - 1 else ' '
            yield AgentEvent(type='delta', data={'text': f'{word}{suffix}'})

    async def _stream_setup(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]:
        tool_name = self._setup_intent(request)
        if tool_name is None:
            yield AgentEvent(
                type='delta',
                data={
                    'text': 'I can help create an Admin Profile, Admin User, Instance, or Adapter. '
                            'Tell me which resource you want to create.',
                },
            )
            return

        args = self._collect_setup_args(request, tool_name)
        missing = self._first_missing(tool_name, args)
        if missing:
            yield AgentEvent(type='delta', data={'text': self._missing_prompt(tool_name, missing)})
            return

        if tool_name in (CREATE_ADMIN_USER, CREATE_ADAPTER):
            query_call_id = f'{request.run_id}:query-setup'
            yield AgentEvent(
                type='tool_start',
                data={'call_id': query_call_id, 'name': QUERY_SETUP_STATE},
            )
            query_result = await self.tool_broker.execute(
                run_id=request.run_id,
                execution_token=request.tool_broker.execution_token,
                tool_name=QUERY_SETUP_STATE,
                raw_args={},
            )
            yield AgentEvent(
                type='tool_result',
                data={
                    'call_id': query_call_id,
                    'name': QUERY_SETUP_STATE,
                    'ok': query_result.ok,
                    'summary': 'Current setup loaded' if query_result.ok else query_result.error.message,
                    'result': query_result.result,
                    'error': query_result.error.model_dump() if query_result.error else None,
                },
            )
            if not query_result.ok:
                yield AgentEvent(type='error', data={'code': 'tool_failed', 'message': query_result.error.message})
                return
            snapshot = query_result.result or {}
            collection = snapshot.get('profiles' if tool_name == CREATE_ADMIN_USER else 'instances', [])
            relation_key = 'profile_id' if tool_name == CREATE_ADMIN_USER else 'instance_id'
            relation_label = 'Admin Profile' if tool_name == CREATE_ADMIN_USER else 'Instance'
            if not collection:
                yield AgentEvent(type='delta', data={'text': f'No {relation_label} exists yet. Create one first.'})
                return
            reference = args.pop('_relation', None)
            related = self._resolve_relation(reference, collection)
            if related is None:
                options = ', '.join(f"{item['name']} (id {item['id']})" for item in collection)
                yield AgentEvent(
                    type='delta',
                    data={'text': f'Which {relation_label} should I use? Available: {options}.'},
                )
                return
            args[relation_key] = related['id']

        call_id = f'{request.run_id}:create'
        yield AgentEvent(type='tool_start', data={'call_id': call_id, 'name': tool_name})
        result = await self.tool_broker.execute(
            run_id=request.run_id,
            execution_token=request.tool_broker.execution_token,
            tool_name=tool_name,
            raw_args=args,
        )
        yield AgentEvent(
            type='tool_result',
            data={
                'call_id': call_id,
                'name': tool_name,
                'ok': result.ok,
                'summary': 'Django API completed the operation' if result.ok else result.error.message,
                'result': result.result,
                'error': result.error.model_dump() if result.error else None,
            },
        )
        if not result.ok:
            yield AgentEvent(type='error', data={'code': result.error.code, 'message': result.error.message})
            return
        labels = {
            CREATE_ADMIN_PROFILE: 'Admin Profile',
            CREATE_ADMIN_USER: 'Admin User',
            CREATE_INSTANCE: 'Instance',
            CREATE_ADAPTER: 'Adapter configuration',
        }
        yield AgentEvent(
            type='delta',
            data={'text': f"{labels[tool_name]} was created successfully through the Django API."},
        )

    @staticmethod
    def _detect_setup_tool(text: str) -> str | None:
        lowered = text.lower()
        if 'admin user' in lowered or '用户' in lowered or re.search(r'\buser\b', lowered):
            return CREATE_ADMIN_USER
        if 'admin profile' in lowered or '权限' in lowered or re.search(r'\bprofile\b', lowered):
            return CREATE_ADMIN_PROFILE
        if 'adapter' in lowered or '适配器' in lowered:
            return CREATE_ADAPTER
        if 'instance' in lowered or '实例' in lowered:
            return CREATE_INSTANCE
        return None

    def _setup_intent(self, request: AgentRunRequest) -> str | None:
        direct = self._detect_setup_tool(request.question)
        if direct:
            return direct
        for turn in reversed(request.conversation):
            if turn.role == 'user':
                detected = self._detect_setup_tool(turn.content)
                if detected:
                    return detected
        for turn in reversed(request.conversation):
            if turn.role == 'assistant':
                detected = self._detect_setup_tool(turn.content)
                if detected:
                    return detected
        return None

    def _collect_setup_args(self, request: AgentRunRequest, tool_name: str) -> dict:
        turns = [*request.conversation, type('Turn', (), {'role': 'user', 'content': request.question})()]
        intent_index = 0
        for index, turn in enumerate(turns):
            if turn.role == 'user' and self._detect_setup_tool(turn.content) == tool_name:
                intent_index = index
        args: dict = {}
        previous_assistant = ''
        for turn in turns[intent_index:]:
            text = turn.content.strip()
            lowered = text.lower()
            if turn.role == 'assistant':
                previous_assistant = lowered
                continue
            explicit_name = re.search(r'(?:named|called|name\s*(?:is|=|:))\s+["\']?(.+?)["\']?$', text, re.I)
            if explicit_name:
                args['name'] = explicit_name.group(1).strip(' "\'')
            if 'what should the admin profile be called' in previous_assistant or 'what should the instance be called' in previous_assistant or 'what should the adapter be called' in previous_assistant:
                args['name'] = text
            if 'what username' in previous_assistant:
                args['username'] = text
            if 'what email' in previous_assistant:
                args['email'] = text
            if 'which admin profile' in previous_assistant or 'which instance should i use' in previous_assistant:
                args['_relation'] = text
            if 'which access level' in previous_assistant or re.search(r'\b(readonly|read[ /-]?only|readwrite|read[ /-]?write)\b', lowered):
                if re.search(r'\bread[ /-]?only\b|\breadonly\b|只读', lowered):
                    args['access_level'] = 'readonly'
                elif re.search(r'\bread[ /-]?write\b|\breadwrite\b|读写', lowered):
                    args['access_level'] = 'readwrite'
            if 'which environment' in previous_assistant or re.search(r'\b(dev|development|test|testing|prod|production)\b', lowered):
                match = re.search(r'\b(dev|development|test|testing|prod|production)\b', lowered)
                if match:
                    args['environment'] = {'development': 'dev', 'testing': 'test', 'production': 'prod'}.get(match.group(1), match.group(1))
            if 'which adapter type' in previous_assistant or re.search(r'\b(rest|syslog|custom)\b', lowered):
                match = re.search(r'\b(rest|syslog|custom)\b', lowered)
                if match:
                    args['adapter_type'] = match.group(1)
            email = re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', text)
            if email:
                args['email'] = email.group(0)
            if 'what endpoint' in previous_assistant:
                args['endpoint'] = text
            if 'what username' not in previous_assistant:
                username = re.search(r'(?:username\s*(?:is|=|:)?|用户名(?:是|为|:)?)[\s"\']*([\w.-]+)', text, re.I)
                if username:
                    args['username'] = username.group(1)
            previous_assistant = ''
        return args

    @staticmethod
    def _first_missing(tool_name: str, args: dict) -> str | None:
        required = {
            CREATE_ADMIN_PROFILE: ('name', 'access_level'),
            CREATE_ADMIN_USER: ('username', 'email'),
            CREATE_INSTANCE: ('name', 'environment'),
            CREATE_ADAPTER: ('name', 'adapter_type', 'endpoint'),
        }[tool_name]
        return next((field for field in required if not args.get(field)), None)

    @staticmethod
    def _missing_prompt(tool_name: str, field: str) -> str:
        prompts = {
            (CREATE_ADMIN_PROFILE, 'name'): 'What should the Admin Profile be called?',
            (CREATE_ADMIN_PROFILE, 'access_level'): 'Which access level should it use: readonly or readwrite?',
            (CREATE_ADMIN_USER, 'username'): 'What username should the Admin User use?',
            (CREATE_ADMIN_USER, 'email'): 'What email address should the Admin User use?',
            (CREATE_INSTANCE, 'name'): 'What should the Instance be called?',
            (CREATE_INSTANCE, 'environment'): 'Which environment should it use: dev, test, or prod?',
            (CREATE_ADAPTER, 'name'): 'What should the Adapter be called?',
            (CREATE_ADAPTER, 'adapter_type'): 'Which Adapter type should it use: rest, syslog, or custom?',
            (CREATE_ADAPTER, 'endpoint'): 'What endpoint should the Adapter store?',
        }
        return prompts[(tool_name, field)]

    @staticmethod
    def _resolve_relation(reference: str | None, collection: list[dict]) -> dict | None:
        if not reference:
            return None
        normalized = reference.strip().lower()
        id_match = re.search(r'\b(?:id\s*)?(\d+)\b', normalized)
        if id_match:
            return next((item for item in collection if item['id'] == int(id_match.group(1))), None)
        exact = next((item for item in collection if item['name'].lower() == normalized), None)
        if exact:
            return exact
        matches = [item for item in collection if normalized in item['name'].lower()]
        return matches[0] if len(matches) == 1 else None


class PiAgentServiceAdapter:
    """HTTP/SSE adapter for a separately deployed Pi Agent Service."""

    allowed_event_types = {'tool_start', 'tool_result', 'delta', 'error'}

    def __init__(self, base_url: str, service_token: str, timeout_seconds: float):
        self.base_url = base_url.rstrip('/')
        self.service_token = service_token
        self.timeout_seconds = timeout_seconds

    async def stream(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]:
        timeout = httpx.Timeout(self.timeout_seconds, read=None)
        headers = {
            'Authorization': f'Bearer {self.service_token}',
            'Accept': 'text/event-stream',
        }
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=timeout) as client:
                async with client.stream(
                    'POST',
                    '/v1/agent/stream',
                    json=request.model_dump(mode='json'),
                    headers=headers,
                ) as response:
                    response.raise_for_status()
                    event_name: str | None = None
                    data_lines: list[str] = []
                    async for line in response.aiter_lines():
                        if line.startswith('event:'):
                            event_name = line[6:].strip()
                        elif line.startswith('data:'):
                            data_lines.append(line[5:].lstrip())
                        elif line == '' and event_name and data_lines:
                            if event_name in self.allowed_event_types:
                                yield AgentEvent(
                                    type=event_name,
                                    data=json.loads('\n'.join(data_lines)),
                                )
                            event_name = None
                            data_lines = []
        except (httpx.HTTPError, json.JSONDecodeError):
            yield AgentEvent(
                type='error',
                data={'code': 'pi_service_error', 'message': 'Pi Agent Service failed.'},
            )
