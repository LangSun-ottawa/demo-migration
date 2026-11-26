"""Opt-in live Pi authorization smoke test; never part of the offline test suite."""
import json
import secrets
from uuid import uuid4

import httpx
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from demoapp.models import (
    AdapterConfig, AdminProfile, AdminUserRecord, AssistantToolCall, ManagedInstance,
)


class Command(BaseCommand):
    help = 'Verify real Pi attempts a create, Django denies a readonly session, and no business rows are added.'

    def handle(self, *args, **options):
        # Intentionally loopback-only: do not provision accounts against arbitrary remote services.
        django_url, gateway_url = 'http://127.0.0.1:8001', 'http://127.0.0.1:8002'
        models = (AdminProfile, AdminUserRecord, ManagedInstance, AdapterConfig)
        suffix = uuid4().hex
        password = secrets.token_urlsafe(32)
        user = get_user_model().objects.create_user(f'verify_ro_{suffix[:16]}', password=password)
        profile_name = f'Readonly proof {suffix}'
        browser = httpx.Client(timeout=100)
        try:
            readonly, _ = Group.objects.get_or_create(name='feature:demo_setup:readonly')
            user.groups.add(readonly)
            if user.is_superuser or user.groups.count() != 1:
                raise CommandError('Test identity must have only the readonly group.')
            health = browser.get(gateway_url + '/health')
            health.raise_for_status()
            if health.json().get('assistant_provider') != 'pi':
                raise CommandError('This live check requires ASSISTANT_PROVIDER=pi; deterministic is not a Pi verification.')
            browser.get(django_url + '/api/demo/auth/session').raise_for_status()
            response = browser.post(django_url + '/api/demo/auth/login', json={
                'username': user.username, 'password': password,
            }, headers={'X-CSRFToken': browser.cookies['csrftoken']})
            response.raise_for_status()
            if not response.json().get('result', {}).get('authenticated'):
                raise CommandError('Django did not establish the test session.')
            read = browser.get(django_url + '/api/demo/secure/setup')
            read.raise_for_status()
            before = tuple(model.objects.count() for model in models)
            response = browser.post(gateway_url + '/assistant/stream', json={
                'question': f'Create an Admin Profile named "{profile_name}" with readwrite access. Please create it now.',
                'page_state': {'route': '/new/setup'},
            })
            response.raise_for_status()
            events = []
            for block in response.text.strip().split('\n\n'):
                kind, payload = None, []
                for line in block.splitlines():
                    if line.startswith('event: '):
                        kind = line[7:]
                    elif line.startswith('data: '):
                        payload.append(line[6:])
                if kind and payload:
                    events.append((kind, json.loads('\n'.join(payload))))
            meta = next((data for kind, data in events if kind == 'meta'), {})
            if meta.get('provider') != 'pi':
                raise CommandError('Response did not identify a real Pi run.')
            starts = {data['call_id'] for kind, data in events
                if kind == 'tool_start' and data.get('name') == 'create_admin_profile'}
            results = [data for kind, data in events if kind == 'tool_result'
                and data.get('name') == 'create_admin_profile' and data.get('call_id') in starts]
            if not results:
                raise CommandError('Pi did not attempt create_admin_profile; this run cannot prove API write denial.')
            for result in results:
                error = result.get('error') or {}
                if result.get('ok') or error.get('code') != 'django_forbidden' or error.get('status_code') != 403:
                    raise CommandError('Expected a failed create tool result with django_forbidden / 403.')
                stored = AssistantToolCall.objects.get(turn__run_id=meta['run_id'], call_id=result['call_id'])
                if stored.status != 'failed' or stored.result.get('error', {}).get('status_code') != 403:
                    raise CommandError('Durable Broker history does not corroborate the failed call.')
            if tuple(model.objects.count() for model in models) != before or AdminProfile.objects.filter(name=profile_name).exists():
                raise CommandError('Business rows changed during verification; inspect DB before claiming write denial.')
            if any(kind == 'error' for kind, _ in events):
                raise CommandError('The run also produced a stream error; tool denial was observed but the full flow did not complete cleanly.')
            if not any(kind == 'done' and data.get('status') == 'completed' for kind, data in events):
                raise CommandError('The Pi run did not complete.')
            self.stdout.write('PASS: readonly session GET setup -> 200')
            self.stdout.write('PASS: real Pi -> create_admin_profile -> Broker -> Django 403')
            self.stdout.write('PASS: SSE tool_result ok=false, django_forbidden, status_code=403')
            self.stdout.write('PASS: durable tool history status=failed; all four business table counts unchanged')
            self.stdout.write(f"request_id={meta['request_id']} run_id={meta['run_id']}")
            answer = ''.join(data.get('text', '') for kind, data in events if kind == 'delta')
            self.stdout.write(f'Pi answer: {answer}')
        except httpx.HTTPStatusError as exc:
            raise CommandError(f'Live check HTTP {exc.response.status_code} at {exc.request.url.path}.') from None
        except (httpx.HTTPError, ValueError, KeyError, AssistantToolCall.DoesNotExist) as exc:
            # No raw HTTP headers, Cookie or credential values in diagnostics.
            raise CommandError(f'Live readonly verification failed ({type(exc).__name__}). Check local services.') from None
        finally:
            try:
                csrf = browser.cookies.get('csrftoken')
                if csrf:
                    browser.post(django_url + '/api/demo/auth/logout', headers={'X-CSRFToken': csrf}, timeout=5)
            except httpx.HTTPError:
                pass
            finally:
                browser.close()
                # Delete only the newly-created test identity; its history cascades.
                user.delete()
                self.stdout.write('Temporary test identity and conversation history removed; existing users/data untouched.')
