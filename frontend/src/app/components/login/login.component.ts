import { Component, EventEmitter, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IconModule } from 'carbon-components-angular/icon';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, IconModule],
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.scss']
})
export class LoginComponent {
  loginWithGoogle() {
    window.location.href = 'http://localhost:8000/api/auth/login/google';
  }

  loginWithGithub() {
    window.location.href = 'http://localhost:8000/api/auth/login/github';
  }
}
