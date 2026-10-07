import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ContactService } from './contact.service';

describe('ContactService', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('envoie le formulaire en POST à l\'API', () => {
    const form = { from: 'a@b.fr', subject: 'Sujet', body: 'Message' };
    TestBed.inject(ContactService).sendEmail(form).subscribe();

    const req = http.expectOne('https://api.julesrotilio.fr/api/send-email');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(form);
    req.flush({ success: true });
  });
});
