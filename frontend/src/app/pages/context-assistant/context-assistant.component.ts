import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { FdcApiResponse } from '../../models/http.model';
import {
  AssistantStreamEvent,
  ContextAssistantService,
  VmAssociationContext,
  VmRecord,
} from '../../services/context-assistant.service';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

@Component({
  selector: 'app-context-assistant',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink],
  templateUrl: './context-assistant.component.html',
  styleUrl: './context-assistant.component.scss',
})
export class ContextAssistantComponent implements OnInit, OnDestroy {
  private readonly assistant = inject(ContextAssistantService);

  readonly question = new FormControl('Which associations need review?', {
    nonNullable: true,
    validators: [Validators.required, Validators.maxLength(500)],
  });
  readonly quickPrompts = [
    'Summarize the selected VM.',
    'Which associations need review?',
    'Explain the visible associations.',
  ];

  context: VmAssociationContext | null = null;
  selectedRecordId = 1;
  visibleFilter: 'all' | 'active' | 'inactive' = 'all';
  activePanel: 'associations' | 'warnings' = 'associations';
  expandedAssociationIds: string[] = [];
  messages: ChatMessage[] = [];
  streamSource = '';
  errorMessage = '';
  isLoadingContext = false;
  isStreaming = false;
  private streamController: AbortController | null = null;

  ngOnInit(): void {
    this.loadContext(this.selectedRecordId);
  }

  ngOnDestroy(): void {
    this.streamController?.abort();
  }

  get visibleRecords(): VmRecord[] {
    const records = this.context?.records ?? [];
    if (this.visibleFilter === 'active') {
      return records.filter((record) => record.active);
    }
    if (this.visibleFilter === 'inactive') {
      return records.filter((record) => !record.active);
    }
    return records;
  }

  loadContext(recordId: number): void {
    this.isLoadingContext = true;
    this.errorMessage = '';
    this.assistant.loadContext(recordId).subscribe({
      next: (response) => {
        this.context = response.result ?? null;
        this.selectedRecordId = recordId;
        this.expandedAssociationIds = [];
        this.isLoadingContext = false;
      },
      error: (error) => {
        this.isLoadingContext = false;
        this.captureApiError(error, 'Unable to load Django page context.');
      },
    });
  }

  selectRecord(recordId: number): void {
    if (recordId === this.selectedRecordId || this.isLoadingContext) {
      return;
    }
    this.stopStream();
    this.messages = [];
    this.streamSource = '';
    this.loadContext(recordId);
  }

  setFilter(filter: 'all' | 'active' | 'inactive'): void {
    this.visibleFilter = filter;
  }

  setPanel(panel: 'associations' | 'warnings'): void {
    this.activePanel = panel;
  }

  toggleAssociation(associationId: string): void {
    this.expandedAssociationIds = this.expandedAssociationIds.includes(associationId)
      ? this.expandedAssociationIds.filter((id) => id !== associationId)
      : [...this.expandedAssociationIds, associationId];
  }

  isAssociationExpanded(associationId: string): boolean {
    return this.expandedAssociationIds.includes(associationId);
  }

  sendQuickPrompt(prompt: string): void {
    this.question.setValue(prompt);
    void this.sendQuestion();
  }

  async sendQuestion(): Promise<void> {
    if (this.question.invalid || !this.context || this.isStreaming) {
      this.question.markAsTouched();
      return;
    }

    const question = this.question.getRawValue().trim();
    if (!question) {
      return;
    }

    const previousConversation = this.messages
      .filter((message) => message.content)
      .slice(-6);
    this.messages = [
      ...this.messages,
      { role: 'user', content: question },
      { role: 'assistant', content: '' },
    ];
    this.errorMessage = '';
    this.streamSource = '';
    this.isStreaming = true;
    this.streamController = new AbortController();

    try {
      await this.assistant.stream(
        {
          question,
          page_state: {
            route: '/new/context-assistant',
            selected_record_id: this.selectedRecordId,
            active_panel: this.activePanel,
            visible_filter: this.visibleFilter,
            expanded_association_ids: this.expandedAssociationIds,
          },
          conversation: previousConversation,
        },
        this.streamController.signal,
        (event) => this.handleStreamEvent(event),
      );
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        this.errorMessage = (error as Error).message || 'Assistant streaming failed.';
      }
    } finally {
      this.isStreaming = false;
      this.streamController = null;
    }
  }

  stopStream(): void {
    this.streamController?.abort();
    this.streamController = null;
    this.isStreaming = false;
  }

  private handleStreamEvent(event: AssistantStreamEvent): void {
    if (event.type === 'meta') {
      this.streamSource = `${event.data.source} / ${event.data.record_name}`;
      return;
    }
    if (event.type === 'delta') {
      const lastIndex = this.messages.length - 1;
      const current = this.messages[lastIndex];
      if (current?.role === 'assistant') {
        this.messages = [
          ...this.messages.slice(0, lastIndex),
          { ...current, content: current.content + event.data.text },
        ];
      }
    }
  }

  private captureApiError(error: unknown, fallback: string): void {
    const payload = (error as HttpErrorResponse).error as FdcApiResponse<unknown> | undefined;
    this.errorMessage = payload?.error?.[0]?.message || fallback;
  }
}
