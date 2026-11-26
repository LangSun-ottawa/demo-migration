import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, HostListener, OnDestroy, OnInit, inject } from '@angular/core';
import { FormBuilder, FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { FdcApiResponse } from '../../models/http.model';
import { AssistantStreamEvent } from '../../services/context-assistant.service';
import { DemoApiService } from '../../services/demo-api.service';
import { SetupAssistantService } from '../../services/setup-assistant.service';
import { SetupDemoService, SetupSnapshot } from '../../services/setup-demo.service';
import { AssistantMarkdownPipe } from './assistant-markdown.pipe';
import { CreatedRecordCard, createdRecordCard } from './created-record';
import { EvidenceTimeline, EvidenceTimelineComponent, evidenceTimeline } from './evidence-timeline.component';
import { LogDataset, LogEvidenceService, LogScenario } from '../../services/log-evidence.service';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  cards?: CreatedRecordCard[];
  timelines?: EvidenceTimeline[];
}

@Component({
  selector: 'app-setup-demo',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink, AssistantMarkdownPipe, EvidenceTimelineComponent],
  templateUrl: './setup-demo.component.html',
  styleUrl: './setup-demo.component.scss',
})
export class SetupDemoComponent implements OnInit, OnDestroy {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(DemoApiService);
  private readonly setup = inject(SetupDemoService);
  private readonly assistant = inject(SetupAssistantService);
  private readonly logs = inject(LogEvidenceService);
  private controller: AbortController | null = null;

  authenticated = false;
  sessionLoading = true;
  setupAccess = 'none';
  samlEnabled = false;
  snapshot: SetupSnapshot = { profiles: [], users: [], instances: [], adapters: [] };
  messages: ChatMessage[] = [];
  toolActivity: string[] = [];
  error = '';
  busy = false;
  historyLoading = false;
  conversationId: string | null = null;
  private historyGeneration = 0;
  private sessionUsername: string | null = null;
  datasets: LogDataset[] = [];
  logDatasetId: string | null = null;
  logBusy = false;
  sampleScenario: LogScenario = 'policy_block';
  assistantMode: 'setup' | 'investigation' = 'setup';

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
  readonly readPrompts = ['Show existing Admin Profiles', 'Show existing Admin Users', 'Show instances and adapters'];

  ngOnInit(): void {
    sessionStorage.removeItem('setup-assistant-messages'); // Remove the old, unowned transcript cache.
    this.loadSession();
  }

  private loadSession(): void {
    this.sessionLoading = true;
    this.auth.getSession().subscribe({
      next: (response) => {
        this.sessionLoading = false;
        this.authenticated = Boolean(response.result?.authenticated);
        this.setupAccess = response.result?.setup_access ?? 'none';
        this.samlEnabled = Boolean(response.result?.saml_enabled);
        this.sessionUsername = response.result?.username ?? null;
        if (this.authenticated && this.setupAccess !== 'none') { this.refreshSnapshot(); this.restoreConversation(); this.loadLogs(); }
      },
      error: () => { this.sessionLoading = false; this.error = 'Cannot check your session. Refresh when Django is available.'; },
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
      next: (response) => {
        this.sessionUsername = response.result?.username ?? null;
        this.authenticated = true;
        this.busy = false;
        this.loadSession();
      },
      error: (error) => this.captureError(error),
    });
  }

  logout(): void {
    this.auth.logout().subscribe({
      next: () => {
        this.controller?.abort();
        this.clearConversation();
        this.authenticated = false;
        this.setupAccess = 'none';
        this.sessionUsername = null;
        this.snapshot = { profiles: [], users: [], instances: [], adapters: [] };
        this.datasets = []; this.logDatasetId = null;
        this.question.setValue('');
        this.error = '';
      },
      error: (error) => this.captureError(error),
    });
  }

