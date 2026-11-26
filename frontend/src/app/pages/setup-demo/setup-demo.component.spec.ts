import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { DemoApiService } from '../../services/demo-api.service';
import { SetupAssistantService } from '../../services/setup-assistant.service';
import { SetupDemoService } from '../../services/setup-demo.service';
import { SetupDemoComponent } from './setup-demo.component';

describe('SetupDemoComponent composer', () => {
  let component: SetupDemoComponent;
  let stream: jasmine.Spy;

  beforeEach(() => {
    stream = jasmine.createSpy('stream').and.resolveTo();
    TestBed.configureTestingModule({
      imports: [SetupDemoComponent],
      providers: [
        provideRouter([]),
        { provide: DemoApiService, useValue: { getSession: () => of({ result: { authenticated: true } }) } },
        { provide: SetupAssistantService, useValue: { stream } },
        { provide: SetupDemoService, useValue: { load: () => of({}) } },
      ],
    });
    component = TestBed.createComponent(SetupDemoComponent).componentInstance;
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
});
