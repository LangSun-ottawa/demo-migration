import { TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { of, Subject, throwError } from 'rxjs';
import { DemoApiService } from '../../services/demo-api.service';
import { SetupDemoService } from '../../services/setup-demo.service';
import { ResourceListComponent } from './resource-list.component';

describe('Resource lists demo states', () => {
  let api: any;
  let auth: any;
  const snapshot = { profiles: [{ id: 1, name: 'Ops', access_level: 'readonly' }], users: [], instances: [], adapters: [] };

  beforeEach(() => {
    api = jasmine.createSpyObj('api', ['load', 'createProfile', 'createUser', 'update', 'delete']);
    api.load.and.returnValue(of({ result: snapshot }));
    api.createProfile.and.returnValue(of({ result: snapshot }));
    auth = { getSession: jasmine.createSpy().and.returnValue(of({ result: { authenticated: true, setup_access: 'readwrite' } })) };
    TestBed.configureTestingModule({
      imports: [ResourceListComponent], providers: [provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { data: { resource: 'profiles', title: 'Admin Profiles', singular: 'Admin Profile' }, queryParamMap: convertToParamMap({}) } } },
        { provide: SetupDemoService, useValue: api }, { provide: DemoApiService, useValue: auth }],
    });
  });

  function create() { const fixture = TestBed.createComponent(ResourceListComponent); fixture.detectChanges(); return fixture; }

  it('hides mutation controls for readonly and blocks direct UI methods', () => {
    auth.getSession.and.returnValue(of({ result: { authenticated: true, setup_access: 'readonly' } }));
    const fixture = create(); const component = fixture.componentInstance;
    expect(fixture.nativeElement.textContent).toContain('Read-only access');
    expect(fixture.nativeElement.querySelector('form')).toBeNull();
    component.save(); component.edit(snapshot.profiles[0]); component.remove(snapshot.profiles[0]);
    expect(api.createProfile).not.toHaveBeenCalled(); expect(api.delete).not.toHaveBeenCalled();
    expect(component.editingId).toBeNull();
  });

  it('shows loading rather than an empty state until the response arrives', () => {
    const pending = new Subject<any>(); api.load.and.returnValue(pending);
    const fixture = create();
    expect(fixture.nativeElement.textContent).toContain('Loading records');
    expect(fixture.nativeElement.textContent).not.toContain('No records yet');
    pending.next({ result: snapshot }); fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Ops');
    expect(fixture.componentInstance.loading).toBeFalse();
  });

  it('offers sign in without calling protected APIs for anonymous users', () => {
    auth.getSession.and.returnValue(of({ result: { authenticated: false, setup_access: 'none' } }));
    const fixture = create();
    expect(api.load).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('Sign in');
    expect(fixture.nativeElement.querySelector('form')).toBeNull();
  });

  it('shows access denied rather than exposing an empty editable list', () => {
    auth.getSession.and.returnValue(of({ result: { authenticated: true, setup_access: 'none' } }));
    const fixture = create();
    expect(api.load).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('no access');
  });

  it('supports retry after a transport error', () => {
    api.load.and.returnValue(throwError(() => new HttpErrorResponse({ status: 0 })));
    const fixture = create(); const component = fixture.componentInstance;
    expect(component.loadFailed).toBeTrue();
    expect(fixture.nativeElement.textContent).toContain('Retry');
    api.load.and.returnValue(of({ result: snapshot })); component.load(); fixture.detectChanges();
    expect(component.loadFailed).toBeFalse(); expect(component.rows.length).toBe(1);
  });

  it('validates blank required fields without making a request', () => {
    const component = create().componentInstance;
    component.form.patchValue({ name: '   ' }); component.save();
    expect(component.error).toBe('Name is required.'); expect(api.createProfile).not.toHaveBeenCalled();
  });

  it('retains an unchanged operation key after response loss', () => {
    api.createProfile.and.returnValue(throwError(() => new HttpErrorResponse({ status: 0 })));
    const component = create().componentInstance;
    component.form.patchValue({ name: 'Ops' }); component.save(); component.save();
    expect(api.createProfile.calls.argsFor(0)[1]).toBe(api.createProfile.calls.argsFor(1)[1]);
    component.form.patchValue({ name: 'Different' }); component.save();
    expect(api.createProfile.calls.argsFor(2)[1]).not.toBe(api.createProfile.calls.argsFor(0)[1]);
  });

  it('clears visible rows and disables writing when the session expires', () => {
    api.createProfile.and.returnValue(throwError(() => new HttpErrorResponse({ status: 401 })));
    const component = create().componentInstance;
    component.form.patchValue({ name: 'Ops' }); component.save();
    expect(component.authenticated).toBeFalse(); expect(component.canWrite).toBeFalse();
    expect(component.rows).toEqual([]); expect(component.error).toContain('Session expired');
  });
});
