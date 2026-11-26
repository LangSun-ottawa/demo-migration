import { Injectable, NgZone, inject } from '@angular/core';

import {
  AssistantStreamEvent,
  parseSseBlock,
} from './context-assistant.service';

@Injectable({ providedIn: 'root' })
export class SetupAssistantService {
  private readonly zone = inject(NgZone);
  private readonly gatewayUrl = `${window.location.protocol}//${window.location.hostname}:8002`;

  async stream(
    question: string,
    conversation: Array<{ role: 'user' | 'assistant'; content: string }>,
    signal: AbortSignal,
    onEvent: (event: AssistantStreamEvent) => void,
  ): Promise<void> {
    const response = await fetch(`${this.gatewayUrl}/assistant/stream`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        conversation,
        page_state: { route: '/new/setup' },
      }),
      signal,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null) as { detail?: string } | null;
      throw new Error(payload?.detail || `Assistant returned HTTP ${response.status}.`);
    }
    if (!response.body) throw new Error('Streaming response is unavailable.');

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const blocks = buffer.split('\n\n');
      buffer = blocks.pop() ?? '';
      for (const block of blocks) {
        const event = parseSseBlock(block);
        if (event) this.zone.run(() => onEvent(event));
      }
      if (done) {
        const finalEvent = parseSseBlock(buffer);
        if (finalEvent) this.zone.run(() => onEvent(finalEvent));
        break;
      }
    }
  }
}
