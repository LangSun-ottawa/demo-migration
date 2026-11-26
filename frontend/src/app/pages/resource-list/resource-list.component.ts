import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { FdcApiResponse } from '../../models/http.model';
import { SetupDemoService, SetupSnapshot } from '../../services/setup-demo.service';
import { DemoApiService } from '../../services/demo-api.service';

type ResourceKey = 'profiles' | 'users' | 'instances' | 'adapters';

@Component({
  selector: 'app-resource-list',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink],
  templateUrl: './resource-list.component.html',
  styleUrl: './resource-list.component.scss',
})
export class ResourceListComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(SetupDemoService);
  private readonly route = inject(ActivatedRoute);
  private readonly auth = inject(DemoApiService);

  readonly resource = this.route.snapshot.data['resource'] as ResourceKey;
  readonly title = this.route.snapshot.data['title'] as string;
  readonly singular = this.route.snapshot.data['singular'] as string;
  readonly highlightedId = Number(this.route.snapshot.queryParamMap.get('record'));
  snapshot: SetupSnapshot = { profiles: [], users: [], instances: [], adapters: [] };
  editingId: number | null = null;
  busy = false;
  loading = true;
  authenticated = false;
  canWrite = false;
  loadFailed = false;
  error = '';
  message = '';
  private pendingCreate: { body: string; key: string } | null = null;

  readonly form = this.fb.nonNullable.group({
    name: ['', Validators.required],
    access_level: ['readwrite'],
    username: ['', Validators.required],
    email: ['', Validators.email],
    profile_id: [0],
    environment: ['test'],
    adapter_type: ['rest'],
    endpoint: ['https://example.invalid/api'],
    instance_id: [0],
  });

  ngOnInit(): void { this.load(); }

  get rows(): any[] { return this.snapshot[this.resource] as any[]; }

  load(): void {
    if (this.busy) return;
    this.loading = true;
    this.loadFailed = false;
    this.canWrite = false;
    this.error = '';
    this.snapshot = { profiles: [], users: [], instances: [], adapters: [] };
    this.auth.getSession().subscribe({
      next: ({ result }) => {
        this.authenticated = Boolean(result?.authenticated);
        if (!this.authenticated || result?.setup_access === 'none') {
          this.loading = false;
          this.loadFailed = true;
          this.error = this.authenticated ? 'Your account has no access to this page.' : 'Sign in to view these records.';
          return;
        }
        this.canWrite = result?.setup_access === 'readwrite';
        this.api.load().subscribe({
          next: (response) => { if (response.result) this.snapshot = response.result; this.loading = false; },
          error: (error) => { this.loadFailed = true; this.captureError(error); },
        });
      },
      error: (error) => { this.loadFailed = true; this.captureError(error); },
    });
  }

  edit(row: any): void {
    if (!this.canWrite || this.busy || this.loading) return;
    this.error = ''; this.message = '';
    this.editingId = row.id;
    this.form.patchValue({
      name: row.name ?? '', username: row.username ?? '', email: row.email ?? '',
      access_level: row.access_level ?? 'readwrite', profile_id: row.profile_id ?? 0,
      environment: row.environment ?? 'test', adapter_type: row.adapter_type ?? 'rest',
      endpoint: row.endpoint ?? 'https://example.invalid/api', instance_id: row.instance_id ?? 0,
    });
  }

  reset(): void {
    this.pendingCreate = null;
    this.editingId = null;
    this.form.reset({
      name: '', username: '', email: '', access_level: 'readwrite', profile_id: 0,
      environment: 'test', adapter_type: 'rest', endpoint: 'https://example.invalid/api', instance_id: 0,
    });
    this.error = '';
  }

  save(): void {
    if (!this.canWrite || this.busy || this.loading) return;
    const payload = this.payload();
    if (!payload || this.busy) return;
    this.busy = true;
    this.error = '';
    this.message = '';
    const request = this.editingId
      ? this.api.update(this.resource, this.editingId, payload)
      : this.create(payload);
    request.subscribe({
      next: (response) => {
        if (response.result) this.snapshot = response.result;
        this.message = `${this.singular} ${this.editingId ? 'updated' : 'created'}.`;
        this.busy = false;
        this.reset();
      },
      error: (error) => this.captureError(error),
    });
  }

  remove(row: any): void {
    if (!this.canWrite || this.busy || this.loading) return;
    if (!confirm(`Delete ${row.name || row.username}?`)) return;
    this.busy = true;
    this.error = ''; this.message = '';
    this.api.delete(this.resource, row.id).subscribe({
      next: (response) => {
        if (response.result) this.snapshot = response.result;
        this.message = `${this.singular} deleted.`;
        this.busy = false;
        if (this.editingId === row.id) this.reset();
      },
      error: (error) => this.captureError(error),
    });
  }

  private payload(): object | null {
    const value = this.form.getRawValue();
    if (this.resource !== 'users' && !value.name.trim()) { this.error = 'Name is required.'; return null; }
    if (this.resource === 'profiles') return { name: value.name.trim(), access_level: value.access_level };
    if (this.resource === 'users') {
      if (!value.username.trim() || !value.email.trim() || !value.profile_id) { this.error = 'Username, email and profile are required.'; return null; }
      if (this.form.controls.email.invalid) { this.error = 'Enter a valid email address.'; return null; }
      return { username: value.username.trim(), email: value.email.trim(), profile_id: value.profile_id };
    }
    if (this.resource === 'instances') return { name: value.name.trim(), environment: value.environment };
    if (!value.name.trim() || !value.endpoint.trim() || !value.instance_id) { this.error = 'Name, endpoint and instance are required.'; return null; }
    return { name: value.name.trim(), adapter_type: value.adapter_type, endpoint: value.endpoint.trim(), instance_id: value.instance_id };
  }

  private create(payload: any) {
    const body = JSON.stringify(payload);
    if (this.pendingCreate?.body !== body) this.pendingCreate = { body, key: crypto.randomUUID() };
    const key = this.pendingCreate.key;
    if (this.resource === 'profiles') return this.api.createProfile(payload, key);
    if (this.resource === 'users') return this.api.createUser(payload, key);
    if (this.resource === 'instances') return this.api.createInstance(payload, key);
    return this.api.createAdapter(payload, key);
  }

  private captureError(error: HttpErrorResponse): void {
    this.busy = false;
    this.loading = false;
    if ([401, 403].includes(error.status)) {
      this.reset();
      this.canWrite = false;
      this.editingId = null;
      this.loadFailed = true;
      this.snapshot = { profiles: [], users: [], instances: [], adapters: [] };
      if (error.status === 401) this.authenticated = false;
    }
    const payload = error.error as FdcApiResponse<unknown> | undefined;
    this.error = payload?.error?.map((entry) => entry.message).filter(Boolean).join(' ') ||
      (error.status === 401 ? 'Session expired. Sign in again.' : error.status === 0 ? 'Cannot reach the server. Retry when it is available.' : 'Request failed.');
  }
}
