import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { FdcApiResponse } from '../../models/http.model';
import {
  DemoApiService,
  EchoResult,
  SearchResult,
  UploadResult,
} from '../../services/demo-api.service';

@Component({
  selector: 'app-demo-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink],
  templateUrl: './demo-form.component.html',
  styleUrl: './demo-form.component.scss',
})
export class DemoFormComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(DemoApiService);
  private readonly route = inject(ActivatedRoute);

  readonly echoForm = this.fb.nonNullable.group({
    name: ['Demo User', [Validators.required, Validators.maxLength(60)]],
    age: [29, [Validators.required, Validators.min(18), Validators.max(99)]],
    active: [true, Validators.required],
    note: [''],
    source: ['legacy-demo', [Validators.required, Validators.maxLength(30)]],
    tags: ['alpha, beta', Validators.required],
  });

  readonly searchForm = this.fb.nonNullable.group({
    term: ['a', [Validators.required, Validators.maxLength(40)]],
    limit: [3, [Validators.required, Validators.min(1), Validators.max(10)]],
    active: ['' as '' | 'true' | 'false'],
  });

  selectedFile: File | null = null;
  banner = '';
  apiErrors: string[] = [];
  echoResponse: EchoResult | null = null;
  searchResponse: SearchResult | null = null;
  uploadResponse: UploadResult | null = null;

  ngOnInit(): void {
    this.route.queryParamMap.subscribe((params) => {
      const banner = params.get('banner');
      this.banner = banner === 'temp-redirect'
        ? 'The API returned a 303 redirect and the Angular interceptor brought you back here.'
        : banner === 'reboot-complete'
          ? 'The simulated reboot transition page finished polling and routed you back to the demo form.'
          : '';
    });
  }

  submitEcho(): void {
    if (this.echoForm.invalid) {
      this.echoForm.markAllAsTouched();
      return;
    }

    this.resetMessages();
    const value = this.echoForm.getRawValue();
    const tags = value.tags
      .split(',')
      .map((tag) => tag.trim())
      .filter(Boolean);

    this.api.echo({
      name: value.name,
      age: Number(value.age),
      active: value.active,
      note: value.note || undefined,
      metadata: { source: value.source },
      tags,
    }).subscribe({
      next: (response) => {
        this.echoResponse = response.result ?? null;
      },
      error: (error) => this.handleApiError(error),
    });
  }

  runSearch(): void {
    if (this.searchForm.invalid) {
      this.searchForm.markAllAsTouched();
      return;
    }

    this.resetMessages();
    const value = this.searchForm.getRawValue();
    const active = value.active === '' ? '' : value.active === 'true';

    this.api.search(value.term, Number(value.limit), active).subscribe({
      next: (response) => {
        this.searchResponse = response.result ?? null;
      },
      error: (error) => this.handleApiError(error),
    });
  }

  uploadFile(): void {
    if (!this.selectedFile) {
      this.apiErrors = ['Choose a .txt, .md, or .json file before uploading.'];
      return;
    }

    this.resetMessages();
    this.api.upload(this.selectedFile).subscribe({
      next: (response) => {
        this.uploadResponse = response.result ?? null;
      },
      error: (error) => this.handleApiError(error),
    });
  }

  triggerTemporaryRedirect(): void {
    this.resetMessages();
    this.api.triggerTemporaryRedirect().subscribe({
      error: (error) => this.handleApiError(error, false),
    });
  }

  triggerErrorRedirect(): void {
    this.resetMessages();
    this.api.triggerErrorRedirect().subscribe({
      error: (error) => this.handleApiError(error, false),
    });
  }

  triggerRebootRedirect(): void {
    this.resetMessages();
    this.api.triggerRebootRedirect().subscribe({
      error: (error) => this.handleApiError(error, false),
    });
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.selectedFile = input.files?.[0] ?? null;
  }

  private resetMessages(): void {
    this.apiErrors = [];
    this.banner = '';
  }

  private handleApiError(error: unknown, showRedirectHint = true): void {
    const payload = (error as HttpErrorResponse).error as FdcApiResponse<unknown> | undefined;
    const messages = payload?.error?.map((entry) => entry.message).filter((message): message is string => Boolean(message)) ?? [];

    if (messages.length > 0) {
      this.apiErrors = messages;
      return;
    }

    if (showRedirectHint && (error as HttpErrorResponse).status === 303) {
      this.apiErrors = ['The API requested a redirect. The interceptor should have navigated automatically.'];
      return;
    }

    this.apiErrors = ['The request did not complete successfully.'];
  }
}
