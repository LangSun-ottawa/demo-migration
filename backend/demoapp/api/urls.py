from django.urls import path

from demoapp.api.views import (
    ContractCatalogView,
    EchoView,
    ErrorRedirectView,
    LoginView,
    LogoutView,
    ModelComparisonView,
    RebootRedirectView,
    SearchView,
    SecurityInspectionView,
    SessionView,
    SystemOperationStatusView,
    TemporaryRedirectView,
    UploadView,
    VmAssociationContextView,
)

urlpatterns = [
    path('api/demo/auth/login', LoginView.as_view(), name='api-auth-login'),
    path('api/demo/auth/logout', LogoutView.as_view(), name='api-auth-logout'),
    path('api/demo/auth/session', SessionView.as_view(), name='api-auth-session'),
    path('api/demo/contracts', ContractCatalogView.as_view(), name='api-contracts'),
    path('api/demo/secure/security/inspect', SecurityInspectionView.as_view(), name='api-security-inspect'),
    path('api/demo/secure/models', ModelComparisonView.as_view(), name='api-model-comparison'),
    path(
        'api/demo/secure/page-context',
        VmAssociationContextView.as_view(),
        name='api-vm-association-context',
    ),
    path('api/demo/echo', EchoView.as_view(), name='api-echo'),
    path('api/demo/search', SearchView.as_view(), name='api-search'),
    path('api/demo/upload', UploadView.as_view(), name='api-upload'),
    path('api/demo/redirect/temp', TemporaryRedirectView.as_view(), name='api-redirect-temp'),
    path('api/demo/redirect/error', ErrorRedirectView.as_view(), name='api-redirect-error'),
    path('api/demo/system/reboot', RebootRedirectView.as_view(), name='api-system-reboot'),
    path('api/demo/system/status', SystemOperationStatusView.as_view(), name='api-system-status'),
]
