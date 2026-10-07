import { Component } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { ContactService } from '../services/contact.service';
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

  constructor(private contactService: ContactService) {}

  send() {
    this.success = false;
    this.error = '';
    this.sending = true;
    this.contactService.sendEmail(this.form).subscribe({
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
