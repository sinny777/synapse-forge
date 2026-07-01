import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, ActivatedRoute } from '@angular/router';
import { IconModule } from 'carbon-components-angular/icon';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule, IconModule],
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.scss']
})
export class LoginComponent implements OnInit {
  // Credential login form
  email = '';
  password = '';
  loginError = '';
  isLoading = false;

  // OAuth provider availability
  googleAvailable = false;
  githubAvailable = false;

  // OAuth error from redirect
  oauthError = '';

  constructor(
    private authService: AuthService,
    private router: Router,
    private route: ActivatedRoute
  ) {}

  ngOnInit(): void {
    // Check for OAuth error query param (set by backend callback on failure)
    this.route.queryParams.subscribe(params => {
      if (params['error'] === 'oauth_failed') {
        this.oauthError = 'OAuth authentication failed. Please try again or use email/password.';
      }
    });

    // Check which OAuth providers are configured on the server
    this.authService.getProviders().subscribe({
      next: (providers) => {
        this.googleAvailable = providers.google;
        this.githubAvailable = providers.github;
      },
      error: () => {
        // Backend unreachable — leave both disabled
      }
    });

    // If already authenticated, redirect to home
    this.authService.checkAuth().subscribe(user => {
      if (user) {
        this.router.navigate(['/']);
      }
    });
  }

  loginWithGoogle(): void {
    window.location.href = 'http://localhost:8000/api/auth/login/google';
  }

  loginWithGithub(): void {
    window.location.href = 'http://localhost:8000/api/auth/login/github';
  }

  loginWithCredentials(): void {
    if (!this.email || !this.password) {
      this.loginError = 'Please enter your email and password.';
      return;
    }
    this.isLoading = true;
    this.loginError = '';
    this.authService.loginWithCredentials(this.email, this.password).subscribe({
      next: () => {
        this.isLoading = false;
        this.router.navigate(['/']);
      },
      error: (err) => {
        this.isLoading = false;
        this.loginError = err.error?.detail || 'Invalid email or password.';
      }
    });
  }
}
