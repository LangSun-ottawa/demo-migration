from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=1000)


class PageState(BaseModel):
    route: Literal['/new/context-assistant']
    selected_record_id: int = Field(gt=0)
    active_panel: Literal['associations', 'warnings'] = 'associations'
    visible_filter: Literal['all', 'active', 'inactive'] = 'all'
    expanded_association_ids: list[str] = Field(default_factory=list, max_length=20)


class SetupPageState(BaseModel):
    route: Literal['/new/setup']


class AssistantRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    page_state: PageState | SetupPageState
    conversation: list[ChatTurn] = Field(default_factory=list, max_length=20)


class ToolBrokerDescriptor(BaseModel):
    run_id: str
    base_url: str
    execution_token: str


class AgentRunRequest(AssistantRequest):
    request_id: str
    run_id: str
    allowed_tools: list[str]
    tool_broker: ToolBrokerDescriptor


class AgentEvent(BaseModel):
    type: Literal['tool_start', 'tool_result', 'delta', 'error']
    data: dict[str, Any]


class ToolInvocation(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict)


class ToolError(BaseModel):
    code: str
    message: str
    status_code: int | None = None


class ToolResult(BaseModel):
    ok: bool
    name: str
    result: dict[str, Any] | None = None
    error: ToolError | None = None


class ToolResultEventData(BaseModel):
    """Public SSE tool_result payload; never include credentials or raw headers."""

    call_id: str
    name: str
    ok: bool
    summary: str
    result: dict[str, Any] | None = None
    error: ToolError | None = None
    question: str | None = None
    missing_fields: list[str] | None = None
