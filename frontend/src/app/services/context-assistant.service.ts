import { HttpClient } from '@angular/common/http';
import { inject, Injectable, NgZone } from '@angular/core';
import { Observable } from 'rxjs';

import { FdcApiResponse } from '../models/http.model';

export interface VmRecord {
  id: number;
  name: string;
  category: string;
  active: boolean;
}

export interface VmAssociation {
  id: string;
  type: string;
  name: string;
  status: 'associated' | 'review' | 'blocked';
}

export interface VmAssociationContext {
  page: {
    id: string;
    title: string;
    route: string;
    source: string;
  };
  selection: {
    record_id: number;
    name: string;
    category: string;
    active: boolean;
  };
  records: VmRecord[];
  associations: VmAssociation[];
  warnings: string[];
  assistant_scope: string[];
}

export interface AssistantPageState {
  route: '/new/context-assistant';
  selected_record_id: number;
  active_panel: 'associations' | 'warnings';
  visible_filter: 'all' | 'active' | 'inactive';
  expanded_association_ids: string[];
}

export interface AssistantStreamRequest {
  question: string;
  page_state: AssistantPageState;
  conversation: Array<{
    role: 'user' | 'assistant';
    content: string;
  }>;
}

export type AssistantStreamEvent =
  | {
      type: 'meta';
      data: {
        request_id: string;
        source: string;
        record_id: number;
        record_name: string;
      };
    }
  | { type: 'delta'; data: { text: string } }
  | { type: 'done'; data: { request_id: string } };

export function parseSseBlock(block: string): AssistantStreamEvent | null {
  const lines = block.split('\n');
  const eventLine = lines.find((line) => line.startsWith('event:'));
  const dataLines = lines
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart());

  if (!eventLine || dataLines.length === 0) {
    return null;
  }

  const type = eventLine.slice(6).trim();
  if (type !== 'meta' && type !== 'delta' && type !== 'done') {
    return null;
  }

  return {
    type,
    data: JSON.parse(dataLines.join('\n')),
  } as AssistantStreamEvent;
}

function resolveGatewayUrl(): string {
  const { protocol, hostname } = window.location;
  return `${protocol}//${hostname}:8002`;
}

@Injectable({ providedIn: 'root' })
export class ContextAssistantService {
  private readonly http = inject(HttpClient);
  private readonly zone = inject(NgZone);
  private readonly gatewayUrl = resolveGatewayUrl();

  loadContext(recordId: number): Observable<FdcApiResponse<VmAssociationContext>> {
    return this.http.get<FdcApiResponse<VmAssociationContext>>(
      '/api/demo/secure/page-context',
      { params: { record_id: recordId } },
    );
  }

  async stream(
    request: AssistantStreamRequest,
    signal: AbortSignal,
    onEvent: (event: AssistantStreamEvent) => void,
  ): Promise<void> {
    const response = await fetch(`${this.gatewayUrl}/assistant/stream`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal,
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => null) as { detail?: string } | null;
      throw new Error(payload?.detail || `Assistant gateway returned HTTP ${response.status}.`);
    }
    if (!response.body) {
      throw new Error('Streaming is not supported by this browser response.');
    }

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
        if (event) {
          this.zone.run(() => onEvent(event));
        }
      }

      if (done) {
        const finalEvent = parseSseBlock(buffer);
        if (finalEvent) {
          this.zone.run(() => onEvent(finalEvent));
        }
        break;
      }
    }
  }
}
