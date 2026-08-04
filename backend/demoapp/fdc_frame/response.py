import json

from django.http import HttpResponse

from demoapp.definitions.fdc_http import ERROR_CODE, HTTP_STATUS_CODE, RETURN_CODE


def FdcJsonResponse(success, message='', result=None, errors=None, http_code=None, redirect=''):
    errors = errors or []
    if success:
        payload = {'status': {'return_code': RETURN_CODE.SUCCESS.value}}
        if message:
            payload['status']['message'] = message
        if result is not None:
            payload['result'] = result
        return HttpResponse(
            json.dumps(payload, indent=2),
            status=HTTP_STATUS_CODE.SUCCESS.value,
            content_type='application/json',
        )

    status_code = http_code or HTTP_STATUS_CODE.BUSINESS_ERROR.value
    payload = {'status': {'return_code': RETURN_CODE.FAILURE.value}}
    if redirect and status_code in (
        HTTP_STATUS_CODE.SEE_OTHER_REDIRECT.value,
        HTTP_STATUS_CODE.REDIRECT.value,
    ):
        payload['status']['redirect'] = redirect
    if message:
        payload['status']['message'] = message
    if result is not None:
        payload['result'] = result
    if errors:
        payload['error'] = []
        for error in errors:
            entry = {}
            if 'code' in error:
                entry['code'] = error['code']
                if (
                    status_code == HTTP_STATUS_CODE.BUSINESS_ERROR.value
                    and error['code'] == ERROR_CODE.SYSTEM.value
                ):
                    status_code = HTTP_STATUS_CODE.SYSTEM_ERROR.value
            if 'message' in error:
                entry['message'] = error['message']
            payload['error'].append(entry)
    return HttpResponse(
        json.dumps(payload, indent=2),
        status=status_code,
        content_type='application/json',
    )
