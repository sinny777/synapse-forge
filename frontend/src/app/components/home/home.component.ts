import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { IconModule } from 'carbon-components-angular/icon';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [CommonModule, IconModule],
  templateUrl: './home.component.html',
  styleUrls: ['./home.component.scss']
})
export class HomeComponent {
  constructor(private router: Router) {}

  navigateToWorkflow(): void {
    this.router.navigate(['/workflow']);
  }

  openGithub(): void {
    window.open('https://github.com/sinny777/synapse-forge', '_blank');
  }
}

// Made with Bob
