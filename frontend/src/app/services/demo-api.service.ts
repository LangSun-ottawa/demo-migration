import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { FdcApiResponse } from '../models/http.model';

export interface EchoPayload {
  name: string;
  age: number;
  active: boolean;
  note?: string;
  metadata: {
    source: string;
  };
  tags: string[];
}

export interface EchoResult {
  sanitized_name: string;
  submitted: EchoPayload;
  summary: string;
}

export interface SearchItem {
  id: number;
  name: string;
  active: boolean;
  category: string;
}

export interface SearchResult {
  items: SearchItem[];
  count: number;
}

export interface UploadResult {
  filename: string;
  content_type: string;
  size: number;
}

export interface TraceStep {
  stage: string;
  detail: string;
}

export interface ContractMetadata {
  view_class: string;
  schema_name: string;
  http_method: string;
  schema_modes: string[];
}

export interface SessionResult {
  authenticated: boolean;
  username: string | null;
  contract: ContractMetadata;
  trace: TraceStep[];
}

export interface ModelQueryResult {
  model: string;
  database: string;
  sql_template: string;
  bound_params: unknown;
  items: Array<{
    id: number;
    name: string;
    category: string;
    active: boolean;
  }>;
}

export interface ModelComparisonResult {
  search_term_preserved: string;
  django_orm: ModelQueryResult;
  sqlalchemy: ModelQueryResult;
  security_conclusion: string;
  contract: ContractMetadata;
  trace: TraceStep[];
}

export interface SecurityInspectionResult {
  validated_payload: {
    display_name: string;
    lookup_term: string;
    safe_identifier: string;
  };
  processing: string[];
  model_comparison: ModelComparisonResult;
  contract: ContractMetadata;
  trace: TraceStep[];
}

export interface ContractCatalogResult {
  contracts: Array<{
    view_class: string;
    schema_name: string;
    method: string;
    fields: string[];
  }>;
  models: Array<{
    class: string;
    base: string;
    session: string;
  }>;
  contract: ContractMetadata;
  trace: TraceStep[];
}

@Injectable({ providedIn: 'root' })
export class DemoApiService {
  private readonly http = inject(HttpClient);

  echo(payload: EchoPayload): Observable<FdcApiResponse<EchoResult>> {
    return this.http.post<FdcApiResponse<EchoResult>>('/api/demo/echo', payload);
  }

  search(term: string, limit?: number, active?: boolean | ''): Observable<FdcApiResponse<SearchResult>> {
    let params = new HttpParams().set('term', term);
    if (limit !== undefined && limit !== null) {
      params = params.set('limit', limit);
    }
    if (active !== '') {
      params = params.set('active', String(active));
    }

    return this.http.get<FdcApiResponse<SearchResult>>('/api/demo/search', { params });
  }

  upload(file: File): Observable<FdcApiResponse<UploadResult>> {
    const body = new FormData();
    body.append('attachment', file);
    return this.http.post<FdcApiResponse<UploadResult>>('/api/demo/upload', body);
  }

  triggerTemporaryRedirect(): Observable<FdcApiResponse<never>> {
    return this.http.post<FdcApiResponse<never>>('/api/demo/redirect/temp', null);
  }

  triggerErrorRedirect(): Observable<FdcApiResponse<never>> {
    return this.http.post<FdcApiResponse<never>>('/api/demo/redirect/error', null);
  }

  triggerRebootRedirect(): Observable<FdcApiResponse<never>> {
    return this.http.post<FdcApiResponse<never>>('/api/demo/system/reboot', null);
  }

  getSession(): Observable<FdcApiResponse<SessionResult>> {
    return this.http.get<FdcApiResponse<SessionResult>>('/api/demo/auth/session');
  }

  login(username: string, password: string): Observable<FdcApiResponse<SessionResult>> {
    return this.http.post<FdcApiResponse<SessionResult>>('/api/demo/auth/login', {
      username,
      password,
    });
  }

  logout(): Observable<FdcApiResponse<SessionResult>> {
    return this.http.post<FdcApiResponse<SessionResult>>('/api/demo/auth/logout', null);
  }

  getContractCatalog(): Observable<FdcApiResponse<ContractCatalogResult>> {
    return this.http.get<FdcApiResponse<ContractCatalogResult>>('/api/demo/contracts');
  }

  inspectSecurity(payload: {
    display_name: string;
    lookup_term: string;
    safe_identifier: string;
  }): Observable<FdcApiResponse<SecurityInspectionResult>> {
    return this.http.post<FdcApiResponse<SecurityInspectionResult>>(
      '/api/demo/secure/security/inspect',
      payload,
    );
  }

  compareModels(term: string): Observable<FdcApiResponse<ModelComparisonResult>> {
    const params = new HttpParams().set('term', term);
    return this.http.get<FdcApiResponse<ModelComparisonResult>>(
      '/api/demo/secure/models',
      { params },
    );
  }
}
