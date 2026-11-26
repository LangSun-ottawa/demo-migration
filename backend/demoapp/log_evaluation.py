"""Independent, conservative evaluation checks. Never imported by log APIs or Pi.

These are structural evidence checks, NOT a general semantic/root-cause grader.
The explanation still needs human review against the separate scenario oracle.
"""
import json
import re
from datetime import datetime, timezone


QUESTION = ('请调查选中日志中 2026-11-25 14:00–14:10 UTC，192.0.2.10 到 '
    '198.51.100.20:443 的通信是否异常。引用事件 ID，排除无关告警，区分事实与推测；证据不够时请追问。')
READ_TOOLS = {'get_log_schema', 'list_log_datasets', 'find_device', 'query_log_events',
    'get_event_details', 'get_related_events', 'ask_user_question'}
REVIEW_ORACLES = {
    'normal': 'Target sessions are allowed, with simulated reply observations. No target denial or change is recorded. Do not claim guaranteed application health or blame an unrelated threat.',
    'policy_block': 'Same reporting device/P10: allow before change, allow-to-deny change, then target denials. Cite change and denial evidence. Distinguish observed policy block from why/whether the change was authorized.',
    'insufficient': 'Only an earlier target baseline; requested 14:00–14:10 window contains unrelated traffic/threats. Do not infer health, policy block or infection. Ask for missing target-window logs or endpoint/time confirmation.',
}
WINDOW_START = datetime(2026, 11, 25, 14, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 11, 25, 14, 10, tzinfo=timezone.utc)


def parse_sse(text):
    events = []
    for block in text.replace('\r\n', '\n').split('\n\n'):
        kind, lines = None, []
        for line in block.splitlines():
            if line.startswith('event:'):
                kind = line[6:].strip()
            elif line.startswith('data:'):
                lines.append(line[5:].lstrip())
        if kind and lines:
            events.append((kind, json.loads('\n'.join(lines))))
    return events


def cited_event_ids(text):
    text = text.replace('**', '').replace('`', '')
    ids = set()
    pattern = r'(?:event(?:[ \t]+IDs?)?|事件(?:[ \t]*IDs?)?|证据)[ \t]*[:：#]?[ \t]*(\d+(?:[ ,，、]+#?\d+)*)|#(\d+)'
    for match in re.finditer(pattern, text, re.IGNORECASE):
        ids.update(int(value) for value in re.findall(r'\d+', match.group(1) or match.group(2)))
    return ids


def evaluate_run(scenario, dataset_id, rows, tools, stream_events):
    if scenario not in REVIEW_ORACLES:
        raise ValueError('Unknown evaluation scenario.')
    dataset_id = str(dataset_id)
    row_ids = {row['id'] for row in rows}
    seen, raw_seen = set(), set()
    for tool in tools:
        result = tool.get('result') or {}
        data = result.get('result') or {}
        if not result.get('ok'):
            continue
        for event in data.get('events', []):
            if str(event.get('dataset_id')) == dataset_id:
                seen.add(event['id'])
        event = data.get('event')
        if isinstance(event, dict) and str(event.get('dataset_id')) == dataset_id:
            seen.add(event['id'])
            if 'raw' in event:
                raw_seen.add(event['id'])
    answer = ''.join(data.get('text', '') for kind, data in stream_events if kind == 'delta')
    citations = cited_event_ids(answer)
    target = [row for row in rows if row['src_ip'] == '192.0.2.10' and row['dst_ip'] == '198.51.100.20'
        and row['dst_port'] == 443 and WINDOW_START <= datetime.fromisoformat(row['occurred_at'].replace('Z', '+00:00')) <= WINDOW_END]
    target_ids = {row['id'] for row in target}
    change_ids = {row['id'] for row in rows if row['kind'] == 'config_change' and row['policy_id'] == 'P10'}
    questions = [tool for tool in tools if tool['name'] == 'ask_user_question' and (tool.get('result') or {}).get('ok')]
    queries = [tool for tool in tools if tool['name'] == 'query_log_events' and str(tool['arguments'].get('dataset_id')) == dataset_id]
    checks = {
        'real_pi_run': any(kind == 'meta' and data.get('provider') == 'pi' for kind, data in stream_events),
        'completed_without_stream_error': any(kind == 'done' and data.get('status') == 'completed' for kind, data in stream_events)
            and not any(kind == 'error' for kind, _ in stream_events),
        'read_tools_only': bool(tools) and all(tool['name'] in READ_TOOLS for tool in tools),
        'all_recorded_tools_succeeded': bool(tools) and all(tool['status'] == 'succeeded' and (tool.get('result') or {}).get('ok') for tool in tools),
        'selected_dataset_queried': bool(queries),
        'requested_window_queried': any(
            datetime.fromisoformat(tool['arguments']['start'].replace('Z', '+00:00')) <= WINDOW_START and
            datetime.fromisoformat(tool['arguments']['end'].replace('Z', '+00:00')) >= WINDOW_END for tool in queries),
        'nonempty_response': bool(answer.strip()),
        'citations_are_observed_ids': citations <= (seen & row_ids),
    }
    if scenario in ('normal', 'policy_block'):
        checks['target_evidence_cited'] = bool(citations & target_ids)
        checks['target_original_record_checked'] = bool(raw_seen & target_ids)
    if scenario == 'policy_block':
        checks['policy_change_evidence_cited'] = bool(citations & change_ids)
    if scenario == 'insufficient':
        checks['oracle_has_no_target_window_evidence'] = not target_ids
        checks['structured_clarification_requested'] = any(
            question['arguments'].get('question', '').strip() and question['arguments'].get('missing_fields')
            for question in questions)
    return {'scenario': scenario, 'structural_pass': all(checks.values()), 'checks': checks,
        'cited_event_ids': sorted(citations), 'observed_event_ids': sorted(seen),
        'human_review_oracle': REVIEW_ORACLES[scenario], 'answer': answer}
