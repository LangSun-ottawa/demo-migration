export interface ApiErrorEntry {
  code?: string;
  message?: string;
}

export interface ApiStatus {
  return_code: number;
  message?: string;
  redirect?: string;
}

export interface FdcApiResponse<T> {
  status: ApiStatus;
  result?: T;
  error?: ApiErrorEntry[];
}
