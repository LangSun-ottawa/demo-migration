"""SAML authentication ends here. Business authorization remains FeaturePermission."""
import hashlib
import json
import time
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import path
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.errors import OneLogin_Saml2_Error, OneLogin_Saml2_ValidationError
from onelogin.saml2.settings import OneLogin_Saml2_Settings
from lxml.etree import XMLSyntaxError

from demoapp.models import SamlIdentity, SamlReplay


def saml_settings():
    base = settings.SAML_SP_BASE_URL.rstrip('/') + '/api/demo/auth/saml'
    return {
        'strict': True, 'debug': False,
        'sp': {
            'entityId': base + '/metadata/',
            'assertionConsumerService': {'url': base + '/acs/', 'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST'},
            'NameIDFormat': 'urn:oasis:names:tc:SAML:2.0:nameid-format:persistent',
        },
        'idp': json.loads(settings.SAML_IDP_CONFIG_FILE.read_text()),
        'security': {
            'wantAssertionsSigned': True, 'wantMessagesSigned': True,
            'wantNameId': True, 'rejectDeprecatedAlgorithm': True,
            'authnRequestsSigned': False, 'requestedAuthnContext': False,
        },
    }


def toolkit(request):
    return OneLogin_Saml2_Auth({
        'https': 'on' if request.is_secure() else 'off',
        'http_host': request.get_host(),
        'script_name': request.path,
        'get_data': request.GET.copy(), 'post_data': request.POST.copy(),
    }, saml_settings())


def unavailable():
    return HttpResponse('SAML is not configured. Use password login or see docs/SAML.md.', status=503)


@require_GET
def start(request):
    if not settings.SAML_ENABLED or not settings.SAML_IDP_CONFIG_FILE.exists():
        return unavailable()
    auth = toolkit(request)
    destination = auth.login()
    request.session['saml_pending'] = {'id': auth.get_last_request_id(), 'started': time.time()}
    response = HttpResponseRedirect(destination)
    response['Cache-Control'] = 'no-store'
    return response


def provision(issuer, subject, attributes):
    """Map only explicit trusted IdP groups; never link a local account by email."""
    digest = hashlib.sha256(f'{issuer}\0{subject}'.encode()).hexdigest()
    identity = SamlIdentity.objects.select_related('user').filter(issuer=issuer, subject=subject).first()
    if identity:
        user = identity.user
    else:
        user = get_user_model().objects.create_user(username='saml_' + digest, password=None)
        SamlIdentity.objects.create(issuer=issuer, subject=subject, user=user)
    if not user.is_active or user.is_staff or user.is_superuser:
        raise ValueError('SSO identity is disabled or reserved.')
    claims = attributes.get('groups', [])
    mapped = {settings.SAML_GROUP_MAPPING[value] for value in claims if value in settings.SAML_GROUP_MAPPING}
    managed = Group.objects.filter(name__in=settings.SAML_GROUP_MAPPING.values())
    user.groups.remove(*managed)
    for name in mapped:
        group, _ = Group.objects.get_or_create(name=name)
        user.groups.add(group)
    return user


# Only this protocol callback is CSRF-exempt: signed SAML + session-bound request ID
# replaces the form CSRF token. Business APIs remain unchanged.
@csrf_exempt
@require_POST
def acs(request):
    if not settings.SAML_ENABLED or not settings.SAML_IDP_CONFIG_FILE.exists():
        return unavailable()
    pending = request.session.pop('saml_pending', None)
    if not pending or not 0 <= time.time() - pending['started'] <= 300:
        return HttpResponse('SAML login expired or was not initiated in this browser. Try again.', status=400)
    try:
        auth = toolkit(request)
        auth.process_response(request_id=pending['id'])
        if (auth.get_errors() or not auth.is_authenticated()
                or auth.get_last_response_in_response_to() != pending['id']):
            raise ValueError('Invalid SAML response')
        subject = auth.get_nameid()
        assertion = auth.get_last_assertion_id()
        expires = auth.get_last_assertion_not_on_or_after()
        issuer = saml_settings()['idp']['entityId']
        if not subject or len(subject) > 500 or not assertion or not expires:
            raise ValueError('Incomplete SAML assertion')
        with transaction.atomic():
            SamlReplay.objects.filter(expires_at__lt=timezone.now()).delete()
            SamlReplay.objects.create(
                digest=hashlib.sha256(f'{issuer}\0{assertion}'.encode()).hexdigest(),
                # Retain beyond assertion expiry to cover toolkit clock-skew tolerance.
                expires_at=datetime.fromtimestamp(expires + 300, tz=dt_timezone.utc),
            )
            user = provision(issuer, subject, auth.get_attributes())
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    except (ValueError, IntegrityError, XMLSyntaxError, OneLogin_Saml2_Error, OneLogin_Saml2_ValidationError):
        return HttpResponse('SAML login rejected. Start a new login; contact the administrator if it persists.', status=400)
    response = HttpResponseRedirect(settings.SAML_LOGIN_RETURN_URL)
    response['Cache-Control'] = 'no-store'
    return response


@require_GET
def metadata(request):
    if not settings.SAML_ENABLED or not settings.SAML_IDP_CONFIG_FILE.exists():
        return unavailable()
    config = OneLogin_Saml2_Settings(saml_settings())
    xml = config.get_sp_metadata()
    if config.validate_metadata(xml):
        return HttpResponse('Invalid SP metadata configuration.', status=503)
    return HttpResponse(xml, content_type='application/samlmetadata+xml')


urlpatterns = [path('login/', start), path('acs/', acs), path('metadata/', metadata)]
