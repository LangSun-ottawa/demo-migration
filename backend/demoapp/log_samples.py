"""Fictional normalized demo logs, not captured Fortinet/device telemetry."""
import json

SCENARIOS = {
    'policy_block': {'name': 'Simulated policy-change incident', 'label': 'Policy block'},
    'normal': {'name': 'Simulated observation set A', 'label': 'Normal observations'},
    'insufficient': {'name': 'Simulated observation set B', 'label': 'Insufficient evidence'},
}


def sample_log_text(scenario='policy_block'):
    if scenario not in SCENARIOS:
        raise ValueError('Unknown sample scenario.')
    rows = []
    def event(time, kind, action, message, **extra):
        rows.append({'device': 'Demo Gateway A', 'device_ip': '192.0.2.1', 'device_type': 'simulated-firewall',
            'occurred_at': f'2026-11-25T{time}:00Z', 'kind': kind, 'action': action, 'message': message, **extra})
    if scenario == 'normal':
        for minute in ('14:00', '14:05', '14:10'):
            event(minute, 'traffic', 'allow', 'Synthetic session permitted; reply packets observed.',
                src_ip='192.0.2.10', dst_ip='198.51.100.20', dst_port=443, session_id='normal-' + minute, policy_id='P10')
        event('14:02', 'threat', 'blocked', 'Synthetic test signature detected; traffic blocked.',
            src_ip='192.0.2.77', dst_ip='203.0.113.99', dst_port=80, threat='SYNTHETIC-TEST-SIGNATURE', policy_id='P88')
        return '\n'.join(json.dumps(row) for row in rows)
    if scenario == 'insufficient':
        event('13:45', 'traffic', 'allow', 'Session permitted.',
            src_ip='192.0.2.10', dst_ip='198.51.100.20', dst_port=443, session_id='baseline-only', policy_id='P10')
        event('14:02', 'traffic', 'allow', 'UDP DNS query permitted.',
            src_ip='192.0.2.55', dst_ip='203.0.113.53', dst_port=53, session_id='noise-only', policy_id='P99')
        event('14:03', 'threat', 'blocked', 'Synthetic test signature detected; traffic blocked.',
            src_ip='192.0.2.77', dst_ip='203.0.113.99', dst_port=80, threat='SYNTHETIC-TEST-SIGNATURE', policy_id='P88')
        return '\n'.join(json.dumps(row) for row in rows)
    event('13:55', 'traffic', 'allow', 'Session permitted.',
        src_ip='192.0.2.10', dst_ip='198.51.100.20', dst_port=443, session_id='before-1', policy_id='P10')
    event('13:58', 'traffic', 'allow', 'UDP DNS query permitted.',
        src_ip='192.0.2.55', dst_ip='203.0.113.53', dst_port=53, session_id='noise-1', policy_id='P99')
    event('14:00', 'config_change', 'policy_change', 'Policy P10 action changed from allow to deny; operator demo-operator.', policy_id='P10')
    event('14:01', 'traffic', 'deny', 'Connection blocked by policy P10.',
        src_ip='192.0.2.10', dst_ip='198.51.100.20', dst_port=443, session_id='after-1', policy_id='P10')
    event('14:02', 'traffic', 'deny', 'Retry blocked by policy P10.',
        src_ip='192.0.2.10', dst_ip='198.51.100.20', dst_port=443, session_id='after-2', policy_id='P10')
    event('14:03', 'threat', 'blocked', 'Synthetic test signature detected; traffic blocked.',
        src_ip='192.0.2.77', dst_ip='203.0.113.99', dst_port=80, threat='SYNTHETIC-TEST-SIGNATURE', policy_id='P88')
    return '\n'.join(json.dumps(row) for row in rows)
