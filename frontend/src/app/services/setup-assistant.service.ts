import { Injectable, NgZone, inject } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { FdcApiResponse } from '../models/http.model';

import {
  AssistantStreamEvent,
  parseSseBlock,
} from './context-assistant.service';

export interface ConversationSnapshot {
  conversation_id: string | null;
  turns: Array<{
    question: string; assistant_text: string; status: string;
    tools: Array<{
      call_id: string; name: string; status: string;
      result: { ok: boolean; result?: Record<string, unknown> } | null;
    }>;
  }>;
}

@Injectable({ providedIn: 'root' })
export class SetupAssistantService {
  private readonly zone = inject(NgZone);
  private readonly http = inject(HttpClient);
  private readonly gatewayUrl = `${window.location.protocol}//${window.location.hostname}:8002`;

  latest() {
    return this.http.get<FdcApiResponse<ConversationSnapshot>>('/api/demo/secure/assistant/conversations/latest');
  }

  async stream(
    question: string,
    conversationId: string | null,
    signal: AbortSignal,
    onEvent: (event: AssistantStreamEvent) => void,
    logDatasetId: string | null = null,
    mode: 'setup' | 'investigation' = 'setup',
  ): Promise<void> {
    const response = await fetch(`${this.gatewayUrl}/assistant/stream`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        conversation_id: conversationId,
        page_state: { route: '/new/setup', log_dataset_id: logDatasetId, mode },
      }),
      signal,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null) as { detail?: string } | null;
      throw new HttpErrorResponse({ status: response.status,
        error: payload, statusText: payload?.detail || `Assistant returned HTTP ${response.status}.` });
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
