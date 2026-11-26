from collections.abc import Mapping
from http.cookies import SimpleCookie
from typing import Any
from datetime import datetime, timedelta
import json
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from assistant_gateway.protocol import ToolError, ToolResult
from assistant_gateway.run_store import InMemoryAgentRunStore


QUERY_VM_CONTEXT = 'query_vm_context'
QUERY_SETUP_STATE = 'query_setup_state'
CREATE_ADMIN_PROFILE = 'create_admin_profile'
CREATE_ADMIN_USER = 'create_admin_user'
CREATE_INSTANCE = 'create_instance'
CREATE_ADAPTER = 'create_adapter'
LOG_ROUTES = {
    'list_log_datasets': '/datasets', 'get_log_schema': '/schema', 'find_device': '/devices',
    'query_log_events': '/events', 'get_event_details': '/event', 'get_related_events': '/related',
}
SETUP_TOOLS = (
    QUERY_SETUP_STATE,
    CREATE_ADMIN_PROFILE,
    CREATE_ADMIN_USER,
    CREATE_INSTANCE,
    CREATE_ADAPTER,
    *LOG_ROUTES,
)


class QueryVmContextArguments(BaseModel):
    model_config = ConfigDict(extra='forbid')

    record_id: int = Field(gt=0)


class EmptyToolArguments(BaseModel):
    model_config = ConfigDict(extra='forbid')


class CreateArguments(BaseModel):
    operation_id: UUID | None = None


class CreateAdminProfileArguments(CreateArguments):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=80)
    access_level: str = Field(pattern='^(readonly|readwrite)$')


class CreateAdminUserArguments(CreateArguments):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=254)
    profile_id: int = Field(gt=0)


class CreateInstanceArguments(CreateArguments):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=80)
    environment: str = Field(pattern='^(dev|test|prod)$')


class CreateAdapterArguments(CreateArguments):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=80)
    adapter_type: str = Field(pattern='^(rest|syslog|custom)$')
    endpoint: str = Field(min_length=1, max_length=200)
    instance_id: int = Field(gt=0)


class DatasetArguments(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset_id: UUID


class FindDeviceArguments(DatasetArguments):
    query: str = Field(default='', max_length=80)


class LogQueryArguments(DatasetArguments):
    start: datetime
    end: datetime
    device_id: int | None = Field(default=None, gt=0)
    ip: str | None = Field(default=None, max_length=45)
    kind: str | None = Field(default=None, pattern='^(traffic|config_change|threat)$')
    action: str | None = Field(default=None, pattern='^(allow|deny|blocked|policy_change|detected)$')
    limit: int = Field(default=30, ge=1, le=50)

    @model_validator(mode='after')
    def bounded_range(self):
        if not self.start.tzinfo or not self.end.tzinfo or not timedelta(0) <= self.end - self.start <= timedelta(hours=24):
            raise ValueError('Use timezone-aware ordered timestamps with at most 24 hours between them.')
        return self


class EventReferenceArguments(DatasetArguments):
    event_id: int = Field(gt=0)


TOOL_ARGUMENT_MODELS = {
    QUERY_VM_CONTEXT: QueryVmContextArguments,
    QUERY_SETUP_STATE: EmptyToolArguments,
    CREATE_ADMIN_PROFILE: CreateAdminProfileArguments,
    CREATE_ADMIN_USER: CreateAdminUserArguments,
    CREATE_INSTANCE: CreateInstanceArguments,
    CREATE_ADAPTER: CreateAdapterArguments,
    'list_log_datasets': EmptyToolArguments,
    'get_log_schema': EmptyToolArguments,
    'find_device': FindDeviceArguments,
    'query_log_events': LogQueryArguments,
    'get_event_details': EventReferenceArguments,
    'get_related_events': EventReferenceArguments,
}


class DjangoApiClient:
    def __init__(self, base_url: str, timeout_seconds: float = 5.0):
        self.base_url = base_url.rstrip('/')
        self.timeout_seconds = timeout_seconds

    async def query_vm_context(self, args: QueryVmContextArguments, cookie: str) -> ToolResult:
        return await self._request(
            QUERY_VM_CONTEXT,
            'GET',
            '/api/demo/secure/page-context',
            cookie,
            params={'record_id': args.record_id},
        )

    async def execute_setup_tool(self, tool_name: str, args: BaseModel, cookie: str) -> ToolResult:
        if tool_name in LOG_ROUTES:
            return await self._request(tool_name, 'GET', '/api/demo/secure/logs' + LOG_ROUTES[tool_name], cookie,
                params=args.model_dump(mode='json', exclude_none=True))
        routes = {
            QUERY_SETUP_STATE: ('GET', '/api/demo/secure/setup'),
            CREATE_ADMIN_PROFILE: ('POST', '/api/demo/secure/setup/profiles'),
            CREATE_ADMIN_USER: ('POST', '/api/demo/secure/setup/users'),
            CREATE_INSTANCE: ('POST', '/api/demo/secure/setup/instances'),
            CREATE_ADAPTER: ('POST', '/api/demo/secure/setup/adapters'),
        }
        method, path = routes[tool_name]
        return await self._request(
            tool_name,
            method,
            path,
            cookie,
            json_body=args.model_dump(mode='json', exclude={'operation_id'}) if method == 'POST' else None,
            operation_id=str(args.operation_id) if method == 'POST' and args.operation_id else None,
        )

    async def _request(
        self,
        tool_name: str,
        method: str,
        path: str,
        cookie: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        operation_id: str | None = None,
    ) -> ToolResult:
        headers = {'cookie': cookie} if cookie else {}
        if operation_id:
            headers['Idempotency-Key'] = operation_id
        parsed_cookie = SimpleCookie()
        parsed_cookie.load(cookie)
        if 'csrftoken' in parsed_cookie:
            headers['X-CSRFToken'] = parsed_cookie['csrftoken'].value
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
            ) as client:
                response = await client.request(
                    method,
                    path,
                    params=params,
                    json=json_body,
                    headers=headers,
                )
        except httpx.HTTPError:
            return ToolResult(
                ok=False,
                name=tool_name,
                error=ToolError(
                    code='django_unavailable',
                    message='The Django API is unavailable.',
                    status_code=502,
                ),
            )

        try:
            payload = response.json()
        except ValueError:
            return ToolResult(
                ok=False,
                name=tool_name,
                error=ToolError(
                    code='invalid_django_response',
                    message='Django returned an invalid tool response.',
                    status_code=502,
                ),
            )

        if response.status_code in (401, 403):
            return ToolResult(
                ok=False,
                name=tool_name,
                error=ToolError(
                    code='django_unauthorized' if response.status_code == 401 else 'django_forbidden',
                    message=(
                        'Django requires an authenticated session.'
                        if response.status_code == 401
                        else 'Django denied this operation.'
                    ),
                    status_code=response.status_code,
                ),
            )
        if response.status_code >= 400:
            errors = payload.get('error') if isinstance(payload, Mapping) else None
            message = (
                '; '.join(str(error.get('message', '')) for error in errors[:5] if isinstance(error, Mapping))
                if isinstance(errors, list) and errors and isinstance(errors[0], Mapping)
                else 'Django rejected the tool request.'
            )
            return ToolResult(
                ok=False,
                name=tool_name,
                error=ToolError(
                    code='django_business_error',
                    message=str(message),
                    status_code=response.status_code,
                ),
            )

        result = payload.get('result') if isinstance(payload, Mapping) else None
        if not isinstance(result, dict):
            return ToolResult(
                ok=False,
                name=tool_name,
                error=ToolError(
                    code='invalid_django_response',
                    message='Django response did not contain a context result.',
                    status_code=502,
                ),
            )
        return ToolResult(ok=True, name=tool_name, result=result)


