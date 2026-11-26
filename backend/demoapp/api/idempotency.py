import hashlib
import json
from uuid import UUID

from django.db import IntegrityError, OperationalError, transaction
from rest_framework.exceptions import APIException, ValidationError

from demoapp.api.base import ContractAPIView
from demoapp.fdc_frame.response import FdcJsonResponse
from demoapp.models import CreateOperation


class OperationConflict(APIException):
    status_code = 409
    default_detail = 'Operation key already used with different parameters, or operation is still in progress. Retry the same key.'


class IdempotentCreateView(ContractAPIView):
    """Optional Idempotency-Key, user scoped; mutation + saved result share one transaction."""

    def initial(self, request, *args, **kwargs):
        try:
            super().initial(request, *args, **kwargs)
        except ValidationError:
            # A concurrent request may commit between initial lookup and unique-name validation.
            # Authentication/permissions already ran; only an exact body replay may bypass that race.
            if not request.query_params and self.restore_saved_operation(request):
                return
            raise
        except OperationalError:
            raise OperationConflict()

    def handle_exception(self, exc):
        if isinstance(exc, OperationConflict):
            return FdcJsonResponse(False, errors=[{'code': 'BE', 'message': str(exc.detail)}], http_code=409)
        return super().handle_exception(exc)

    def restore_saved_operation(self, request):
        raw_key = request.headers.get('Idempotency-Key')
        request.saved_operation = None
        request.operation_key = None
        if not raw_key:
            return False
        try:
            request.operation_key = UUID(raw_key)
        except ValueError:
            raise ValidationError({'Idempotency-Key': 'Expected a UUID.'})
        canonical = json.dumps({'resource': self.resource, 'data': request.data}, sort_keys=True, separators=(',', ':'))
        request.operation_fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
        saved = CreateOperation.objects.filter(owner=request.user, key=request.operation_key).first()
        if saved:
            if saved.fingerprint != request.operation_fingerprint or saved.result is None:
                raise OperationConflict()
            request.saved_operation = saved.result
            return True  # Skip duplicate-name validation only for a previously authorized exact replay.
        return False

    def post(self, request):
        from demoapp.api.views import build_creation_result
        if request.saved_operation is not None:
            return FdcJsonResponse(True, result={**request.saved_operation, 'operation_replayed': True})
        try:
            with transaction.atomic():
                operation = None
                if request.operation_key:
                    operation, created = CreateOperation.objects.get_or_create(
                        owner=request.user, key=request.operation_key,
                        defaults={'fingerprint': request.operation_fingerprint, 'resource': self.resource})
                    if not created:
                        if operation.fingerprint != request.operation_fingerprint or operation.result is None:
                            raise OperationConflict()
                        return FdcJsonResponse(True, result={**operation.result, 'operation_replayed': True})
                record = self.model.objects.create(**request.validated_data)
                result = build_creation_result(self.resource, record.id)
                if operation:
                    result['operation_id'] = str(operation.key)
                    operation.result = result
                    operation.save(update_fields=['result'])
                return FdcJsonResponse(True, result=result)
        except (IntegrityError, OperationalError):
            # Includes SQLite lock contention: never retry a write implicitly.
            raise OperationConflict()
