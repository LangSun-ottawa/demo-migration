import { parseSseBlock } from './context-assistant.service';

describe('parseSseBlock', () => {
  it('parses a streamed delta event', () => {
    const event = parseSseBlock('event: delta\ndata: {"text":"hello "}');

    expect(event).toEqual({ type: 'delta', data: { text: 'hello ' } });
  });

  it('ignores unsupported or incomplete events', () => {
    expect(parseSseBlock('data: {"text":"missing event"}')).toBeNull();
    expect(parseSseBlock('event: heartbeat\ndata: {}')).toBeNull();
  });
});
