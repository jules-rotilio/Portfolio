import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ProjectsService } from './projects.service';

describe('ProjectsService', () => {
  let service: ProjectsService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(ProjectsService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('récupère les projets depuis l\'API', () => {
    let result: unknown;
    service.getProjects().subscribe((data) => (result = data));

    const req = http.expectOne('https://api.julesrotilio.fr/api/projects');
    expect(req.request.method).toBe('GET');
    req.flush([{ id: 0, name: 'Projet' }]);

    expect(result).toEqual([{ id: 0, name: 'Projet' }]);
  });
});
