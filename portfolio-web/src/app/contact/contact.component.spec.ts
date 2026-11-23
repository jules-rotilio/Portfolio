import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ContactComponent } from './contact.component';
import { captchaFor, waitFor } from '../services/contact.service.spec';

const API_URL = 'https://api.julesrotilio.fr/api/send-email';
const CAPTCHA_URL = 'https://api.julesrotilio.fr/api/captcha';

describe('ContactComponent', () => {
  let fixture: ComponentFixture<ContactComponent>;
  let component: ContactComponent;
  let http: HttpTestingController;
  let element: HTMLElement;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ContactComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(ContactComponent);
    component = fixture.componentInstance;
    http = TestBed.inject(HttpTestingController);
    element = fixture.nativeElement;
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  const submitButton = () => element.querySelector('button[type="submit"]') as HTMLButtonElement;
  const alertText = (kind: 'success' | 'danger') => element.querySelector(`.alert-${kind}`)?.textContent?.trim();

  async function fillForm(from = 'visiteur@example.com', subject = 'Bonjour', body = 'Un message') {
    component.form = { from, subject, body };
    fixture.detectChanges();
    await fixture.whenStable(); // laisse ngModel mettre à jour la validité du formulaire
    fixture.detectChanges();
  }

  const captchaBox = () => element.querySelector('#captcha') as HTMLInputElement;

  async function tickCaptcha() {
    captchaBox().click();
    fixture.detectChanges();
    http.expectOne(CAPTCHA_URL).flush(await captchaFor(3));
    await waitFor(() => !!component.captcha);
    fixture.detectChanges();
  }

  async function send() {
    await tickCaptcha();
    submitButton().click();
    fixture.detectChanges();
    return http.expectOne(API_URL);
  }

  async function sendAndRespond(body: object | string, status = 200) {
    const req = await send();
    if (status === 200) {
      req.flush(body);
    } else if (status === 0) {
      req.error(new ProgressEvent('error'), { status: 0 });
    } else {
      req.flush(body, { status, statusText: 'Erreur' });
    }
    fixture.detectChanges();
  }

  it('désactive le bouton tant que le formulaire est incomplet', async () => {
    await fillForm('visiteur@example.com', 'Bonjour', '');
    expect(submitButton().disabled).toBeTrue();
  });

  it('désactive le bouton si l\'adresse email est invalide', async () => {
    await fillForm('pas-un-email');
    expect(submitButton().disabled).toBeTrue();
  });

  it('désactive le bouton tant que la case anti-robot n\'est pas cochée', async () => {
    await fillForm();
    expect(submitButton().disabled).toBeTrue();

    await tickCaptcha();
    expect(element.textContent).toContain('Vérifié');
    expect(captchaBox().disabled).toBeTrue();
    expect(submitButton().disabled).toBeFalse();
  });

  it('demande de recocher la case après un envoi (solution à usage unique)', async () => {
    await fillForm();
    await sendAndRespond({ success: false, message: 'Erreur' }, 500);

    expect(captchaBox().checked).toBeFalse();
    expect(captchaBox().disabled).toBeFalse();
    expect(submitButton().disabled).toBeTrue();
  });

  it('applique les mêmes limites de longueur que l\'API', () => {
    expect(element.querySelector('#from')?.getAttribute('maxlength')).toBe('254');
    expect(element.querySelector('#subject')?.getAttribute('maxlength')).toBe('150');
    expect(element.querySelector('#body')?.getAttribute('maxlength')).toBe('5000');
  });

  it('bloque un double envoi pendant que la requête est en cours', async () => {
    await fillForm();
    const req = await send();

    expect(submitButton().disabled).toBeTrue();
    expect(submitButton().textContent).toContain('Envoi en cours');
    req.flush({ success: true });
  });

  it('confirme l\'envoi et vide le formulaire', async () => {
    await fillForm();
    await sendAndRespond({ success: true, message: 'Email envoyé.' });

    expect(alertText('success')).toContain('Message envoyé');
    expect(component.form).toEqual({ from: '', subject: '', body: '' });
    expect(submitButton().textContent).toContain('Envoyer');
  });

  it('affiche le message de l\'API quand la limite d\'envoi est atteinte', async () => {
    await fillForm();
    await sendAndRespond({ success: false, message: 'Trop de messages envoyés. Réessayez dans une heure.' }, 429);

    expect(alertText('danger')).toBe('Trop de messages envoyés. Réessayez dans une heure.');
    expect(component.form.body).toBe('Un message'); // le visiteur ne perd pas son message
  });

  it('affiche un message clair si l\'API refuse les données (400)', async () => {
    await fillForm();
    await sendAndRespond({ title: 'One or more validation errors occurred.' }, 400);

    expect(alertText('danger')).toBe('Vérifiez votre adresse email et le contenu du message.');
  });

  it('affiche un message clair si le serveur est injoignable', async () => {
    await fillForm();
    await sendAndRespond('', 0);

    expect(alertText('danger')).toBe('Impossible de joindre le serveur. Vérifiez votre connexion.');
  });

  it('efface l\'ancienne erreur lors d\'un nouvel envoi réussi', async () => {
    await fillForm();
    await sendAndRespond({ success: false, message: 'Erreur' }, 500);
    expect(alertText('danger')).toBeTruthy();

    await sendAndRespond({ success: true });
    expect(alertText('danger')).toBeUndefined();
    expect(alertText('success')).toContain('Message envoyé');
  });

  it('ne propose pas de liens vers des sites d\'emploi sans profil', () => {
    const hrefs = Array.from(element.querySelectorAll('a')).map((a) => a.getAttribute('href') ?? '');
    expect(hrefs.some((h) => /indeed|hellowork|francetravail/.test(h))).toBeFalse();
    expect(element.textContent).toContain('Également présent sur France Travail, HelloWork et Indeed.');
  });
});
