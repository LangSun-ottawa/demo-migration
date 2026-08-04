import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { FdcApiResponse } from '../../models/http.model';
import {
  ContractCatalogResult,
  DemoApiService,
  SessionResult,
  TraceStep,
} from '../../services/demo-api.service';

@Component({
  selector: 'app-architecture-lab',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './architecture-lab.component.html',
  styleUrl: './architecture-lab.component.scss',
})
export class ArchitectureLabComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(DemoApiService);

  readonly loginForm = this.fb.nonNullable.group({
    username: ['demo', [Validators.required, Validators.maxLength(30)]],
    password: ['DemoPass123!', Validators.required],
  });

  readonly securityForm = this.fb.nonNullable.group({
    display_name: ['  <script>alert("demo")</script>  ', Validators.required],
    lookup_term: ["' OR 1=1 --", Validators.required],
    safe_identifier: ['report_2026', Validators.required],
  });

  readonly modelForm = this.fb.nonNullable.group({
    term: ["' OR 1=1 --", Validators.required],
  });

  session: SessionResult | null = null;
  catalog: ContractCatalogResult | null = null;
  output: unknown = null;
  trace: TraceStep[] = [];
  errorMessages: string[] = [];
  runningAction = '';

  ngOnInit(): void {
    this.refreshSession();
    this.api.getContractCatalog().subscribe({
      next: (response) => {
        this.catalog = response.result ?? null;
      },
      error: (error) => this.captureError(error),
    });
  }

  refreshSession(): void {
    this.run('Reading session', () => this.api.getSession().subscribe({
      next: (response) => {
        this.session = response.result ?? null;
        this.captureSuccess(response);
      },
      error: (error) => this.captureError(error),
    }));
  }

  login(): void {
    if (this.loginForm.invalid) {
      this.loginForm.markAllAsTouched();
      return;
    }
    const credentials = this.loginForm.getRawValue();
    this.run('Logging in', () => this.api.login(credentials.username, credentials.password).subscribe({
      next: (response) => {
        this.session = response.result ?? null;
        this.captureSuccess(response);
      },
      error: (error) => this.captureError(error),
    }));
  }

  logout(): void {
    this.run('Logging out', () => this.api.logout().subscribe({
      next: (response) => {
        this.session = response.result ?? null;
        this.captureSuccess(response);
      },
      error: (error) => this.captureError(error),
    }));
  }

  callProtectedEndpoint(): void {
    this.run('Calling protected model endpoint', () => this.api.compareModels('Alpha').subscribe({
      next: (response) => this.captureSuccess(response),
      error: (error) => this.captureError(error),
    }));
  }

  inspectSecurity(rejectIdentifier = false): void {
    if (this.securityForm.invalid) {
      this.securityForm.markAllAsTouched();
      return;
    }
    const payload = this.securityForm.getRawValue();
    if (rejectIdentifier) {
      payload.safe_identifier = 'report;rm-rf';
    }
    this.run(
      rejectIdentifier ? 'Testing schema rejection' : 'Inspecting input defenses',
      () => this.api.inspectSecurity(payload).subscribe({
        next: (response) => this.captureSuccess(response),
        error: (error) => this.captureError(error),
      }),
    );
  }

  compareModels(): void {
    if (this.modelForm.invalid) {
      this.modelForm.markAllAsTouched();
      return;
    }
    this.run('Comparing ORM queries', () => this.api.compareModels(
      this.modelForm.getRawValue().term,
    ).subscribe({
      next: (response) => this.captureSuccess(response),
      error: (error) => this.captureError(error),
    }));
  }

  private run(label: string, action: () => void): void {
    this.runningAction = label;
    this.errorMessages = [];
    action();
  }

  private captureSuccess(response: FdcApiResponse<unknown>): void {
    this.runningAction = '';
    this.output = response;
    this.trace = this.extractTrace(response.result);
  }

  private captureError(error: unknown): void {
    this.runningAction = '';
    const payload = (error as HttpErrorResponse).error as FdcApiResponse<unknown> | undefined;
    this.output = payload ?? error;
    this.trace = this.extractTrace(payload?.result);
    this.errorMessages = payload?.error
      ?.map((entry) => entry.message)
      .filter((message): message is string => Boolean(message)) ?? ['Request failed.'];
  }

  private extractTrace(result: unknown): TraceStep[] {
    if (!result || typeof result !== 'object') {
      return [];
    }
    const trace = (result as { trace?: TraceStep[] }).trace;
    return Array.isArray(trace) ? trace : [];
  }
}
