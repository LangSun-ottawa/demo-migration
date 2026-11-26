import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { DemoApiService } from '../../services/demo-api.service';
import { SetupAssistantService } from '../../services/setup-assistant.service';
import { SetupDemoService } from '../../services/setup-demo.service';
import { SetupDemoComponent } from './setup-demo.component';
import { LogEvidenceService } from '../../services/log-evidence.service';

describe('SetupDemoComponent composer', () => {
  let component: SetupDemoComponent;
  let stream: jasmine.Spy;

  beforeEach(() => {
    stream = jasmine.createSpy('stream').and.resolveTo();
    TestBed.configureTestingModule({
      imports: [SetupDemoComponent],
      providers: [
        provideRouter([]),
        { provide: DemoApiService, useValue: { getSession: () => of({ result: { authenticated: true, setup_access: 'readwrite', saml_enabled: true } }), logout: () => of({ result: { authenticated: false } }) } },
        { provide: SetupAssistantService, useValue: { stream, latest: () => of({ result: { conversation_id: null, turns: [] } }) } },
        { provide: SetupDemoService, useValue: { load: () => of({}) } },
        { provide: LogEvidenceService, useValue: { list: () => of({ result: { datasets: [] } }), demo: jasmine.createSpy('demo') } },
      ],
    });
    component = TestBed.createComponent(SetupDemoComponent).componentInstance;
  });

  it('clears user conversation and data on sign out', () => {
    component.authenticated = true;
    component.messages = [{ role: 'assistant', content: 'private' }];
    component.question.setValue('draft');
    component.conversationId = 'previous-user';
    component.logout();
    expect(component.authenticated).toBeFalse();
    expect(component.conversationId).toBeNull();
    expect(component.question.value).toBe('');
    expect(component.messages.some((message) => message.content === 'private')).toBeFalse();
  });

  it('sends on Enter and clears the input immediately', async () => {
    component.question.setValue(' hello ');
    const event = new KeyboardEvent('keydown', { key: 'Enter', cancelable: true });
    component.onComposerKeydown(event);
    expect(event.defaultPrevented).toBeTrue();
    expect(stream.calls.mostRecent().args[0]).toBe('hello');
    expect(component.question.value).toBe('');
    await Promise.resolve();
  });

  it('allows Shift+Enter and IME confirmation without sending', () => {
    component.question.setValue('你好');
    for (const event of [
      new KeyboardEvent('keydown', { key: 'Enter', shiftKey: true, cancelable: true }),
      new KeyboardEvent('keydown', { key: 'Enter', isComposing: true, cancelable: true }),
    ]) {
      component.onComposerKeydown(event);
      expect(event.defaultPrevented).toBeFalse();
    }
    expect(stream).not.toHaveBeenCalled();
    expect(component.question.value).toBe('你好');
  });

  it('blocks duplicate sends and preserves the next draft while streaming', async () => {
    let finish!: () => void;
    stream.and.returnValue(new Promise<void>((resolve) => { finish = resolve; }));
    component.question.setValue('first');
    const pending = component.send();
    component.question.setValue('next draft');
    await component.send();
    expect(stream).toHaveBeenCalledTimes(1);
    finish();
    await pending;
    expect(component.question.value).toBe('next draft');
  });

  it('restores the submitted input on transport failure', async () => {
    stream.and.rejectWith(new Error('Network unavailable'));
    component.question.setValue('retry me');
    await component.send();
    expect(component.question.value).toBe('retry me');
    expect(component.error).toBe('Network unavailable');
  });

  it('restores server-owned conversation and cards instead of a previous local account cache', () => {
    sessionStorage.setItem('setup-assistant-messages', JSON.stringify([{role: 'user', content: 'private old cache'}]));
    const assistant = TestBed.inject(SetupAssistantService);
    spyOn(assistant, 'latest').and.returnValue(of({ status: { return_code: 0 }, result: {
      conversation_id: 'server-id', turns: [{ question: 'Create Ops', assistant_text: 'Done', status: 'completed',
        tools: [{ call_id: 'actual-call', name: 'create_admin_profile', status: 'succeeded',
          result: { ok: true, result: { created_record: { resource: 'profiles',
            record: { id: 42, name: 'Ops', access_level: 'readonly' } } } } }] }],
    } }));
    component.ngOnInit();
    expect(component.conversationId).toBe('server-id');
    expect(component.messages[1].cards?.[0].id).toBe(42);
    expect(sessionStorage.getItem('setup-assistant-messages')).toBeNull();
    component.question.setValue('Use that profile');
    void component.send();
    expect(stream.calls.mostRecent().args[1]).toBe('server-id');
  });

  it('starts a new chat without sending a stale transcript', () => {
    component.conversationId = 'old-id';
    component.messages = [{ role: 'user', content: 'old text' }];
    component.newConversation();
    expect(component.messages).toEqual([]);
    component.question.setValue('Hello');
    void component.send();
    expect(stream.calls.mostRecent().args[1]).toBeNull();
  });

  it('clears old evidence and draft when selecting a different existing dataset', () => {
    component.conversationId = 'old-chat';
    component.logDatasetId = 'old-dataset';
    component.messages = [{ role: 'assistant', content: 'old evidence' }];
    component.question.setValue('previous question');
    component.selectDataset('new-dataset');
    expect(component.conversationId).toBeNull();
    expect(component.messages).toEqual([]);
    expect(component.question.value).toBe('');
    expect(component.logDatasetId).toBe('new-dataset');
    expect(stream).not.toHaveBeenCalled();
  });

  it('loads the selected scenario into an isolated read-only chat without auto-sending', () => {
    const logs = TestBed.inject(LogEvidenceService);
    const dataset = { id: 'new-dataset', name: 'Observation set A', simulated: true, event_count: 4,
      start: '2026-11-25T14:01:00Z', end: '2026-11-25T14:06:00Z' };
    (logs.demo as jasmine.Spy).and.returnValue(of({ result: { dataset } }));
    spyOn(logs, 'list').and.returnValue(of({ status: { return_code: 0 }, result: { datasets: [dataset] } }));
    component.conversationId = 'previous-chat';
    component.logDatasetId = 'previous-dataset';
    component.messages = [{ role: 'assistant', content: 'A previous unrelated hypothesis' }];
    component.sampleScenario = 'normal';
    component.importLogs();
    expect(logs.demo).toHaveBeenCalledWith('normal');
    expect(component.conversationId).toBeNull();
    expect(component.messages).toEqual([]);
    expect(component.assistantMode).toBe('investigation');
    expect(component.logDatasetId).toBe('new-dataset');
    expect(component.question.value).toContain('14:00–14:10 UTC');
    expect(stream).not.toHaveBeenCalled();
  });
});
