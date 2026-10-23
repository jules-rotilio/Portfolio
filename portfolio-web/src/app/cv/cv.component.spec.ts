import { ComponentFixture, TestBed } from '@angular/core/testing';

import { CVComponent } from './cv.component';

describe('CVComponent', () => {
  let component: CVComponent;
  let fixture: ComponentFixture<CVComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CVComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(CVComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should only open the first experience missions by default', () => {
    expect(component.isOpen(0)).toBeTrue();
    expect(component.isOpen(1)).toBeFalse();
  });

  it('should toggle the missions of an experience', () => {
    const toggle: HTMLButtonElement = fixture.nativeElement.querySelectorAll('.missions-toggle')[1];
    expect(toggle.getAttribute('aria-expanded')).toBe('false');

    toggle.click();
    fixture.detectChanges();
    expect(toggle.getAttribute('aria-expanded')).toBe('true');

    toggle.click();
    fixture.detectChanges();
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
  });
});
