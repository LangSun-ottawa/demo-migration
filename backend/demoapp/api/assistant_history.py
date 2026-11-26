"""User-owned durable history. Only Gateway/Broker may append assistant/tool data."""
import hmac
import json
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import BasePermission

from demoapp.api.base import ContractAPIView, EmptySerializer, StrictSerializer
from demoapp.api.permissions import FEATURE_DEMO_SETUP, FeaturePermission, FeaturePrivilege
from demoapp.fdc_frame.response import FdcJsonResponse
from demoapp.models import AssistantConversation, AssistantTurn, AssistantToolCall


def failure(message, status):
    return FdcJsonResponse(False, errors=[{'code': 'BE', 'message': message}], http_code=status)


class HistoryServicePermission(BasePermission):
    message = 'History service credential required.'

    def has_permission(self, request, view):
        return bool(settings.ASSISTANT_HISTORY_TOKEN) and hmac.compare_digest(
            request.headers.get('X-Assistant-History-Token', ''), settings.ASSISTANT_HISTORY_TOKEN,
        )


class HistoryView(ContractAPIView):
    permission_classes = [FeaturePermission]
    feature_key = FEATURE_DEMO_SETUP
    method_permissions = {'get': FeaturePrivilege.READONLY, 'post': FeaturePrivilege.READONLY}


class InternalHistoryView(HistoryView):
    permission_classes = [FeaturePermission, HistoryServicePermission]


class StartSerializer(StrictSerializer):
    conversation_id = serializers.UUIDField(required=False, allow_null=True)
    run_id = serializers.UUIDField()
    request_id = serializers.UUIDField()
    question = serializers.CharField(max_length=500)


class ToolSerializer(StrictSerializer):
    call_id = serializers.CharField(max_length=256)
    name = serializers.ChoiceField(choices=[
        'query_setup_state', 'create_admin_profile', 'create_admin_user',
        'create_instance', 'create_adapter', 'ask_user_question',
        'list_log_datasets', 'get_log_schema', 'find_device', 'query_log_events', 'get_event_details', 'get_related_events',
    ])
    phase = serializers.ChoiceField(choices=['started', 'finished'])
    arguments = serializers.JSONField(required=False, default=dict)
    result = serializers.JSONField(required=False, allow_null=True)

    def validate(self, attrs):
        for key in ('arguments', 'result'):
            if attrs.get(key) is not None and not isinstance(attrs[key], dict):
                raise serializers.ValidationError({key: 'Expected an object.'})
        if len(json.dumps(attrs)) > 200_000:
            raise serializers.ValidationError('Tool history exceeds size limit.')
        return attrs


class FinishSerializer(StrictSerializer):
    assistant_text = serializers.CharField(max_length=12000, allow_blank=True)
    status = serializers.ChoiceField(choices=['completed', 'failed', 'cancelled', 'timed_out'])


def tool_payload(tool):
    return {'call_id': tool.call_id, 'name': tool.name, 'arguments': tool.arguments,
            'result': tool.result, 'status': tool.status}


def packed_history(conversation):
    """Bound by whole turns, never separate a tool result from its call."""
    turns = list(conversation.turns.order_by('-id').prefetch_related('tools')[:10])
    selected, remaining = [], 64000
    for turn in turns:
        tools = []
        for tool in turn.tools.all():
            item = tool_payload(tool)
            result = item['result']
            if result and isinstance(result.get('result'), dict):
                data = result['result']
                if data.get('created_record'):
                    item['result'] = {**result, 'result': {key: data[key] for key in
                        ('created_record', 'operation_id', 'operation_replayed') if key in data}}
                elif len(json.dumps(data)) > 8000:
                    item['result'] = {**result, 'result': {'history_truncated': True,
                        'message': 'Query again for current data; the original response exceeded context limits.'}}
            tools.append(item)
        item = {'run_id': str(turn.run_id), 'question': turn.question,
                'assistant_text': turn.assistant_text[:8000], 'status': turn.status, 'tools': tools}
        size = len(json.dumps(item, ensure_ascii=False))
        if size > remaining:
            break
        selected.append(item)
        remaining -= size
    return list(reversed(selected))


