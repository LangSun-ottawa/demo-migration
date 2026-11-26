import asyncio
import json
import logging
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from assistant_gateway.config import get_assistant_settings
from assistant_gateway.protocol import (
    AgentEvent,
    AgentRunRequest,
    AssistantRequest,
    PageState,
    ToolBrokerDescriptor,
    ToolInvocation,
    ToolResult,
)
from assistant_gateway.providers import (
    AssistantProvider,
    DeterministicAssistantProvider,
    PiAgentServiceAdapter,
)
from assistant_gateway.run_store import (
    InMemoryAgentRunStore,
    InvalidExecutionTokenError,
    RunNotFoundError,
)
from assistant_gateway.tools import (
    SETUP_TOOLS,
    QUERY_VM_CONTEXT,
    DjangoApiClient,
    ToolBrokerService,
)


LOGGER = logging.getLogger('assistant_gateway')
SETTINGS = get_assistant_settings()
RUN_STORE = InMemoryAgentRunStore(SETTINGS.agent_run_ttl_seconds)
DJANGO_CLIENT = DjangoApiClient(SETTINGS.django_base_url)
TOOL_BROKER = ToolBrokerService(RUN_STORE, DJANGO_CLIENT)


def encode_sse(event: str, data: dict) -> str:
    return f'event: {event}\ndata: {json.dumps(data, ensure_ascii=True)}\n\n'


def get_run_store() -> InMemoryAgentRunStore:
    return RUN_STORE


def get_tool_broker() -> ToolBrokerService:
    return TOOL_BROKER


def get_assistant_provider(
    tool_broker: ToolBrokerService = Depends(get_tool_broker),
) -> AssistantProvider:
    if SETTINGS.assistant_provider == 'pi':
        return PiAgentServiceAdapter(
            SETTINGS.pi_agent_base_url,
            SETTINGS.require_pi_service_token(),
            SETTINGS.agent_run_timeout_seconds,
        )
    return DeterministicAssistantProvider(tool_broker)


def _bearer_token(authorization: str | None) -> str:
    scheme, _, token = (authorization or '').partition(' ')
    if scheme.lower() != 'bearer' or not token:
        raise HTTPException(status_code=401, detail='Bearer execution token required.')
    return token


def _django_session_cookie(request: Request) -> str:
    cookie_names = (
        SETTINGS.django_session_cookie_name,
        SETTINGS.django_csrf_cookie_name,
    )
    return '; '.join(
        f'{name}={request.cookies[name]}'
        for name in cookie_names
        if request.cookies.get(name)
    )


async def stream_gateway_events(
    *,
    browser_request: Request,
    agent_request: AgentRunRequest,
    provider: AssistantProvider,
    run_store: InMemoryAgentRunStore,
) -> AsyncIterator[str]:
    LOGGER.info(
        'agent_run_started request_id=%s run_id=%s provider=%s',
        agent_request.request_id,
        agent_request.run_id,
        type(provider).__name__,
    )
    yield encode_sse(
        'meta',
        {
            'request_id': agent_request.request_id,
            'run_id': agent_request.run_id,
            'provider': SETTINGS.assistant_provider,
        },
    )
    final_status = 'completed'
    try:
        async with asyncio.timeout(SETTINGS.agent_run_timeout_seconds):
            async for event in provider.stream(agent_request):
                if await browser_request.is_disconnected():
                    final_status = 'cancelled'
                    break
                yield encode_sse(event.type, event.data)
                if event.type == 'error':
                    final_status = 'failed'
    except TimeoutError:
        final_status = 'timed_out'
        yield encode_sse(
            'error',
            {'code': 'agent_timeout', 'message': 'The agent run timed out.'},
        )
    except asyncio.CancelledError:
        final_status = 'cancelled'
        raise
    except Exception:
        final_status = 'failed'
        LOGGER.exception(
            'agent_run_failed request_id=%s run_id=%s',
            agent_request.request_id,
            agent_request.run_id,
        )
        yield encode_sse(
            'error',
            {'code': 'gateway_error', 'message': 'The assistant run failed.'},
        )
    finally:
        await run_store.delete(agent_request.run_id)
        LOGGER.info(
            'agent_run_finished request_id=%s run_id=%s status=%s',
            agent_request.request_id,
            agent_request.run_id,
            final_status,
        )

    if final_status != 'cancelled':
        yield encode_sse(
            'done',
            {
                'request_id': agent_request.request_id,
                'run_id': agent_request.run_id,
                'status': final_status,
            },
        )


app = FastAPI(
    title='Coexist Demo Assistant Gateway',
    description='Agent orchestration and session-bound tool broker boundary.',
    version='2.0.0',
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        'http://127.0.0.1:8001',
        'http://localhost:8001',
        'http://127.0.0.1:4200',
        'http://localhost:4200',
    ],
    allow_credentials=True,
    allow_methods=['POST', 'GET'],
    allow_headers=['Content-Type'],
)


@app.get('/health')
async def health():
    return {
        'status': 'ok',
        'django_base_url': SETTINGS.django_base_url,
        'assistant_provider': SETTINGS.assistant_provider,
        'assistant_model': SETTINGS.assistant_model,
    }


@app.post('/internal/agent-runs/{run_id}/tools/{tool_name}', response_model=ToolResult)
async def invoke_tool(
    run_id: str,
    tool_name: str,
    invocation: ToolInvocation,
    authorization: str | None = Header(default=None),
    tool_broker: ToolBrokerService = Depends(get_tool_broker),
):
    token = _bearer_token(authorization)
    try:
        return await tool_broker.execute(
            run_id=run_id,
            execution_token=token,
            tool_name=tool_name,
            raw_args=invocation.args,
        )
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidExecutionTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post('/assistant/stream')
async def assistant_stream(
    payload: AssistantRequest,
    request: Request,
    provider: AssistantProvider = Depends(get_assistant_provider),
    run_store: InMemoryAgentRunStore = Depends(get_run_store),
):
    request_id = str(uuid4())
    run_id = str(uuid4())
    allowed_tools = (
        set(SETUP_TOOLS)
        if payload.page_state.route == '/new/setup'
        else {QUERY_VM_CONTEXT}
    )
    execution_token = await run_store.create(
        request_id=request_id,
        run_id=run_id,
        django_cookie=_django_session_cookie(request),
        allowed_tools=allowed_tools,
    )
    agent_request = AgentRunRequest(
        **payload.model_dump(),
        request_id=request_id,
        run_id=run_id,
        allowed_tools=sorted(
            allowed_tools | {'ask_user_question'}
            if payload.page_state.route == '/new/setup'
            else allowed_tools
        ),
        tool_broker=ToolBrokerDescriptor(
            run_id=run_id,
            base_url=SETTINGS.tool_broker_base_url.rstrip('/'),
            execution_token=execution_token,
        ),
    )
    return StreamingResponse(
        stream_gateway_events(
            browser_request=request,
            agent_request=agent_request,
            provider=provider,
            run_store=run_store,
        ),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'X-Request-ID': request_id,
            'X-Agent-Run-ID': run_id,
        },
    )


__all__ = [
    'AgentEvent',
    'AssistantRequest',
    'PageState',
    'app',
    'encode_sse',
    'stream_gateway_events',
]
