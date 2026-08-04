import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

interface NavItem {
  label: string;
  description: string;
  path?: string;
  href?: string;
}

interface NavSection {
  label: string;
  items: NavItem[];
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss'
})
export class AppComponent {
  title = 'Coexist Demo';
  readonly navSections: NavSection[] = [
    {
      label: 'Workspace',
      items: [
        {
          label: 'API Contract Playground',
          description: 'Four independent JSON, query, upload, and redirect experiments',
          path: '/demo/form',
        },
        {
          label: 'Security & ORM Lab',
          description: 'Session auth, dispatch schemas, injection defenses, and two ORMs',
          path: '/architecture',
        },
        {
          label: 'Context Assistant',
          description: 'Django page state through FastAPI to a streaming assistant',
          path: '/context-assistant',
        },
        {
          label: 'Legacy Report',
          description: 'Django template embedded inside the Angular shell',
          path: '/legacy/report',
        },
      ],
    },
    {
      label: 'Escape Hatch',
      items: [
        {
          label: 'Raw Django Page',
          description: 'Direct backend-rendered route outside the Angular shell',
          href: '/legacy/report/',
        },
      ],
    },
  ];
}
