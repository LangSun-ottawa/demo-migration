from demoapp.definitions.fdc_http import ERROR_CODE, HTTP_STATUS_CODE
from demoapp.fdc_frame.response import FdcJsonResponse


class DemoAuthenticationMiddleware:
    """Protect only the architecture-lab APIs so the original demo stays public."""

    secure_prefix = '/api/demo/secure/'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.fdc_trace = [
            {
                'stage': 'authentication',
                'detail': (
                    f'Django AuthenticationMiddleware resolved '
                    f'{request.user.username if request.user.is_authenticated else "AnonymousUser"}'
                ),
            }
        ]
        if request.path.startswith(self.secure_prefix) and not request.user.is_authenticated:
            request.fdc_trace.append(
                {'stage': 'authentication', 'detail': 'Request stopped before view dispatch'}
            )
            return FdcJsonResponse(
                False,
                message='Authentication required.',
                errors=[
                    {
                        'code': ERROR_CODE.VALIDATION.value,
                        'message': 'Login before calling a protected endpoint.',
                    }
                ],
                result={'trace': request.fdc_trace},
                http_code=HTTP_STATUS_CODE.UNAUTHORIZED.value,
            )

        if request.path.startswith(self.secure_prefix):
            request.fdc_trace.append(
                {'stage': 'authentication', 'detail': 'Authenticated request may continue'}
            )
        return self.get_response(request)
