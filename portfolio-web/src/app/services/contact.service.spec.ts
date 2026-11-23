import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ContactService, sha256Hex } from './contact.service';

const CAPTCHA_URL = 'https://api.julesrotilio.fr/api/captcha';
const API_URL = 'https://api.julesrotilio.fr/api/send-email';

/** Captcha dont la réponse est `number`, comme le renverrait l'API. */
export async function captchaFor(number: number) {
  return { salt: '123.abc', challenge: await sha256Hex('123.abc' + number), maxNumber: 20, signature: 'sig' };
}

/** Attend une condition remplie hors zone de test (résolution du captcha par crypto.subtle). */
export async function waitFor(condition: () => boolean) {
  for (let i = 0; i < 200 && !condition(); i++) {
    await new Promise((r) => setTimeout(r, 5));
  }
  if (!condition()) throw new Error('Condition jamais remplie');
}

describe('ContactService', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('demande un captcha à l\'API et le résout', async () => {
    let solution: unknown;
    TestBed.inject(ContactService).verify().subscribe((s) => (solution = s));

    http.expectOne(CAPTCHA_URL).flush(await captchaFor(7));
    await waitFor(() => !!solution);
    expect(solution).toEqual({ salt: '123.abc', number: 7, signature: 'sig' });
  });

  it('envoie le formulaire et la solution du captcha en POST à l\'API', () => {
    const form = { from: 'a@b.fr', subject: 'Sujet', body: 'Message' };
    const captcha = { salt: '123.abc', number: 7, signature: 'sig' };
    TestBed.inject(ContactService).sendEmail(form, captcha).subscribe();

    const req = http.expectOne(API_URL);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ ...form, captcha });
    req.flush({ success: true });
  });
});
