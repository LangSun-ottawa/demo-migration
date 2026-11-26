import { evidenceTimeline } from './evidence-timeline.component';

describe('Evidence timeline', () => {
  const event = { id: 1, occurred_at: '2026-11-25T14:01:00Z', device: 'Gateway', action: 'deny',
    message: '<script>untrusted</script>', src_ip: '192.0.2.10', dst_ip: '198.51.100.20' };
  it('uses only successful structured query data, orders events and retains simulation label', () => {
    const timeline = evidenceTimeline('query_log_events', { dataset_id: 'dataset', simulated: true, truncated: true,
      events: [event, { ...event, id: 2, occurred_at: '2026-11-25T14:00:00Z' }, { id: 'fake' }] });
    expect(timeline?.events.map((e) => e.id)).toEqual([2, 1]);
    expect(timeline?.simulated).toBeTrue();
    expect(timeline?.truncated).toBeTrue();
    expect(timeline?.events[1].message).toBe('<script>untrusted</script>'); // Rendered by text interpolation, not innerHTML.
  });
  it('does not infer events from model prose or unrelated tool results', () => {
    expect(evidenceTimeline('create_instance', { dataset_id: 'dataset', events: [event] })).toBeNull();
    expect(evidenceTimeline('query_log_events', { text: 'Event #1 was blocked' })).toBeNull();
  });
});
