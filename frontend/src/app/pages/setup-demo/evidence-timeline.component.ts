import { CommonModule } from '@angular/common';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Component, Input, inject } from '@angular/core';
import { FdcApiResponse } from '../../models/http.model';

export interface EvidenceTimeline {
  datasetId: string; simulated: boolean; truncated: boolean;
  events: Array<{ id: number; occurred_at: string; device: string; action: string;
    message: string; src_ip: string | null; dst_ip: string | null }>;
}

export function evidenceTimeline(tool: string, result?: Record<string, unknown>): EvidenceTimeline | null {
  if (!['query_log_events', 'get_related_events'].includes(tool) || !result) return null;
  if (typeof result['dataset_id'] !== 'string' || !Array.isArray(result['events'])) return null;
  const events = result['events'].filter((event): event is EvidenceTimeline['events'][number] =>
    event && Number.isSafeInteger(event.id) && event.id > 0 &&
    typeof event.occurred_at === 'string' && Number.isFinite(Date.parse(event.occurred_at)) &&
    typeof event.device === 'string' && typeof event.action === 'string' && typeof event.message === 'string');
  return { datasetId: result['dataset_id'], simulated: result['simulated'] === true,
    truncated: result['truncated'] === true, events: events.slice(0, 50)
      .sort((a, b) => Date.parse(a.occurred_at) - Date.parse(b.occurred_at) || a.id - b.id) };
}

@Component({
  selector: 'app-evidence-timeline', standalone: true, imports: [CommonModule],
  template: `
    <section class="timeline" aria-label="Log evidence timeline">
      <h3>Evidence timeline · {{ timeline.simulated ? 'SIMULATED' : 'Uploaded · unverified' }}</h3>
      <small>Times in UTC · correlation is not proof of causation</small>
      @if (timeline.truncated) { <p>Partial results — narrow the query to see more.</p> }
      @if (!timeline.events.length) { <p>No matching events in this query.</p> }
      <ol>@for (event of timeline.events; track event.id) {
        <li>
          <time>{{ event.occurred_at | date:'yyyy-MM-dd HH:mm:ss':'UTC' }}</time>
          <strong>#{{ event.id }} · {{ event.action }} · {{ event.device }}</strong>
          @if (event.src_ip || event.dst_ip) { <p>{{ event.src_ip || '—' }} → {{ event.dst_ip || '—' }}</p> }
          <p>{{ event.message }}</p>
          <button type="button" (click)="showSource(event.id)">View original #{{ event.id }}</button>
        </li>
      }</ol>
      @if (error) { <p role="alert">{{ error }}</p> }
      @if (source !== null) { <details open><summary>Original normalized record #{{ sourceId }}</summary><pre>{{ source | json }}</pre></details> }
    </section>
  `,
  styles: [`
    .timeline { border:1px solid #cbd5e1; border-radius:12px; padding:16px; margin:12px 0; background:#f8fafc; color:#0f172a; }
    h3 { margin:0 0 8px; font-size:16px; } small,time { color:#475569; } ol { padding-left:20px; }
    li { padding:10px 0; border-bottom:1px solid #e2e8f0; } time,strong { display:block; } p { margin:6px 0; }
    button { background:transparent; color:#1d4ed8; border:1px solid #cbd5e1; border-radius:6px; padding:6px; cursor:pointer; }
    pre { white-space:pre-wrap; overflow-wrap:anywhere; font-size:12px; }
  `],
})
export class EvidenceTimelineComponent {
  @Input({ required: true }) timeline!: EvidenceTimeline;
  private readonly http = inject(HttpClient);
  source: unknown = null;
  sourceId: number | null = null;
  error = '';
  showSource(id: number): void {
    this.source = null; this.error = ''; this.sourceId = id;
    const params = new HttpParams().set('dataset_id', this.timeline.datasetId).set('event_id', id);
    this.http.get<FdcApiResponse<{ event: { raw: unknown } }>>('/api/demo/secure/logs/event', { params }).subscribe({
      next: ({ result }) => { if (this.sourceId === id) this.source = result?.event.raw ?? null; },
      error: () => { this.error = 'Evidence unavailable or access denied.'; },
    });
  }
}
