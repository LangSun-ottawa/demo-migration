import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { FdcApiResponse } from '../models/http.model';

export interface LogDataset {
  id: string; name: string; simulated: boolean; event_count: number; start: string; end: string;
}
export type LogScenario = 'policy_block' | 'normal' | 'insufficient';

@Injectable({ providedIn: 'root' })
export class LogEvidenceService {
  private readonly http = inject(HttpClient);
  list() { return this.http.get<FdcApiResponse<{ datasets: LogDataset[] }>>('/api/demo/secure/logs/datasets'); }
  demo(scenario: LogScenario = 'policy_block') { return this.http.post<FdcApiResponse<{ dataset: LogDataset }>>('/api/demo/secure/logs/demo', { scenario }); }
  upload(file: File) {
    const form = new FormData(); form.append('attachment', file);
    return this.http.post<FdcApiResponse<{ dataset: LogDataset }>>('/api/demo/secure/logs/upload', form);
  }
}
