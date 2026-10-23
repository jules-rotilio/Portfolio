import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

@Injectable({ providedIn: 'root' })
export class ContactService {
  private apiUrl = `${environment.apiOrigin}/api/send-email`;

  constructor(private http: HttpClient) {}

  sendEmail(form: { from: string; subject: string; body: string }): Observable<any> {
    return this.http.post(this.apiUrl, form);
  }
}
