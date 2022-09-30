import { Injectable } from '@angular/core';
import {
  HttpClient,
  HttpHeaders,
  HttpParams,
  HttpErrorResponse,
} from '@angular/common/http';
import { BehaviorSubject, Observable } from 'rxjs';
import { tap, filter, take, shareReplay } from 'rxjs/operators';

import { environment } from '../../environments/environment';
import { StorageService } from './storage.service';

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  registerUserURL = `${environment.API_URL}/auth/users/`;
  loginUserURL = `${environment.API_URL}/auth/jwt/create`;
  refreshUserURL = `${environment.API_URL}/auth/jwt/refresh`;
  userDetailURL = `${environment.API_URL}/auth/users/me`;

  public isAuthenticated: BehaviorSubject<boolean> =
    new BehaviorSubject<boolean>(null);
  private token: BehaviorSubject<string> = new BehaviorSubject<string>(
    'uninitialized'
  );
  private refresh: BehaviorSubject<string> = new BehaviorSubject<string>(
    'uninitialized'
  );

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
    return this.httpClient
      .post(this.loginUserURL, { username: username, password: password })
      .pipe(
        tap((ret) => {
          console.log('authService Login:', ret);
          if (ret) {
            let accessToken = ret['access'];
            let refreshToken = ret['refresh'];
            this.storageService.set('access', accessToken);
            this.storageService.set('refresh', refreshToken);
            this.token.next(accessToken);
            this.refresh.next(refreshToken);
            this.isAuthenticated.next(true);
          }
        })
      );
  }

  load_token() {
    return this.storageService.init().then(() => {
      // make sure that storage is already there
      this.storageService.get('access').then((val: string) => {
        //console.log('auth service - access token: ', val);
        if (val) {
          this.token.next(val);
          this.storageService.get('refresh').then((val: string) => {
            this.refresh.next(val);
            this.isAuthenticated.next(true);
          });
        } else {
          this.token.next(null);
          this.refresh.next(null);
          this.isAuthenticated.next(false);
          console.log('no token in storage');
        }
      });
    });
  }

  logout(): Promise<void> {
    this.isAuthenticated.next(false);
    this.token.next(null);
    this.refresh.next(null);
    return new Promise(async (resolve) => {
      this.storageService.set('access', null);
      this.storageService.set('refresh', null);
    });
  }

  refreshToken() {
    console.log('Asking for a token refresh with : ', this.refresh.getValue());
    return this.httpClient
      .post(this.refreshUserURL, { refresh: this.refresh.getValue() })
      .pipe(
        tap((ret) => {
          console.log('authService: refresh', ret);
          let accessToken = ret['access'];
          let refreshToken = ret['refresh'];
          this.storageService.set('access', accessToken);
          this.storageService.set('refresh', refreshToken);
          this.token.next(accessToken);
          this.refresh.next(refreshToken);
        })
      );
  }

  getUserDetail() {
    return this.httpClient.get(this.userDetailURL).pipe(shareReplay());
  }

  getToken() {
    return this.token;
  }

  getRefresh() {
    return this.refresh;
  }
}
