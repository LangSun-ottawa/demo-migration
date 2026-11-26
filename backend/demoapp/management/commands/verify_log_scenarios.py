"""Opt-in real-model evaluation against independent, fictional log datasets."""
import secrets
from uuid import uuid4

import httpx
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from demoapp.api.log_evidence import event_result
from demoapp.log_evaluation import QUESTION, evaluate_run, parse_sse
from demoapp.log_samples import SCENARIOS
from demoapp.models import AssistantToolCall


class Command(BaseCommand):
    help = 'Run real Pi normal/block/insufficient log scenarios; checks evidence contracts and prints answers for human review.'

    def add_arguments(self, parser):
        parser.add_argument('--scenario', choices=list(SCENARIOS), action='append',
            help='Run selected case(s); default is all three. Uses a temporary readonly investigator.')

    def handle(self, *args, **options):
        django_url, gateway_url = 'http://127.0.0.1:8001', 'http://127.0.0.1:8002'
        selected = list(dict.fromkeys(options['scenario'] or ['normal', 'policy_block', 'insufficient']))
        password = secrets.token_urlsafe(32)
        user = get_user_model().objects.create_user('eval_logs_' + uuid4().hex[:16], password=password)
        browser = httpx.Client(timeout=100)
        failed = []
        try:
            writer = Group.objects.get(name='feature:demo_setup:readwrite')
            reader, _ = Group.objects.get_or_create(name='feature:demo_setup:readonly')
            user.groups.set([writer])
            health = browser.get(gateway_url + '/health')
            health.raise_for_status()
            if health.json().get('assistant_provider') != 'pi':
                raise CommandError('Requires ASSISTANT_PROVIDER=pi. Mock reasoning cannot pass a real-model evaluation.')
            browser.get(django_url + '/api/demo/auth/session').raise_for_status()
            login = browser.post(django_url + '/api/demo/auth/login', json={'username': user.username, 'password': password})
            login.raise_for_status()
            datasets = {}
            for scenario in selected:
                response = browser.post(django_url + '/api/demo/secure/logs/demo', json={'scenario': scenario},
                    headers={'X-CSRFToken': browser.cookies['csrftoken']})
                response.raise_for_status()
                datasets[scenario] = response.json()['result']['dataset']['id']
            # The model operates as readonly; only fixture creation uses write permission.
            user.groups.set([reader])
            before = browser.get(django_url + '/api/demo/secure/setup')
            before.raise_for_status()
            before = before.json()['result']
            for scenario, dataset_id in datasets.items():
                self.stdout.write(f'RUN {scenario} (new conversation, selected dataset only)')
                response = browser.post(gateway_url + '/assistant/stream', json={
                    'question': QUESTION, 'page_state': {'route': '/new/setup', 'mode': 'investigation', 'log_dataset_id': dataset_id}})
                response.raise_for_status()
                events = parse_sse(response.text)
                meta = next((data for kind, data in events if kind == 'meta'), {})
                if not meta.get('run_id'):
                    raise CommandError('No run ID; cannot corroborate actual Broker history.')
                # Never trust model prose/SSE as proof a tool fetched evidence: read real stored outcomes.
                tools = list(AssistantToolCall.objects.filter(turn__run_id=meta['run_id'], turn__conversation__owner=user)
                    .values('name', 'arguments', 'result', 'status'))
                dataset = user.logdataset_set.get(id=dataset_id)
                rows = [event_result(event) for event in dataset.events.select_related('device')]
                report = evaluate_run(scenario, dataset_id, rows, tools, events)
                after = browser.get(django_url + '/api/demo/secure/setup')
                after.raise_for_status()
                report['checks']['business_data_unchanged'] = after.json()['result'] == before
                passed = report['structural_pass'] and report['checks']['business_data_unchanged']
                for name, ok in report['checks'].items():
                    self.stdout.write(f"  {'PASS' if ok else 'FAIL'} {name}")
                self.stdout.write(f"  run_id={meta['run_id']} citations={report['cited_event_ids']}")
                self.stdout.write('HUMAN REVIEW ORACLE (not sent to model): ' + report['human_review_oracle'])
                self.stdout.write('MODEL ANSWER:\n' + report['answer'])
                if not passed:
                    failed.append(scenario)
            if failed:
                raise CommandError('Structural evaluation failed: ' + ', '.join(failed) + '. Review the printed answers; do not mark semantic correctness from keyword matches.')
            self.stdout.write(self.style.SUCCESS('All selected structural checks passed. Human review of facts/hypotheses is still required.'))
        except httpx.HTTPStatusError as exc:
            raise CommandError(f'HTTP {exc.response.status_code} at {exc.request.url.path}; check local services.') from None
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise CommandError(f'Log evaluation failed ({type(exc).__name__}); no credentials printed.') from None
        finally:
            try:
                csrf = browser.cookies.get('csrftoken')
                if csrf:
                    browser.post(django_url + '/api/demo/auth/logout', headers={'X-CSRFToken': csrf}, timeout=5)
            except httpx.HTTPError:
                pass
            finally:
                browser.close()
                user.delete()  # Only this newly-created evaluation identity, datasets and history.
                self.stdout.write('Temporary evaluation identity/datasets/history removed. Existing users and data preserved.')
