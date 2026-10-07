import { TestBed } from '@angular/core/testing';
import { FooterComponent } from './footer.component';

describe('FooterComponent', () => {
  beforeEach(async () => {
    localStorage.removeItem('theme');
    await TestBed.configureTestingModule({ imports: [FooterComponent] }).compileComponents();
  });

  afterEach(() => {
    localStorage.removeItem('theme');
    document.body.classList.remove('dark-theme', 'white-theme');
  });

  function toggle(checked: boolean) {
    const fixture = TestBed.createComponent(FooterComponent);
    fixture.detectChanges();
    const input = (fixture.nativeElement as HTMLElement).querySelector('input[type="checkbox"]') as HTMLInputElement;
    input.checked = checked;
    input.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    return fixture;
  }

  it('passe en thème sombre et mémorise le choix', () => {
    const fixture = toggle(true);

    expect(document.body.classList).toContain('dark-theme');
    expect(document.body.classList).not.toContain('white-theme');
    expect(localStorage.getItem('theme')).toBe('dark');
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Thème Sombre');
  });

  it('repasse en thème clair et mémorise le choix', () => {
    toggle(false);

    expect(document.body.classList).toContain('white-theme');
    expect(document.body.classList).not.toContain('dark-theme');
    expect(localStorage.getItem('theme')).toBe('white');
  });

  it('réapplique le thème mémorisé au chargement', () => {
    localStorage.setItem('theme', 'dark');
    const fixture = TestBed.createComponent(FooterComponent);

    expect(fixture.componentInstance.isDark).toBeTrue();
    expect(document.body.classList).toContain('dark-theme');
  });

  it('affiche l\'année en cours', () => {
    const fixture = TestBed.createComponent(FooterComponent);
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).textContent).toContain(`© ${new Date().getFullYear()}`);
  });
});
