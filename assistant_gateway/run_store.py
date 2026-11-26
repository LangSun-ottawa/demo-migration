import asyncio
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentRunContext:
    request_id: str
    run_id: str
    django_cookie: str
    allowed_tools: frozenset[str]
    token_digest: str
    expires_at: float


class RunNotFoundError(Exception):
    pass


class InvalidExecutionTokenError(Exception):
    pass


class InMemoryAgentRunStore:
    """Process-local run state. Replace with a TTL store for multi-worker deployment."""

    def __init__(self, ttl_seconds: float = 120.0):
        self.ttl_seconds = ttl_seconds
        self._runs: dict[str, AgentRunContext] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    async def create(
        self,
        *,
        request_id: str,
        run_id: str,
        django_cookie: str,
        allowed_tools: set[str],
    ) -> str:
        execution_token = secrets.token_urlsafe(32)
        context = AgentRunContext(
            request_id=request_id,
            run_id=run_id,
            django_cookie=django_cookie,
            allowed_tools=frozenset(allowed_tools),
            token_digest=self._digest(execution_token),
            expires_at=time.monotonic() + self.ttl_seconds,
        )
        async with self._lock:
            self._runs[run_id] = context
        return execution_token

    async def authorize(self, run_id: str, execution_token: str) -> AgentRunContext:
        async with self._lock:
            context = self._runs.get(run_id)
            if context is None or context.expires_at <= time.monotonic():
                self._runs.pop(run_id, None)
                raise RunNotFoundError('Agent run is missing or expired.')
            if not hmac.compare_digest(
                context.token_digest,
                self._digest(execution_token),
            ):
                raise InvalidExecutionTokenError('Execution token is invalid.')
            return context

    async def delete(self, run_id: str) -> None:
        async with self._lock:
            self._runs.pop(run_id, None)

    async def contains(self, run_id: str) -> bool:
        async with self._lock:
            return run_id in self._runs
