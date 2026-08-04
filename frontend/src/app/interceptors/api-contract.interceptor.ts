import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { FdcApiResponse } from '../models/http.model';

function normalizeRedirectPath(redirect: string): string {
  const normalized = redirect.replace(/^\/new(?=\/|$)/, '');
  return normalized || '/';
}

export const apiContractInterceptor: HttpInterceptorFn = (req, next) => {
  const router = inject(Router);

  return next(req).pipe(
    catchError((error: unknown) => {
      if (!(error instanceof HttpErrorResponse)) {
        return throwError(() => error);
      }

      const payload = error.error as FdcApiResponse<unknown> | undefined;
      const redirect = payload?.status?.redirect;

      if (error.status === 303 && redirect) {
        void router.navigateByUrl(normalizeRedirectPath(redirect));
      } else if (error.status === 338) {
        void router.navigateByUrl(normalizeRedirectPath(redirect || '/new/error'));
      }

      return throwError(() => error);
    })
  );
};
