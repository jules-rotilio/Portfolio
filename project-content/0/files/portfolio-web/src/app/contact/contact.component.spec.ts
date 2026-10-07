import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ContactComponent } from './contact.component';

const API_URL = 'https://api.julesrotilio.fr/api/send-email';

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

  function sendAndRespond(body: object | string, status = 200) {
    submitButton().click();
    fixture.detectChanges();
    const req = http.expectOne(API_URL);
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

  it('applique les mêmes limites de longueur que l\'API', () => {
    expect(element.querySelector('#from')?.getAttribute('maxlength')).toBe('254');
    expect(element.querySelector('#subject')?.getAttribute('maxlength')).toBe('150');
    expect(element.querySelector('#body')?.getAttribute('maxlength')).toBe('5000');
  });

  it('bloque un double envoi pendant que la requête est en cours', async () => {
    await fillForm();
    submitButton().click();
    fixture.detectChanges();

    expect(submitButton().disabled).toBeTrue();
    expect(submitButton().textContent).toContain('Envoi en cours');
    http.expectOne(API_URL).flush({ success: true });
  });

  it('confirme l\'envoi et vide le formulaire', async () => {
    await fillForm();
    sendAndRespond({ success: true, message: 'Email envoyé.' });

    expect(alertText('success')).toContain('Message envoyé');
    expect(component.form).toEqual({ from: '', subject: '', body: '' });
    expect(submitButton().textContent).toContain('Envoyer');
  });

  it('affiche le message de l\'API quand la limite d\'envoi est atteinte', async () => {
    await fillForm();
    sendAndRespond({ success: false, message: 'Trop de messages envoyés. Réessayez dans une heure.' }, 429);

    expect(alertText('danger')).toBe('Trop de messages envoyés. Réessayez dans une heure.');
    expect(component.form.body).toBe('Un message'); // le visiteur ne perd pas son message
  });

  it('affiche un message clair si l\'API refuse les données (400)', async () => {
    await fillForm();
    sendAndRespond({ title: 'One or more validation errors occurred.' }, 400);

    expect(alertText('danger')).toBe('Vérifiez votre adresse email et le contenu du message.');
  });

  it('affiche un message clair si le serveur est injoignable', async () => {
    await fillForm();
    sendAndRespond('', 0);

    expect(alertText('danger')).toBe('Impossible de joindre le serveur. Vérifiez votre connexion.');
  });

  it('efface l\'ancienne erreur lors d\'un nouvel envoi réussi', async () => {
    await fillForm();
    sendAndRespond({ success: false, message: 'Erreur' }, 500);
    expect(alertText('danger')).toBeTruthy();

    sendAndRespond({ success: true });
    expect(alertText('danger')).toBeUndefined();
    expect(alertText('success')).toContain('Message envoyé');
  });

  it('ne propose pas de liens vers des sites d\'emploi sans profil', () => {
    const hrefs = Array.from(element.querySelectorAll('a')).map((a) => a.getAttribute('href') ?? '');
    expect(hrefs.some((h) => /indeed|hellowork|francetravail/.test(h))).toBeFalse();
    expect(element.textContent).toContain('Également présent sur France Travail, HelloWork et Indeed.');
  });
});
