import { Injectable } from '@angular/core';
import {
  HttpClient,
  HttpHeaders,
  HttpParams,
  HttpErrorResponse,
} from '@angular/common/http';
import { BehaviorSubject, Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { StorageService } from './storage.service';

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  registerUserURL = `${environment.API_URL}/auth/users/`;
  loginUserURL = `${environment.API_URL}/auth/jwt/create`;

  isAuthenticated: BehaviorSubject<boolean> = new BehaviorSubject<boolean>(
    null
  );
  token: BehaviorSubject<string> = new BehaviorSubject<string>('loadingtoken');
  refresh = '';

  constructor(
    private httpClient: HttpClient,
    private storageService: StorageService
  ) {
    this.load_token();
  }

  registerUser(username, password, email) {
    return this.httpClient.post(this.registerUserURL, {
      username: username,
      password: password,
      email: email,
    });
  }

  login(username, password) {
    return new Observable((observer) => {
      this.httpClient
        .post(this.loginUserURL, { username: username, password: password })
        .subscribe((ret) => {
          console.log('authService: ', ret);
          if (ret) {
            let accessToken = ret['access'];
            let refreshToken = ret['refresh'];
            this.storageService.set('access', accessToken);
            this.storageService.set('refresh', refreshToken);
            this.token.next(accessToken);
            this.refresh = refreshToken;
            this.isAuthenticated.next(true);

            observer.next(ret);
            observer.complete();
          } else {
            observer.next();
            observer.complete();
          }
        });
    });
  }

  async load_token() {
    this.storageService.get('access').then((val: string) => {
      console.log('auth service - access token: ', val);
      if (val) {
        this.token.next(val);
        this.storageService.get('refresh').then((val: string) => {
          this.refresh = val;
          this.isAuthenticated.next(true);
        });
      } else {
        console.log('no token in storage');
      }
    });
    //.then((value: string) => {
    //  if (value) {
    //    console.log('load token: ', value);
    //    this.token = value;
    //    this.storageService.get('refresh').then((value: string) => {
    //      this.refresh = value;
    //      this.isAuthenticated.next(true);
    //    });
    //  } else {
    //    console.log('no token in storage');
    //    this.isAuthenticated.next(false);
    //  }
    //});
  }
}