class ToolBrokerService:
    def __init__(self, run_store: InMemoryAgentRunStore, django_client: DjangoApiClient, history_client=None):
        self.run_store = run_store
        self.django_client = django_client
        self.history_client = history_client

    async def execute(
        self,
        *,
        run_id: str,
        execution_token: str,
        tool_name: str,
        raw_args: dict[str, Any],
        call_id: str | None = None,
    ) -> ToolResult:
        context = await self.run_store.authorize(run_id, execution_token)
        async with context.tool_lock:
            # A waiting tool must not outlive its execution capability.
            await self.run_store.authorize(run_id, execution_token)
            return await self._execute(context, run_id, tool_name, raw_args, call_id)

    async def _execute(self, context, run_id, tool_name, raw_args, call_id):
        if tool_name not in context.allowed_tools:
            return ToolResult(
                ok=False,
                name=tool_name,
                error=ToolError(
                    code='tool_not_allowed',
                    message='This tool is not allowed for the current agent run.',
                    status_code=403,
                ),
            )
        argument_model = TOOL_ARGUMENT_MODELS.get(tool_name)
        if argument_model is None:
            return ToolResult(
                ok=False,
                name=tool_name,
                error=ToolError(
                    code='unknown_tool',
                    message='The requested tool is not registered.',
                    status_code=404,
                ),
            )

        try:
            args = argument_model.model_validate(raw_args)
        except ValidationError as exc:
            return ToolResult(
                ok=False,
                name=tool_name,
                error=ToolError(
                    code='invalid_tool_arguments',
                    message='Tool arguments failed validation: ' + '; '.join(
                        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                        for error in exc.errors(include_input=False)[:5]),
                    status_code=422,
                ),
            )
        call_id = call_id or str(uuid4())
        if isinstance(args, CreateArguments) and args.operation_id is None and context.conversation_id:
            canonical = json.dumps(args.model_dump(mode='json', exclude={'operation_id'}), sort_keys=True, separators=(',', ':'))
            args.operation_id = uuid5(NAMESPACE_URL, f'{context.conversation_id}:{tool_name}:{canonical}')
        durable = context.conversation_id and self.history_client
        if durable:
            await self.history_client.tool(context.django_cookie, run_id, call_id, tool_name,
                'started', args.model_dump(mode='json', exclude_none=True))
        if tool_name == QUERY_VM_CONTEXT:
            result = await self.django_client.query_vm_context(args, context.django_cookie)
        else:
            result = await self.django_client.execute_setup_tool(tool_name, args, context.django_cookie)
        if durable:
            await self.history_client.tool(context.django_cookie, run_id, call_id, tool_name,
                'finished', result=result.model_dump(mode='json'))
        return result
