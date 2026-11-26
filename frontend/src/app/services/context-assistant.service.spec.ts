import { parseSseBlock } from './context-assistant.service';

describe('parseSseBlock', () => {
  it('preserves structured results and clarification fields', () => {
    const data = {
      call_id: 'call-result', name: 'create_admin_profile', ok: true,
      summary: 'Created', result: { profiles: [{ id: 6, name: 'test_profile' }] },
    };
    expect(parseSseBlock(`event: tool_result\ndata: ${JSON.stringify(data)}`))
      .toEqual({ type: 'tool_result', data });
    const clarification = {
      call_id: 'call-question', name: 'ask_user_question', ok: true,
      summary: 'Waiting for your reply', question: 'Profile name?', missing_fields: ['name'],
    };
    expect(parseSseBlock(`event: tool_result\ndata: ${JSON.stringify(clarification)}`))
      .toEqual({ type: 'tool_result', data: clarification });
  });

  it('parses a streamed delta event', () => {
    const event = parseSseBlock('event: delta\ndata: {"text":"hello "}');

    expect(event).toEqual({ type: 'delta', data: { text: 'hello ' } });
  });

  it('ignores unsupported or incomplete events', () => {
    expect(parseSseBlock('data: {"text":"missing event"}')).toBeNull();
    expect(parseSseBlock('event: heartbeat\ndata: {}')).toBeNull();
  });

  it('parses tool progress and controlled error events', () => {
    expect(parseSseBlock(
      'event: tool_start\ndata: {"call_id":"call-1","name":"query_vm_context"}',
    )).toEqual({
      type: 'tool_start',
      data: { call_id: 'call-1', name: 'query_vm_context' },
    });
    expect(parseSseBlock(
      'event: tool_result\ndata: {"call_id":"call-1","name":"query_vm_context","ok":true,"summary":"VM context loaded"}',
    )).toEqual({
      type: 'tool_result',
      data: {
        call_id: 'call-1',
        name: 'query_vm_context',
        ok: true,
        summary: 'VM context loaded',
      },
    });
    expect(parseSseBlock(
      'event: error\ndata: {"code":"tool_failed","message":"Django denied this operation."}',
    )).toEqual({
      type: 'error',
      data: { code: 'tool_failed', message: 'Django denied this operation.' },
    });
  });
});
