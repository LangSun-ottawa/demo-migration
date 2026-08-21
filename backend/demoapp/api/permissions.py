from enum import StrEnum

from rest_framework.exceptions import NotAuthenticated
from rest_framework.permissions import BasePermission


class FeaturePrivilege(StrEnum):
    NONE = 'none'
    READONLY = 'readonly'
    READWRITE = 'readwrite'


FEATURE_MODEL_COMPARISON = 'model_comparison'
FEATURE_SECURITY_INSPECTION = 'security_inspection'
FEATURE_VM_ASSOCIATION = 'vm_association'


def feature_group_name(feature_key, privilege):
    return f'feature:{feature_key}:{FeaturePrivilege(privilege).value}'


def get_user_feature_privilege(user, feature_key):
    if not user or not user.is_authenticated:
        return FeaturePrivilege.NONE
    if user.is_superuser:
        return FeaturePrivilege.READWRITE

    group_names = set(
        user.groups.filter(
            name__in=(
                feature_group_name(feature_key, FeaturePrivilege.READONLY),
                feature_group_name(feature_key, FeaturePrivilege.READWRITE),
            )
        ).values_list('name', flat=True)
    )
    if feature_group_name(feature_key, FeaturePrivilege.READWRITE) in group_names:
        return FeaturePrivilege.READWRITE
    if feature_group_name(feature_key, FeaturePrivilege.READONLY) in group_names:
        return FeaturePrivilege.READONLY
    return FeaturePrivilege.NONE


def privilege_allows(actual, required):
    actual = FeaturePrivilege(actual)
    required = FeaturePrivilege(required)
    if required is FeaturePrivilege.READONLY:
        return actual in (FeaturePrivilege.READONLY, FeaturePrivilege.READWRITE)
    if required is FeaturePrivilege.READWRITE:
        return actual is FeaturePrivilege.READWRITE
    return False


class FeaturePermission(BasePermission):
    """Authorize an APIView from explicit feature and method metadata."""

    message = 'Feature permission denied.'

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            self._trace(request, 'AnonymousUser has no feature grants')
            raise NotAuthenticated('Login before calling this protected endpoint.')

        feature_key = getattr(view, 'feature_key', None)
        method_permissions = getattr(view, 'method_permissions', {})
        required = method_permissions.get(request.method.lower())

        # Fail closed when a protected view forgets either declaration.
        if not feature_key or required is None:
            self.message = 'Protected view has no permission contract for this method.'
            self._trace(request, self.message)
            return False

        required = FeaturePrivilege(required)
        actual = get_user_feature_privilege(request.user, feature_key)
        request.feature_permission = {
            'feature_key': feature_key,
            'required': required.value,
            'actual': actual.value,
        }

        allowed = privilege_allows(actual, required)
        decision = 'allowed' if allowed else 'denied'
        self._trace(
            request,
            f'{feature_key}: {actual.value} vs required {required.value} -> {decision}',
        )
        if not allowed:
            self.message = (
                f'{feature_key} requires {required.value} privilege; '
                f'the current grant is {actual.value}.'
            )
        return allowed

    @staticmethod
    def _trace(request, detail):
        if not hasattr(request, 'fdc_trace'):
            request.fdc_trace = []
        request.fdc_trace.append({'stage': 'permission', 'detail': detail})

