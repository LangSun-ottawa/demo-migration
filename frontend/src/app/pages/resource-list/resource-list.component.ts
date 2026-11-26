import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { FdcApiResponse } from '../../models/http.model';
import { SetupDemoService, SetupSnapshot } from '../../services/setup-demo.service';

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

  readonly resource = this.route.snapshot.data['resource'] as ResourceKey;
  readonly title = this.route.snapshot.data['title'] as string;
  readonly singular = this.route.snapshot.data['singular'] as string;
  readonly highlightedId = Number(this.route.snapshot.queryParamMap.get('record'));
  snapshot: SetupSnapshot = { profiles: [], users: [], instances: [], adapters: [] };
  editingId: number | null = null;
  busy = false;
  error = '';
  message = '';

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
    this.api.load().subscribe({
      next: (response) => { if (response.result) this.snapshot = response.result; },
      error: (error) => this.captureError(error),
    });
  }

  edit(row: any): void {
    this.editingId = row.id;
    this.form.patchValue({
      name: row.name ?? '', username: row.username ?? '', email: row.email ?? '',
      access_level: row.access_level ?? 'readwrite', profile_id: row.profile_id ?? 0,
      environment: row.environment ?? 'test', adapter_type: row.adapter_type ?? 'rest',
      endpoint: row.endpoint ?? 'https://example.invalid/api', instance_id: row.instance_id ?? 0,
    });
  }

  reset(): void {
    this.editingId = null;
    this.form.reset({
      name: '', username: '', email: '', access_level: 'readwrite', profile_id: 0,
      environment: 'test', adapter_type: 'rest', endpoint: 'https://example.invalid/api', instance_id: 0,
    });
    this.error = '';
  }

  save(): void {
    const payload = this.payload();
    if (!payload || this.busy) return;
    this.busy = true;
    this.error = '';
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
    if (!confirm(`Delete ${row.name || row.username}?`)) return;
    this.busy = true;
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
    if (this.resource === 'profiles') return { name: value.name.trim(), access_level: value.access_level };
    if (this.resource === 'users') {
      if (!value.username.trim() || !value.email.trim() || !value.profile_id) { this.error = 'Username, email and profile are required.'; return null; }
      return { username: value.username.trim(), email: value.email.trim(), profile_id: value.profile_id };
    }
    if (this.resource === 'instances') return { name: value.name.trim(), environment: value.environment };
    if (!value.name.trim() || !value.endpoint.trim() || !value.instance_id) { this.error = 'Name, endpoint and instance are required.'; return null; }
    return { name: value.name.trim(), adapter_type: value.adapter_type, endpoint: value.endpoint.trim(), instance_id: value.instance_id };
  }

  private create(payload: any) {
    if (this.resource === 'profiles') return this.api.createProfile(payload);
    if (this.resource === 'users') return this.api.createUser(payload);
    if (this.resource === 'instances') return this.api.createInstance(payload);
    return this.api.createAdapter(payload);
  }

  private captureError(error: HttpErrorResponse): void {
    this.busy = false;
    const payload = error.error as FdcApiResponse<unknown> | undefined;
    this.error = payload?.error?.[0]?.message || (error.status === 401 ? 'Login required.' : 'Request failed.');
  }
}
