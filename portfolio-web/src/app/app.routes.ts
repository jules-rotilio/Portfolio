import { Routes } from '@angular/router';
import { HomeComponent } from './home/home.component';
import { CVComponent } from './cv/cv.component';
import { ProjetsComponent } from './projets/projets.component';
import { ContactComponent } from './contact/contact.component';

export const routes: Routes = [
  { path: '', component: HomeComponent },
  { path: 'cv', component: CVComponent },
  { path: 'projets', component: ProjetsComponent },
  { path: 'contact', component: ContactComponent },
  { path: '**', redirectTo: '' }, // Redirige les routes inconnues vers l'accueil
];
