import { CommonModule } from '@angular/common';
import { Component, inject } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';

@Component({
  selector: 'app-legacy-frame',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './legacy-frame.component.html',
  styleUrl: './legacy-frame.component.scss',
})
export class LegacyFrameComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly sanitizer = inject(DomSanitizer);

  readonly title = this.route.snapshot.data['title'] ?? 'Embedded legacy page';
  readonly description =
    this.route.snapshot.data['description'] ??
    'This route keeps Angular in charge of layout and navigation while Django still renders the page itself.';
  readonly legacyUrl = this.buildLegacyUrl();

  private buildLegacyUrl(): SafeResourceUrl {
    const target = this.route.snapshot.data['legacyUrl'] ?? '/legacy/report/';
    return this.sanitizer.bypassSecurityTrustResourceUrl(target);
  }
}
