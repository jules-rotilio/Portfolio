import { Component } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { CaptchaSolution, ContactService } from '../services/contact.service';
import { FormsModule } from '@angular/forms';
import { NgIf } from '@angular/common';

@Component({
  selector: 'app-contact',
  standalone: true,
  imports: [FormsModule, NgIf],
  templateUrl: './contact.component.html',
  styleUrl: './contact.component.scss'
})
export class ContactComponent {
  form = { from: '', subject: '', body: '' };
  success = false;
  sending = false;
  error = '';
  verifying = false;
  captcha: CaptchaSolution | null = null;

  constructor(private contactService: ContactService) {}

  verify() {
    this.verifying = true;
    this.error = '';
    this.contactService.verify().subscribe({
      next: (captcha) => {
        this.verifying = false;
        this.captcha = captcha;
      },
      error: () => {
        this.verifying = false;
        this.error = 'La vérification anti-robot a échoué. Réessayez.';
      }
    });
  }

  send() {
    if (!this.captcha) return;
    this.success = false;
    this.error = '';
    this.sending = true;
    // Une solution ne sert qu'une fois côté API : le visiteur recoche la case pour un nouvel envoi
    const captcha = this.captcha;
    this.captcha = null;
    this.contactService.sendEmail(this.form, captcha).subscribe({
      next: () => {
        this.sending = false;
        this.success = true;
        this.form = { from: '', subject: '', body: '' };
      },
      error: (err: HttpErrorResponse) => {
        this.sending = false;
        this.error = this.errorMessage(err);
      }
    });
  }

  private errorMessage(err: HttpErrorResponse): string {
    // L'API renvoie { success, message } pour les erreurs 429 et 500
    if (typeof err.error?.message === 'string') {
      return err.error.message;
    }
    if (err.status === 400) {
      return 'Vérifiez votre adresse email et le contenu du message.';
    }
    if (err.status === 0) {
      return 'Impossible de joindre le serveur. Vérifiez votre connexion.';
    }
    return 'Une erreur est survenue lors de l\'envoi. Réessayez plus tard.';
  }
}
