import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ProjetsComponent } from './projets.component';

const API_URL = 'https://api.julesrotilio.fr/api/projects';

function project(id: number, technologies: string[] = ['C#']) {
  return { id, name: `Projet ${id}`, description: `Description ${id}`, technologies };
}

describe('ProjetsComponent', () => {
  let fixture: ComponentFixture<ProjetsComponent>;
  let http: HttpTestingController;
  let element: HTMLElement;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ProjetsComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(ProjetsComponent);
    http = TestBed.inject(HttpTestingController);
    element = fixture.nativeElement;
    fixture.detectChanges(); // ngOnInit -> requête HTTP
  });

  afterEach(() => http.verify());

  it('affiche une carte par projet, avec ses technologies', () => {
    http.expectOne(API_URL).flush([project(0, ['C#', '.NET 10', 'Angular']), project(1)]);
    fixture.detectChanges();

    const titles = Array.from(element.querySelectorAll('.card-title')).map((t) => t.textContent?.trim());
    expect(titles).toEqual(['Projet 0', 'Projet 1']);

    const badges = Array.from(element.querySelectorAll('.card')[0].querySelectorAll('.badge')).map((b) => b.textContent?.trim());
    expect(badges).toEqual(['C#', '.NET 10', 'Angular']);
  });

  it('range les projets par lignes de deux (dernière ligne incomplète)', () => {
    http.expectOne(API_URL).flush([project(0), project(1), project(2)]);
    fixture.detectChanges();

    const rows = element.querySelectorAll('.row');
    expect(rows.length).toBe(2);
    expect(rows[0].querySelectorAll('.card').length).toBe(2);
    expect(rows[1].querySelectorAll('.card').length).toBe(1);
  });

  it('n\'affiche aucune carte si l\'API est en erreur', () => {
    spyOn(console, 'error'); // l'erreur est journalisée, on évite le bruit dans la sortie des tests
    http.expectOne(API_URL).flush('KO', { status: 500, statusText: 'Server Error' });
    fixture.detectChanges();

    expect(element.querySelectorAll('.card').length).toBe(0);
  });
});