  @HostListener('window:focus')
  checkSessionOnFocus(): void {
    this.auth.getSession().subscribe({
      next: ({ result }) => {
        this.setupAccess = result?.setup_access ?? 'none';
        this.samlEnabled = Boolean(result?.saml_enabled);
        const username = result?.username ?? null;
        const authenticated = Boolean(result?.authenticated);
        if (username !== this.sessionUsername || authenticated !== this.authenticated) {
          this.controller?.abort();
          this.clearConversation();
          this.question.setValue('');
          this.snapshot = { profiles: [], users: [], instances: [], adapters: [] };
          this.datasets = []; this.logDatasetId = null;
          this.sessionUsername = username;
          this.authenticated = authenticated;
          if (authenticated) { this.refreshSnapshot(); this.restoreConversation(); this.loadLogs(); }
        }
      },
    });
  }

  usePrompt(prompt: string): void {
    if (this.busy || this.historyLoading) return;
    this.assistantMode = 'setup';
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
    if (!text || this.busy || this.historyLoading) return;
    this.messages = [...this.messages, { role: 'user', content: text }, { role: 'assistant', content: '' }];
    this.toolActivity = [];
    this.error = '';
    this.busy = true;
    this.question.setValue('');
    this.controller = new AbortController();
    const generation = this.historyGeneration;
    try {
      await this.assistant.stream(text, this.conversationId, this.controller.signal, (event) => {
        if (generation === this.historyGeneration) this.handleEvent(event);
      }, this.logDatasetId, this.assistantMode);
    } catch (error) {
      if (generation !== this.historyGeneration) return;
      if ((error as Error).name === 'AbortError') {
        this.error = 'Run cancelled. Completed writes remain saved; check records before retrying.';
        return;
      }
      if (error instanceof HttpErrorResponse) {
        this.error = error.error?.detail || error.statusText;
        if ([401, 403, 404].includes(error.status)) this.clearConversation();
        if (error.status === 401) this.authenticated = false;
      } else this.error = (error as Error).message;
      // Preserve anything the user has already started typing for their next turn.
      if (!this.question.value) this.question.setValue(text);
    } finally {
      this.busy = false;
      this.controller = null;
      this.refreshSnapshot();
    }
  }

  private handleEvent(event: AssistantStreamEvent): void {
    if (event.type === 'meta') {
      this.conversationId = event.data.conversation_id ?? null;
    } else if (event.type === 'tool_start') {
      this.toolActivity = [...this.toolActivity, `Calling ${event.data.name}`];
    } else if (event.type === 'tool_result') {
      this.toolActivity = [...this.toolActivity, `${event.data.name}: ${event.data.summary}`];
      const card = event.data.ok ? createdRecordCard(event.data.call_id, event.data.name, event.data.result) : null;
      const index = this.messages.length - 1;
      const current = this.messages[index];
      const timeline = event.data.ok ? evidenceTimeline(event.data.name, event.data.result) : null;
      if (timeline && current?.role === 'assistant') {
        this.messages = [...this.messages.slice(0, index), { ...current, timelines: [...(current.timelines ?? []), timeline] }];
      }
      if (card && current?.role === 'assistant' && !current.cards?.some((item) => item.callId === card.callId)) {
        const latest = this.messages[index];
        this.messages = [...this.messages.slice(0, index), { ...latest, cards: [...(latest.cards ?? []), card] }];
      }
    } else if (event.type === 'error') {
      this.error = event.data.message;
    } else if (event.type === 'delta') {
      const index = this.messages.length - 1;
      const current = this.messages[index];
      if (current?.role === 'assistant') {
        this.messages = [...this.messages.slice(0, index), { ...current, content: current.content + event.data.text }];
      }
    }
  }

  newConversation(): void {
    if (this.busy) return;
    this.clearConversation();
    this.error = '';
  }

  cancel(): void {
    this.controller?.abort();
    this.error = 'Run cancelled. Completed writes remain saved; check records before retrying.';
  }

  private clearConversation(): void {
    this.historyGeneration++;
    this.historyLoading = false;
    this.conversationId = null;
    this.messages = [];
    this.toolActivity = [];
  }

