import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { FormBuilder, FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { FdcApiResponse } from '../../models/http.model';
import { AssistantStreamEvent } from '../../services/context-assistant.service';
import { DemoApiService } from '../../services/demo-api.service';
import { SetupAssistantService } from '../../services/setup-assistant.service';
import { SetupDemoService, SetupSnapshot } from '../../services/setup-demo.service';
import { AssistantMarkdownPipe } from './assistant-markdown.pipe';
import { CreatedRecordCard, createdRecordCard } from './created-record';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  cards?: CreatedRecordCard[];
}

@Component({
  selector: 'app-setup-demo',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink, AssistantMarkdownPipe],
  templateUrl: './setup-demo.component.html',
  styleUrl: './setup-demo.component.scss',
})
export class SetupDemoComponent implements OnInit, OnDestroy {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(DemoApiService);
  private readonly setup = inject(SetupDemoService);
  private readonly assistant = inject(SetupAssistantService);
  private controller: AbortController | null = null;

  authenticated = false;
  snapshot: SetupSnapshot = { profiles: [], users: [], instances: [], adapters: [] };
  messages: ChatMessage[] = [];
  toolActivity: string[] = [];
  error = '';
  busy = false;

  readonly loginForm = this.fb.nonNullable.group({
    username: ['demo', Validators.required],
    password: ['DemoPass123!', Validators.required],
  });
  readonly question = new FormControl('', {
    nonNullable: true,
    validators: Validators.required,
  });
  readonly prompts = [
    'Create an Admin Profile',
    'Create an Admin User',
    'Create an Instance',
    'Create an Adapter',
  ];

  ngOnInit(): void {
    const saved = sessionStorage.getItem('setup-assistant-messages');
    if (saved) {
      try { this.messages = JSON.parse(saved) as ChatMessage[]; } catch { sessionStorage.removeItem('setup-assistant-messages'); }
    }
    this.auth.getSession().subscribe({
      next: (response) => {
        this.authenticated = Boolean(response.result?.authenticated);
        if (this.authenticated) this.refreshSnapshot();
      },
    });
  }

  ngOnDestroy(): void {
    this.controller?.abort();
  }

  login(): void {
    if (this.loginForm.invalid) return;
    this.busy = true;
    this.auth.login(
      this.loginForm.controls.username.value,
      this.loginForm.controls.password.value,
    ).subscribe({
      next: () => {
        this.authenticated = true;
        this.busy = false;
        this.refreshSnapshot();
      },
      error: (error) => this.captureError(error),
    });
  }

  usePrompt(prompt: string): void {
    if (this.busy) return;
    this.question.setValue(prompt);
    void this.send();
  }

  onComposerKeydown(event: KeyboardEvent): void {
    if (event.key !== 'Enter' || event.shiftKey || event.isComposing || event.keyCode === 229) return;
    event.preventDefault();
    if (!event.repeat) void this.send();
  }

  async send(): Promise<void> {
    const text = this.question.value.trim();
    if (!text || this.busy) return;
    const conversation = this.messages.filter((message) => message.content.trim()).slice(-18)
      .map(({ role, content }) => ({ role, content }));
    this.messages = [...this.messages, { role: 'user', content: text }, { role: 'assistant', content: '' }];
    this.toolActivity = [];
    this.error = '';
    this.busy = true;
    this.question.setValue('');
    this.controller = new AbortController();
    try {
      await this.assistant.stream(text, conversation, this.controller.signal, (event) => {
        this.handleEvent(event);
      });
    } catch (error) {
      this.error = (error as Error).message;
      // Preserve anything the user has already started typing for their next turn.
      if (!this.question.value) this.question.setValue(text);
    } finally {
      this.busy = false;
      this.controller = null;
      this.refreshSnapshot();
    }
  }

  private handleEvent(event: AssistantStreamEvent): void {
    if (event.type === 'tool_start') {
      this.toolActivity = [...this.toolActivity, `Calling ${event.data.name}`];
    } else if (event.type === 'tool_result') {
      this.toolActivity = [...this.toolActivity, `${event.data.name}: ${event.data.summary}`];
      const card = event.data.ok ? createdRecordCard(event.data.call_id, event.data.name, event.data.result) : null;
      const index = this.messages.length - 1;
      const current = this.messages[index];
      if (card && current?.role === 'assistant' && !current.cards?.some((item) => item.callId === card.callId)) {
        this.messages = [...this.messages.slice(0, index), { ...current, cards: [...(current.cards ?? []), card] }];
        sessionStorage.setItem('setup-assistant-messages', JSON.stringify(this.messages));
      }
    } else if (event.type === 'error') {
      this.error = event.data.message;
    } else if (event.type === 'delta') {
      const index = this.messages.length - 1;
      const current = this.messages[index];
      if (current?.role === 'assistant') {
        this.messages = [...this.messages.slice(0, index), { ...current, content: current.content + event.data.text }];
        sessionStorage.setItem('setup-assistant-messages', JSON.stringify(this.messages));
      }
    }
  }

  private refreshSnapshot(): void {
    this.setup.load().subscribe({
      next: (response) => {
        if (response.result) this.snapshot = response.result;
      },
      error: (error) => this.captureError(error),
    });
  }

  private captureError(error: HttpErrorResponse): void {
    this.busy = false;
    const payload = error.error as FdcApiResponse<unknown> | undefined;
    this.error = payload?.error?.[0]?.message || 'Request failed.';
    if (error.status === 401) this.authenticated = false;
  }
}
