import { Pipe, PipeTransform } from '@angular/core';
import { Marked, Renderer } from 'marked';

const renderer = new Renderer();
// Treat model-provided HTML as text. Angular additionally sanitizes [innerHTML].
renderer.html = ({ text }) => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const markdown = new Marked({ renderer, gfm: true, breaks: true });

@Pipe({ name: 'assistantMarkdown', standalone: true })
export class AssistantMarkdownPipe implements PipeTransform {
  transform(value: string): string {
    return markdown.parse(value, { async: false });
  }
}
