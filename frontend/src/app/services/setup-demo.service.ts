import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';

import { FdcApiResponse } from '../models/http.model';

export interface SetupSnapshot {
  profiles: Array<{ id: number; name: string; access_level: string }>;
  users: Array<{
    id: number;
    username: string;
    email: string;
    profile_id: number;
    profile_name: string;
  }>;
  instances: Array<{
    id: number;
    name: string;
    environment: string;
    status: string;
  }>;
  adapters: Array<{
    id: number;
    name: string;
    adapter_type: string;
    endpoint: string;
    instance_id: number;
    instance_name: string;
    status: string;
  }>;
}

@Injectable({ providedIn: 'root' })
export class SetupDemoService {
  private readonly http = inject(HttpClient);

  load() {
    return this.http.get<FdcApiResponse<SetupSnapshot>>('/api/demo/secure/setup');
  }

  createProfile(payload: { name: string; access_level: string }) {
    return this.http.post<FdcApiResponse<SetupSnapshot>>(
      '/api/demo/secure/setup/profiles', payload,
    );
  }

  createUser(payload: { username: string; email: string; profile_id: number }) {
    return this.http.post<FdcApiResponse<SetupSnapshot>>(
      '/api/demo/secure/setup/users', payload,
    );
  }

  createInstance(payload: { name: string; environment: string }) {
    return this.http.post<FdcApiResponse<SetupSnapshot>>(
      '/api/demo/secure/setup/instances', payload,
    );
  }

  createAdapter(payload: {
    name: string;
    adapter_type: string;
    endpoint: string;
    instance_id: number;
  }) {
    return this.http.post<FdcApiResponse<SetupSnapshot>>(
      '/api/demo/secure/setup/adapters', payload,
    );
  }

  update(resource: 'profiles' | 'users' | 'instances' | 'adapters', id: number, payload: object) {
    return this.http.put<FdcApiResponse<SetupSnapshot>>(
      `/api/demo/secure/setup/${resource}/${id}`, payload,
    );
  }

  delete(resource: 'profiles' | 'users' | 'instances' | 'adapters', id: number) {
    return this.http.delete<FdcApiResponse<SetupSnapshot>>(
      `/api/demo/secure/setup/${resource}/${id}`,
    );
  }
}
