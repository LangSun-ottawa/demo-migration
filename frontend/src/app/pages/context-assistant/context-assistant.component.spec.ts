import { provideHttpClient } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { ContextAssistantComponent } from './context-assistant.component';
import {
  ContextAssistantService,
  VmAssociationContext,
} from '../../services/context-assistant.service';
import { of } from 'rxjs';


const TEST_CONTEXT: VmAssociationContext = {
  page: {
    id: 'vm-association',
    title: 'VM Association',
    route: '/new/context-assistant',
    source: 'Django ORM context API',
  },
  selection: {
    record_id: 1,
    name: 'Alpha Django Sensor',
    category: 'legacy',
    active: true,
  },
  records: [
    { id: 1, name: 'Alpha Django Sensor', category: 'legacy', active: true },
  ],
  associations: [],
  warnings: [],
  assistant_scope: [],
};


class ContextAssistantServiceStub {
  loadContext() {
    return of({ status: { return_code: 1 }, result: TEST_CONTEXT });
  }

  async stream(
    _request: unknown,
    _signal: AbortSignal,
    onEvent: (event: { type: 'delta'; data: { text: string } }) => void,
  ): Promise<void> {
    onEvent({ type: 'delta', data: { text: 'Streamed answer' } });
  }
}


describe('ContextAssistantComponent', () => {
  it('creates user and streamed assistant messages', async () => {
    await TestBed.configureTestingModule({
      imports: [ContextAssistantComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        { provide: ContextAssistantService, useClass: ContextAssistantServiceStub },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(ContextAssistantComponent);
    fixture.detectChanges();
    await fixture.componentInstance.sendQuestion();

    expect(fixture.componentInstance.messages).toEqual([
      { role: 'user', content: 'Which associations need review?' },
      { role: 'assistant', content: 'Streamed answer' },
    ]);
  });
});
