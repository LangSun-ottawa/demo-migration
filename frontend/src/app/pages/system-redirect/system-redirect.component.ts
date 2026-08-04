import { CommonModule } from '@angular/common';
import { HttpBackend, HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { EMPTY, Subject, catchError, concatMap, expand, map, of, switchMap, takeUntil, tap, timer } from 'rxjs';

import { FdcApiResponse } from '../../models/http.model';

const REDIRECT_INIT_DELAY = 1200;
const REDIRECT_PERIOD = 2000;

@Component({
  selector: 'app-system-redirect',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './system-redirect.component.html',
  styleUrl: './system-redirect.component.scss',
})
export class SystemRedirectComponent implements OnInit, OnDestroy {
  private readonly handler = inject(HttpBackend);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyed = new Subject<void>();
  private readonly http = new HttpClient(this.handler);

  title = 'Demo System Rebooting';
  message = 'The demo is simulating a system reboot. This page keeps polling until the backend reports that the system is available again.';
  statusLabel = 'Waiting to start the first health check...';
  operation = '';
  pollCount = 0;

  ngOnInit(): void {
    this.route.queryParamMap.subscribe((params) => {
      const type = params.get('type');
      const operation = params.get('operation');

      if (type !== 'reboot' || !operation) {
        void this.router.navigateByUrl('/demo/form');
        return;
      }

      this.operation = operation;
      this.startPolling(operation);
    });
  }

  ngOnDestroy(): void {
    this.destroyed.next();
    this.destroyed.complete();
  }

  private startPolling(operation: string): void {
    timer(REDIRECT_INIT_DELAY)
      .pipe(
        takeUntil(this.destroyed),
        switchMap(() => this.checkSystemAvailability(operation)),
        expand((ready) => {
          if (ready) {
            return EMPTY;
          }

          return timer(REDIRECT_PERIOD).pipe(
            takeUntil(this.destroyed),
            concatMap(() => this.checkSystemAvailability(operation)),
          );
        }),
      )
      .subscribe((ready) => {
        if (ready) {
          void this.router.navigateByUrl('/demo/form?banner=reboot-complete');
        }
      });
  }

  private checkSystemAvailability(operation: string) {
    return this.http.get<FdcApiResponse<{ ready: boolean }>>('/api/demo/system/status', {
      observe: 'response',
      params: { operation },
    }).pipe(
      map((response) => response.status === 200 && response.body?.result?.ready === true),
      tap((ready) => {
        this.pollCount += 1;
        this.statusLabel = ready
          ? 'The backend is reachable again. Returning to the demo form...'
          : 'The backend responded, but the operation is still marked as in progress.';
      }),
      catchError((error: HttpErrorResponse) => {
        const payload = error.error as FdcApiResponse<unknown> | undefined;
        const message = payload?.status?.message || 'The backend is still unavailable.';
        this.pollCount += 1;
        this.statusLabel = `${message} Checking again in ${REDIRECT_PERIOD / 1000} seconds...`;
        return of(false);
      }),
    );
  }
}
