import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { HeaderComponent } from './header.component';

describe('HeaderComponent', () => {
  let fixture: ComponentFixture<HeaderComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HeaderComponent],
      providers: [provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(HeaderComponent);
    fixture.detectChanges();
  });

  it('propose un lien vers chaque page du site', () => {
    const links = Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('nav a'))
      .map((a) => a.getAttribute('href'));

    expect(links).toEqual(['/', '/cv', '/projets', '/contact']);
  });
});
