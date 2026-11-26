import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { AssistantMarkdownPipe } from './assistant-markdown.pipe';

@Component({ standalone: true, imports: [AssistantMarkdownPipe], template: '<div [innerHTML]="text | assistantMarkdown"></div>' })
class MarkdownHost {
  text = '';
}

describe('Assistant Markdown', () => {
  it('renders bold, lists, inline code and fenced code', () => {
    const html = new AssistantMarkdownPipe().transform('- **Profile:** `demo`\n\n```json\n{"id": 6}\n```');
    expect(html).toContain('<strong>Profile:</strong>');
    expect(html).toContain('<li>');
    expect(html).toContain('<code>demo</code>');
    expect(html).toContain('<pre><code');
  });

  it('does not render model HTML or allow executable link protocols', () => {
    TestBed.configureTestingModule({ imports: [MarkdownHost] });
    const fixture = TestBed.createComponent(MarkdownHost);
    fixture.componentInstance.text = '<img src=x onerror="alert(1)">\n\n<script>alert(1)</script>\n\n[click](javascript:alert%281%29)';
    fixture.detectChanges();
    const element: HTMLElement = fixture.nativeElement;
    expect(element.querySelector('script')).toBeNull();
    expect(element.querySelector('[onerror]')).toBeNull();
    expect(element.querySelector('img')).toBeNull();
    expect(element.querySelector('a')?.getAttribute('href')).not.toMatch(/^javascript:/i);
  });
});
