import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { LegacyFrameComponent } from './legacy-frame.component';

describe('LegacyFrameComponent', () => {
  let component: LegacyFrameComponent;
  let fixture: ComponentFixture<LegacyFrameComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LegacyFrameComponent],
      providers: [
        provideRouter([
          {
            path: '',
            component: LegacyFrameComponent,
            data: {
              title: 'Legacy report inside Angular',
              legacyUrl: '/legacy/report/',
            },
          },
        ]),
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(LegacyFrameComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should render the embedded legacy heading', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('h1')?.textContent).toContain('Embedded legacy page');
  });
});
