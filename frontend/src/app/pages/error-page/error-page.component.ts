import { CommonModule } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

@Component({
  selector: 'app-error-page',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './error-page.component.html',
  styleUrl: './error-page.component.scss',
})
export class ErrorPageComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);

  reason = 'unknown';

  ngOnInit(): void {
    this.route.queryParamMap.subscribe((params) => {
      this.reason = params.get('reason') ?? 'unknown';
    });
  }
}
