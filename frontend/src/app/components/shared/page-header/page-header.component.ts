import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ButtonModule } from 'carbon-components-angular';
import { IconModule } from 'carbon-components-angular/icon';

@Component({
  selector: 'app-page-header',
  standalone: true,
  imports: [CommonModule, ButtonModule, IconModule],
  templateUrl: './page-header.component.html',
  styleUrls: ['./page-header.component.scss']
})
export class PageHeaderComponent {
  @Input() title: string = '';
  @Input() subtitle?: string;
  @Input() breadcrumbs?: { label: string; route?: string }[] = [];
}

// Made with Bob
