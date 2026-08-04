import asyncio
import json
import os
from collections.abc import AsyncIterator
from typing import Literal, Protocol
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


DJANGO_BASE_URL = os.getenv('DJANGO_BASE_URL', 'http://127.0.0.1:8001').rstrip('/')


class ChatTurn(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=1000)


class PageState(BaseModel):
    route: Literal['/new/context-assistant']
    selected_record_id: int = Field(gt=0)
    active_panel: Literal['associations', 'warnings'] = 'associations'
    visible_filter: Literal['all', 'active', 'inactive'] = 'all'
    expanded_association_ids: list[str] = Field(default_factory=list, max_length=20)


class AssistantRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    page_state: PageState
    conversation: list[ChatTurn] = Field(default_factory=list, max_length=8)


class DjangoContextError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class DjangoContextClient:
    def __init__(self, base_url: str = DJANGO_BASE_URL):
        self.base_url = base_url

    async def fetch(self, record_id: int, cookie: str) -> dict:
        headers = {'cookie': cookie} if cookie else {}
        async with httpx.AsyncClient(base_url=self.base_url, timeout=5.0) as client:
            response = await client.get(
                '/api/demo/secure/page-context',
                params={'record_id': record_id},
                headers=headers,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise DjangoContextError('Django returned a non-JSON context response.') from exc

        if response.status_code == 401:
            raise DjangoContextError('Log in to Django before using the assistant.', status_code=401)
        if response.status_code >= 400:
            errors = payload.get('error') or []
            message = errors[0].get('message') if errors else 'Django context request failed.'
            raise DjangoContextError(message, status_code=response.status_code)

        result = payload.get('result')
        if not isinstance(result, dict):
            raise DjangoContextError('Django response did not contain a context result.')
        return result


def get_context_client() -> DjangoContextClient:
    return DjangoContextClient()


class AssistantProvider(Protocol):
    def compose(self, request: AssistantRequest, context: dict) -> str:
        """Return the complete answer text consumed by the SSE transport."""


class DeterministicAssistantProvider:
    """No-key provider that keeps the architecture demo runnable offline."""

    def compose(self, request: AssistantRequest, context: dict) -> str:
        selection = context['selection']
        associations = context.get('associations', [])
        warnings = context.get('warnings', [])
        question = request.question.lower()
        state = request.page_state

        page_summary = (
            f"You are viewing {selection['name']} in the VM Association page. "
            f"Django reports category {selection['category']}, "
            f"status {'active' if selection['active'] else 'inactive'}, and "
            f"{len(associations)} visible associations. "
        )

        if any(term in question for term in ('warning', 'risk', 'review', 'problem')):
            if warnings:
                detail = ' '.join(
                    f'{index + 1}. {warning}' for index, warning in enumerate(warnings)
                )
            else:
                detail = 'Django returned no warnings for the selected VM.'
        elif any(term in question for term in ('association', 'application', 'extension', 'linked')):
            if associations:
                detail = ' '.join(
                    f"{item['name']} is a {item['type']} with status {item['status']}."
                    for item in associations
                )
            else:
                detail = 'No associations are configured for this VM category.'
        else:
            attention_count = sum(
                item['status'] in ('review', 'blocked') for item in associations
            )
            detail = (
                f'{attention_count} association item(s) need attention. '
                'Ask about associations or warnings for a more focused explanation.'
            )

        client_state = (
            f"The client context says the {state.active_panel} panel is open and the "
            f"{state.visible_filter} filter is selected."
        )
        return f'{page_summary}{detail} {client_state}'


def get_assistant_provider() -> AssistantProvider:
    return DeterministicAssistantProvider()


def compose_answer(request: AssistantRequest, context: dict) -> str:
    return DeterministicAssistantProvider().compose(request, context)


def encode_sse(event: str, data: dict) -> str:
    return f'event: {event}\ndata: {json.dumps(data, ensure_ascii=True)}\n\n'


async def stream_answer(
    request_id: str,
    request: AssistantRequest,
    context: dict,
    *,
    delay_seconds: float = 0.035,
    provider: AssistantProvider | None = None,
) -> AsyncIterator[str]:
    selection = context['selection']
    yield encode_sse(
        'meta',
        {
            'request_id': request_id,
            'source': context['page']['source'],
            'record_id': selection['record_id'],
            'record_name': selection['name'],
        },
    )

    answer = (provider or DeterministicAssistantProvider()).compose(request, context)
    words = answer.split(' ')
    for index, word in enumerate(words):
        suffix = '' if index == len(words) - 1 else ' '
        yield encode_sse('delta', {'text': f'{word}{suffix}'})
        if delay_seconds:
            await asyncio.sleep(delay_seconds)

    yield encode_sse('done', {'request_id': request_id})


app = FastAPI(
    title='Coexist Demo Assistant Gateway',
    description='Fetches canonical Django page context and streams assistant responses.',
    version='1.0.0',
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
    return {'status': 'ok', 'django_base_url': DJANGO_BASE_URL}


@app.post('/assistant/stream')
async def assistant_stream(
    payload: AssistantRequest,
    request: Request,
    context_client: DjangoContextClient = Depends(get_context_client),
    provider: AssistantProvider = Depends(get_assistant_provider),
):
    try:
        context = await context_client.fetch(
            payload.page_state.selected_record_id,
            request.headers.get('cookie', ''),
        )
    except DjangoContextError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    request_id = str(uuid4())
    return StreamingResponse(
        stream_answer(request_id, payload, context, provider=provider),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'X-Request-ID': request_id,
        },
    )
