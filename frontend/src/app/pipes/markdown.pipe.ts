import { Pipe, PipeTransform } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { marked } from 'marked';

@Pipe({
  name: 'markdown',
  standalone: true
})
export class MarkdownPipe implements PipeTransform {
  constructor(private sanitizer: DomSanitizer) {
    // Configure marked options
    marked.setOptions({
      gfm: true, // GitHub Flavored Markdown
      breaks: true, // Convert \n to <br>
      pedantic: false,
      silent: false
    });
  }

  transform(value: string): SafeHtml {
    if (!value) return '';
    
    try {
      // Use marked library to parse markdown
      const html = marked.parse(value) as string;
      return this.sanitizer.bypassSecurityTrustHtml(html);
    } catch (error) {
      console.error('Markdown pipe error:', error, 'Input:', value);
      // Fallback to plain text with line breaks
      return this.sanitizer.bypassSecurityTrustHtml(
        '<pre style="white-space: pre-wrap; font-family: inherit;">' +
        value.replace(/</g, '<').replace(/>/g, '>') +
        '</pre>'
      );
    }
  }
}

// Made with Bob
