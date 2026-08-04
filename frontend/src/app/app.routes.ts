import { Routes } from '@angular/router';

import { DemoFormComponent } from './pages/demo-form/demo-form.component';
import { ErrorPageComponent } from './pages/error-page/error-page.component';
import { LegacyFrameComponent } from './pages/legacy-frame/legacy-frame.component';
import { SystemRedirectComponent } from './pages/system-redirect/system-redirect.component';
import { ArchitectureLabComponent } from './pages/architecture-lab/architecture-lab.component';
import { ContextAssistantComponent } from './pages/context-assistant/context-assistant.component';

export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    redirectTo: 'demo/form',
  },
  {
    path: 'demo/form',
    component: DemoFormComponent,
  },
  {
    path: 'architecture',
    component: ArchitectureLabComponent,
  },
  {
    path: 'context-assistant',
    component: ContextAssistantComponent,
  },
  {
    path: 'legacy/report',
    component: LegacyFrameComponent,
    data: {
      title: 'Legacy report inside Angular',
      description:
        'This matches the old project pattern more closely: Angular keeps the shell and side navigation, while Django still renders the legacy page in an iframe.',
      legacyUrl: '/legacy/report/',
    },
  },
  {
    path: 'error',
    component: ErrorPageComponent,
  },
  {
    path: 'system/redirect',
    component: SystemRedirectComponent,
  },
  {
    path: '**',
    redirectTo: 'demo/form',
  },
];