  private restoreConversation(): void {
    this.clearConversation();
    const generation = this.historyGeneration;
    this.historyLoading = true;
    this.assistant.latest().subscribe({
      next: ({ result }) => {
        if (generation !== this.historyGeneration) return;
        this.historyLoading = false;
        this.conversationId = result?.conversation_id ?? null;
        this.messages = (result?.turns ?? []).flatMap((turn): ChatMessage[] => {
          const cards = turn.tools.flatMap((tool) => {
            const card = tool.status === 'succeeded' && tool.result?.ok
              ? createdRecordCard(tool.call_id, tool.name, tool.result.result) : null;
            return card ? [card] : [];
          });
          const warning = turn.status === 'completed' ? '' : `\n\n[Previous turn: ${turn.status}. Check records before retrying a write.]`;
          const timelines = turn.tools.flatMap((tool) => {
            const timeline = tool.status === 'succeeded' && tool.result?.ok ? evidenceTimeline(tool.name, tool.result.result) : null;
            return timeline ? [timeline] : [];
          });
          return [{ role: 'user', content: turn.question },
            { role: 'assistant', content: turn.assistant_text + warning, cards, timelines }];
        });
        const lastBusinessTool = [...(result?.turns ?? [])].reverse().flatMap((turn) => [...turn.tools].reverse())
          .find((tool) => tool.name !== 'ask_user_question');
        if (lastBusinessTool && !lastBusinessTool.name.startsWith('create_') && lastBusinessTool.name !== 'query_setup_state') {
          this.assistantMode = 'investigation';
          const latestTimeline = [...this.messages].reverse().flatMap((message) => message.timelines ?? [])[0];
          if (latestTimeline) this.logDatasetId = latestTimeline.datasetId;
        }
      },
      error: (error) => {
        if (generation !== this.historyGeneration) return;
        this.historyLoading = false;
        this.captureError(error);
      },
    });
  }

  loadLogs(): void {
    const username = this.sessionUsername;
    this.logs.list().subscribe({
      next: ({ result }) => {
        if (username !== this.sessionUsername) return;
        this.datasets = result?.datasets ?? [];
        this.logDatasetId = this.datasets.find((item) => item.id === this.logDatasetId)?.id ?? this.datasets[0]?.id ?? null;
      }, error: () => {
        if (this.authenticated && username === this.sessionUsername) this.error = 'Could not load log datasets.';
      },
    });
  }

  importLogs(file?: File): void {
    if (this.logBusy || this.busy) return;
    if (file && file.size > 1024 * 1024) { this.error = 'Maximum log file size: 1 MiB.'; return; }
    this.logBusy = true;
    const username = this.sessionUsername;
    (file ? this.logs.upload(file) : this.logs.demo(this.sampleScenario)).subscribe({
      next: ({ result }) => {
        this.logBusy = false;
        if (username !== this.sessionUsername) return;
        const nextDatasetId = result?.dataset.id ?? null;
        if (nextDatasetId !== this.logDatasetId) this.clearConversation();
        this.logDatasetId = nextDatasetId;
        this.assistantMode = 'investigation';
        this.loadLogs();
        this.question.setValue(file ? 'Investigate the selected uploaded logs. Ask me for the device and time range if needed; cite event IDs and explain uncertainty.' :
          '请调查选中日志中 2026-11-25 14:00–14:10 UTC，192.0.2.10 到 198.51.100.20:443 的通信是否异常。引用事件 ID，排除无关告警，区分事实与推测；证据不够时请追问。');
      }, error: (error) => { this.logBusy = false; this.captureError(error); },
    });
  }

  onLogFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) this.importLogs(file);
    input.value = '';
  }

  selectDataset(id: string): void {
    if (this.busy || this.logBusy || id === this.logDatasetId) return;
    this.clearConversation();
    this.question.setValue('');
    this.error = '';
    this.logDatasetId = id || null;
  }

  private refreshSnapshot(): void {
    const username = this.sessionUsername;
    this.setup.load().subscribe({
      next: (response) => {
        if (!this.authenticated || username !== this.sessionUsername) return;
        if (response.result) this.snapshot = response.result;
      },
      error: (error) => {
        if (this.authenticated && username === this.sessionUsername) this.captureError(error);
      },
    });
  }

  private captureError(error: HttpErrorResponse): void {
    this.busy = false;
    const payload = error.error as FdcApiResponse<unknown> | undefined;
    this.error = payload?.error?.[0]?.message || 'Request failed.';
    if ([401, 403].includes(error.status)) this.clearConversation();
    if (error.status === 401) this.authenticated = false;
  }
}