def owned_conversations(request):
    return AssistantConversation.objects.filter(owner=request.user, expires_at__gt=timezone.now())


class LatestConversationView(HistoryView):
    serializer_classes = {'get': EmptySerializer}

    def get(self, request):
        conversation = owned_conversations(request).order_by('-updated_at').first()
        return FdcJsonResponse(True, result={
            'conversation_id': str(conversation.id) if conversation else None,
            'turns': packed_history(conversation) if conversation else [],
        })


class ConversationDetailView(HistoryView):
    serializer_classes = {'get': EmptySerializer}

    def get(self, request, conversation_id):
        conversation = owned_conversations(request).filter(id=conversation_id).first()
        if not conversation:
            return failure('Conversation not found or expired.', 404)
        return FdcJsonResponse(True, result={'conversation_id': str(conversation.id), 'turns': packed_history(conversation)})


class StartTurnView(InternalHistoryView):
    serializer_classes = {'post': StartSerializer}

    def post(self, request):
        data, now = request.validated_data, timezone.now()
        with transaction.atomic():
            if data.get('conversation_id'):
                conversation = owned_conversations(request).filter(id=data['conversation_id']).first()
                if not conversation:
                    return failure('Conversation not found or expired.', 404)
            else:
                conversation = AssistantConversation.objects.create(owner=request.user,
                    expires_at=now + timedelta(days=settings.ASSISTANT_HISTORY_RETENTION_DAYS))
            claimed = AssistantConversation.objects.filter(id=conversation.id).filter(
                Q(active_run_id__isnull=True) | Q(lease_expires_at__lte=now),
            ).update(active_run_id=data['run_id'], lease_expires_at=now + timedelta(minutes=3), updated_at=now)
            if not claimed:
                return failure('Another response is still running in this conversation.', 409)
            conversation.turns.filter(status='running').update(status='interrupted', finished_at=now)
            history = packed_history(conversation)
            AssistantTurn.objects.create(conversation=conversation, run_id=data['run_id'],
                request_id=data['request_id'], question=data['question'])
        return FdcJsonResponse(True, result={'conversation_id': str(conversation.id), 'history': history})


class RecordToolView(InternalHistoryView):
    serializer_classes = {'post': ToolSerializer}

    def post(self, request, run_id):
        data = request.validated_data
        with transaction.atomic():
            turn = AssistantTurn.objects.select_for_update().filter(
                run_id=run_id, conversation__in=owned_conversations(request)).first()
            if not turn:
                return failure('Turn not found or expired.', 404)
            existing = turn.tools.filter(call_id=data['call_id']).first()
            if data['phase'] == 'started':
                if turn.status != 'running' or turn.conversation.active_run_id != run_id:
                    return failure('Turn is no longer active.', 409)
                if existing:
                    return failure('This tool call has already started.', 409)
                if turn.tools.count() >= 32:
                    return failure('This turn reached the tool history limit.', 409)
                AssistantToolCall.objects.create(turn=turn, call_id=data['call_id'], name=data['name'],
                    arguments=data['arguments'])
            else:
                if not existing or existing.name != data['name']:
                    return failure('Matching tool call not found.', 409)
                if existing.status != 'running':
                    return failure('Tool result has already been recorded.', 409)
                existing.result = data.get('result')
                existing.status = 'succeeded' if (existing.result or {}).get('ok') else 'failed'
                existing.save(update_fields=['result', 'status'])
        return FdcJsonResponse(True, result={'recorded': True})


class FinishTurnView(InternalHistoryView):
    serializer_classes = {'post': FinishSerializer}

    def post(self, request, run_id):
        data = request.validated_data
        with transaction.atomic():
            turn = AssistantTurn.objects.select_for_update().filter(run_id=run_id, conversation__in=owned_conversations(request)).first()
            if not turn:
                return failure('Turn not found or expired.', 404)
            if turn.status == 'running':
                turn.assistant_text, turn.status, turn.finished_at = data['assistant_text'], data['status'], timezone.now()
                turn.save(update_fields=['assistant_text', 'status', 'finished_at'])
            AssistantConversation.objects.filter(id=turn.conversation_id, active_run_id=run_id).update(
                active_run_id=None, lease_expires_at=None)
        return FdcJsonResponse(True, result={'saved': True})
