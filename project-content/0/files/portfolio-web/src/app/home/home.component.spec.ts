import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { HomeComponent } from './home.component';

describe('HomeComponent', () => {
  let fixture: ComponentFixture<HomeComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HomeComponent],
      providers: [provideRouter([])],
    }).compileComponents();

    fixture = TestBed.createComponent(HomeComponent);
    fixture.detectChanges();
  });

  it('mène vers les projets et le contact', () => {
    const links = Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('.actions a'))
      .map((a) => a.getAttribute('href'));

    expect(links).toEqual(['/projets', '/contact']);
  });
});
