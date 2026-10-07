import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { AppComponent } from './app.component';

describe('AppComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [provideRouter([])],
    }).compileComponents();
  });

  it('affiche l\'en-tête, le contenu et le pied de page', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.querySelector('app-header')).not.toBeNull();
    expect(compiled.querySelector('main router-outlet')).not.toBeNull();
    expect(compiled.querySelector('app-footer')).not.toBeNull();
  });
});
