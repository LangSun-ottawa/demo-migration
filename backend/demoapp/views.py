from pathlib import Path

from django.conf import settings
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.clickjacking import xframe_options_sameorigin

from demoapp.api.views import MOCK_RECORDS


def _discover_frontend_assets():
    build_dir = Path(settings.BASE_DIR) / 'static' / 'frontend' / 'browser'
    asset_prefix = f"{settings.STATIC_URL}frontend/browser"
    if not build_dir.exists():
        build_dir = Path(settings.BASE_DIR) / 'static' / 'frontend'
        asset_prefix = f"{settings.STATIC_URL}frontend"

    stylesheets = []
    scripts = []
    if build_dir.exists():
        stylesheets = sorted(
            f"{asset_prefix}/{asset.name}"
            for asset in build_dir.glob('*.css')
            if asset.is_file()
        )
        script_assets = [asset for asset in build_dir.glob('*.js') if asset.is_file()]
        script_order = {'runtime': 0, 'polyfills': 1, 'main': 2}
        script_assets.sort(
            key=lambda asset: (
                next(
                    (
                        order
                        for prefix, order in script_order.items()
                        if asset.name.startswith(prefix)
                    ),
                    99,
                ),
                asset.name,
            )
        )
        scripts = [f"{asset_prefix}/{asset.name}" for asset in script_assets]

    return {'stylesheets': stylesheets, 'scripts': scripts}


@xframe_options_sameorigin
def legacy_report_view(request):
    return render(request, 'demoapp/legacy_report.html', {'records': MOCK_RECORDS})


@ensure_csrf_cookie
def spa_shell_view(request):
    return render(request, 'demoapp/spa_shell.html', _discover_frontend_assets())
