from collections.abc import Mapping
from http.cookies import SimpleCookie
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from assistant_gateway.protocol import ToolError, ToolResult
from assistant_gateway.run_store import InMemoryAgentRunStore


QUERY_VM_CONTEXT = 'query_vm_context'
QUERY_SETUP_STATE = 'query_setup_state'
CREATE_ADMIN_PROFILE = 'create_admin_profile'
CREATE_ADMIN_USER = 'create_admin_user'
CREATE_INSTANCE = 'create_instance'
CREATE_ADAPTER = 'create_adapter'
SETUP_TOOLS = (
    QUERY_SETUP_STATE,
    CREATE_ADMIN_PROFILE,
    CREATE_ADMIN_USER,
    CREATE_INSTANCE,
    CREATE_ADAPTER,
)


class QueryVmContextArguments(BaseModel):
    model_config = ConfigDict(extra='forbid')

    record_id: int = Field(gt=0)


class EmptyToolArguments(BaseModel):
    model_config = ConfigDict(extra='forbid')


class CreateAdminProfileArguments(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=80)
    access_level: str = Field(pattern='^(readonly|readwrite)$')


class CreateAdminUserArguments(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=254)
    profile_id: int = Field(gt=0)


class CreateInstanceArguments(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=80)
    environment: str = Field(pattern='^(dev|test|prod)$')


class CreateAdapterArguments(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=80)
    adapter_type: str = Field(pattern='^(rest|syslog|custom)$')
    endpoint: str = Field(min_length=1, max_length=200)
    instance_id: int = Field(gt=0)


TOOL_ARGUMENT_MODELS = {
    QUERY_VM_CONTEXT: QueryVmContextArguments,
    QUERY_SETUP_STATE: EmptyToolArguments,
    CREATE_ADMIN_PROFILE: CreateAdminProfileArguments,
    CREATE_ADMIN_USER: CreateAdminUserArguments,
    CREATE_INSTANCE: CreateInstanceArguments,
    CREATE_ADAPTER: CreateAdapterArguments,
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
            json_body=args.model_dump(mode='json') if method == 'POST' else None,
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
    ) -> ToolResult:
        headers = {'cookie': cookie} if cookie else {}
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
                errors[0].get('message')
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
    def __init__(self, run_store: InMemoryAgentRunStore, django_client: DjangoApiClient):
        self.run_store = run_store
        self.django_client = django_client

    async def execute(
        self,
        *,
        run_id: str,
        execution_token: str,
        tool_name: str,
        raw_args: dict[str, Any],
    ) -> ToolResult:
        context = await self.run_store.authorize(run_id, execution_token)
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
        except ValidationError:
            return ToolResult(
                ok=False,
                name=tool_name,
                error=ToolError(
                    code='invalid_tool_arguments',
                    message='Tool arguments failed validation.',
                    status_code=422,
                ),
            )
        if tool_name == QUERY_VM_CONTEXT:
            return await self.django_client.query_vm_context(args, context.django_cookie)
        return await self.django_client.execute_setup_tool(tool_name, args, context.django_cookie)
