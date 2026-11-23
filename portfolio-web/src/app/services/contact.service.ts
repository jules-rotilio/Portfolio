import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, from, switchMap } from 'rxjs';
import { environment } from '../../environments/environment';

export interface CaptchaChallenge { salt: string; challenge: string; maxNumber: number; signature: string; }
export interface CaptchaSolution { salt: string; number: number; signature: string; }

export async function sha256Hex(text: string): Promise<string> {
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(hash), (b) => b.toString(16).padStart(2, '0')).join('');
}

/** Retrouve le nombre caché par l'API (preuve de travail : quelques centaines de ms dans un navigateur). */
export async function solveCaptcha(c: CaptchaChallenge): Promise<CaptchaSolution> {
  for (let number = 0; number <= c.maxNumber; number++) {
    if (await sha256Hex(c.salt + number) === c.challenge) {
      return { salt: c.salt, number, signature: c.signature };
    }
  }
  throw new Error('Captcha insoluble');
}

@Injectable({ providedIn: 'root' })
export class ContactService {
  private apiUrl = `${environment.apiOrigin}/api`;

  constructor(private http: HttpClient) {}

  /** Demande un captcha à l'API et le résout. */
  verify(): Observable<CaptchaSolution> {
    return this.http.get<CaptchaChallenge>(`${this.apiUrl}/captcha`).pipe(switchMap((c) => from(solveCaptcha(c))));
  }

  sendEmail(form: { from: string; subject: string; body: string }, captcha: CaptchaSolution): Observable<any> {
    return this.http.post(`${this.apiUrl}/send-email`, { ...form, captcha });
  }
}
