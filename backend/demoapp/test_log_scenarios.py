import copy
import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import SimpleTestCase, TestCase

from demoapp.log_evaluation import cited_event_ids, evaluate_run, parse_sse
from demoapp.log_samples import SCENARIOS, sample_log_text


class LogScenarioTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user('scenario-investigator')
        user.groups.add(Group.objects.get(name='feature:demo_setup:readwrite'))
        self.client.force_login(user)

    def test_all_three_cases_are_distinct_owned_idempotent_samples(self):
        ids = set()
        for scenario, count in [('normal', 4), ('policy_block', 6), ('insufficient', 3)]:
            response = self.client.post('/api/demo/secure/logs/demo', {'scenario': scenario}, content_type='application/json')
            self.assertEqual(response.status_code, 200, response.content)
            dataset = response.json()['result']['dataset']
            ids.add(dataset['id'])
            self.assertEqual(dataset['event_count'], count)
            repeated = self.client.post('/api/demo/secure/logs/demo', {'scenario': scenario}, content_type='application/json')
            self.assertEqual(repeated.json()['result']['dataset']['id'], dataset['id'])
        self.assertEqual(len(ids), 3)

    def test_unknown_scenario_cannot_import(self):
        self.assertEqual(self.client.post('/api/demo/secure/logs/demo', {'scenario': 'arbitrary'}, content_type='application/json').status_code, 444)
        self.assertEqual(self.client.post('/api/demo/secure/logs/demo', {'scenario': 'normal', 'root_cause': 'invented'}, content_type='application/json').status_code, 444)

    def test_requested_failure_window_not_silently_replaced_by_earlier_baseline(self):
        response = self.client.post('/api/demo/secure/logs/demo', {'scenario': 'insufficient'}, content_type='application/json')
        dataset_id = response.json()['result']['dataset']['id']
        result = self.client.get('/api/demo/secure/logs/events', {'dataset_id': dataset_id,
            'start': '2026-11-25T14:00:00Z', 'end': '2026-11-25T14:10:00Z', 'ip': '192.0.2.10'}).json()['result']
        self.assertEqual(result['events'], [])
        self.assertFalse(result['truncated'])

    def test_fixture_facts_are_not_a_shared_precomputed_answer(self):
        for scenario in SCENARIOS:
            rows = [json.loads(line) for line in sample_log_text(scenario).splitlines()]
            self.assertFalse(any('root_cause' in row or 'expected_answer' in row for row in rows))
            targets = [row for row in rows if row.get('src_ip') == '192.0.2.10' and row.get('dst_ip') == '198.51.100.20']
            if scenario == 'normal':
                self.assertTrue(all(row['action'] == 'allow' for row in targets))
                self.assertFalse(any(row['kind'] == 'config_change' for row in rows))
            elif scenario == 'insufficient':
                self.assertTrue(all(row['occurred_at'] < '2026-11-25T14:00:00Z' for row in targets))
            else:
                self.assertEqual([row['action'] for row in targets], ['allow', 'deny', 'deny'])


class LogEvaluationCheckerTests(SimpleTestCase):
    def transcript(self, scenario):
        dataset_id = 'dataset-under-test'
        rows = [{'src_ip': None, 'dst_ip': None, 'dst_port': None, 'policy_id': '',
            **json.loads(line), 'id': index + 101, 'dataset_id': dataset_id}
            for index, line in enumerate(sample_log_text(scenario).splitlines())]
        tools = [{'name': 'query_log_events', 'status': 'succeeded',
            'arguments': {'dataset_id': dataset_id, 'start': '2026-11-25T13:40:00Z', 'end': '2026-11-25T14:10:00Z'},
            'result': {'ok': True, 'result': {'events': rows}}}]
        relevant = [row for row in rows if row.get('src_ip') == '192.0.2.10']
        for row in relevant:
            tools.append({'name': 'get_event_details', 'status': 'succeeded', 'arguments': {},
                'result': {'ok': True, 'result': {'event': {**row, 'raw': row}}}})
        answer = 'Simulated observations. ' + ' '.join('事件 ID ' + str(row['id']) for row in rows)
        if scenario == 'insufficient':
            tools.append({'name': 'ask_user_question', 'status': 'succeeded',
                'arguments': {'question': 'Please provide target-window logs or confirm the time range.', 'missing_fields': ['target_window_logs']},
                'result': {'ok': True}})
        events = [('meta', {'provider': 'pi'}), ('delta', {'text': answer}), ('done', {'status': 'completed'})]
        return dataset_id, rows, tools, events

    def test_valid_evidence_contracts_for_each_case(self):
        for scenario in SCENARIOS:
            report = evaluate_run(scenario, *self.transcript(scenario))
            self.assertTrue(report['structural_pass'], report)

    def test_checker_rejects_invented_citation_and_unobserved_evidence(self):
        dataset, rows, tools, events = self.transcript('normal')
        events[1][1]['text'] += ' Event ID 999999'
        report = evaluate_run('normal', dataset, rows, tools, events)
        self.assertFalse(report['checks']['citations_are_observed_ids'])
        self.assertFalse(report['structural_pass'])
        dataset, rows, tools, events = self.transcript('normal')
        report = evaluate_run('normal', dataset, rows, [], events)
        self.assertFalse(report['structural_pass'])

    def test_checker_requires_real_clarification_not_just_uncertain_prose(self):
        args = list(self.transcript('insufficient'))
        args[2] = [tool for tool in args[2] if tool['name'] != 'ask_user_question']
        args[3][1][1]['text'] += ' Insufficient evidence. What happened?'
        self.assertFalse(evaluate_run('insufficient', *args)['checks']['structured_clarification_requested'])

    def test_failed_tools_write_tools_and_missing_window_fail(self):
        for mutation in ('failed', 'write', 'window'):
            dataset, rows, tools, events = copy.deepcopy(self.transcript('normal'))
            if mutation == 'failed':
                tools[0]['status'] = 'failed'
            elif mutation == 'write':
                tools[0]['name'] = 'create_admin_profile'
            else:
                tools[0]['arguments']['end'] = '2026-11-25T13:59:00Z'
            self.assertFalse(evaluate_run('normal', dataset, rows, tools, events)['structural_pass'])

    def test_citation_parser_and_sse_do_not_confuse_dates_for_evidence(self):
        self.assertEqual(cited_event_ids('2026-11-25 **事件 ID 17、#18**; Event ID 23; #29'), {17, 18, 23, 29})
        self.assertEqual(parse_sse('event: delta\r\ndata: {"text":"hello"}\r\n\r\n'), [('delta', {'text': 'hello'})])
