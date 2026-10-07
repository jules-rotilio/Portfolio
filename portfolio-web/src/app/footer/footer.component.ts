import { Component } from '@angular/core';

@Component({
  selector: 'app-footer',
  templateUrl: './footer.component.html',
  styleUrl: './footer.component.scss'
})
export class FooterComponent {
  isDark = false;
  currentYear = new Date().getFullYear();

  constructor() {
    if (typeof window !== 'undefined' && typeof localStorage !== 'undefined') {
      const saved = localStorage.getItem('theme');
      this.isDark = saved === 'dark' || (!saved && window.matchMedia('(prefers-color-scheme: dark)').matches);
    }
    this.applyTheme();
  }

  toggleTheme(event: Event) {
    this.isDark = (event.target as HTMLInputElement).checked;
    if (typeof window !== 'undefined' && typeof localStorage !== 'undefined') {
      localStorage.setItem('theme', this.isDark ? 'dark' : 'white');
    }
    this.applyTheme();
  }

  applyTheme() {
    if (typeof document !== 'undefined') {
      document.body.classList.toggle('dark-theme', this.isDark);
      document.body.classList.toggle('white-theme', !this.isDark);
    }
  }
}