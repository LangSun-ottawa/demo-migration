from django.urls import path, re_path

from demoapp.api.urls import urlpatterns as api_urlpatterns
from demoapp.views import legacy_report_view, spa_shell_view

urlpatterns = [
    path('legacy/report/', legacy_report_view, name='legacy-report'),
    re_path(r'^new(?:/.*)?$', spa_shell_view, name='spa-shell'),
]

urlpatterns += api_urlpatterns
