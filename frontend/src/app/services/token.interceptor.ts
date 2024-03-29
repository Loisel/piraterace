import { Injectable } from '@angular/core';
import { HttpInterceptor, HttpRequest, HttpResponse, HttpHandler, HttpEvent, HttpErrorResponse } from '@angular/common/http';
import { Router } from '@angular/router';

import { BehaviorSubject, Observable, throwError, from } from 'rxjs';
import { filter, take, catchError, switchMap } from 'rxjs/operators';
import { AlertController } from '@ionic/angular';

import { AuthService } from './auth.service';

@Injectable()
export class TokenInterceptor implements HttpInterceptor {
  private refreshingInProgress: boolean;
  private accessTokenSubject: BehaviorSubject<string> = new BehaviorSubject<string>(null);

  constructor(private alertController: AlertController, private authService: AuthService, private router: Router) {}

  intercept(request: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
    return from(this.authService.getToken()).pipe(
      filter((token) => token !== 'uninitialized'),
      take(1), // filter 'uninitialized' value to actually wait until auth module may have loaded a token from storage
      switchMap((token) => {
        //console.log('TokenInterceptor token : ', token);
        if (token) {
          request = request.clone({
            setHeaders: { Authorization: 'JWT ' + token },
          });
        }

        return next.handle(request).pipe(
          catchError((error: HttpErrorResponse) => {
            const status = error.status;
            const reason = error && error.error.reason ? error.error.reason : '';
            console.log('Interceptor Error', error, status, reason);

            if (error instanceof HttpErrorResponse && error.status === 401) {
              if (request.url.indexOf('/refresh') > 0) {
                console.log('==== 401 error for a refresh url -> LOGOUT ERROR');
                return this.logoutAndRedirect(error, '/');
              }

              if (!this.authService.getRefresh().getValue()) {
                return this.logoutAndRedirect(error, '/');
              } else {
                return this.refreshToken(request, next);
              }
            }

            return throwError(error);
          })
        );
      })
    );
  }

  private refreshToken(request: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
    console.log('Interceptor Asking for a token refresh', this.refreshingInProgress);
    if (!this.refreshingInProgress) {
      this.refreshingInProgress = true;
      this.accessTokenSubject.next(null);

      return this.authService.refreshToken().pipe(
        switchMap((res) => {
          this.refreshingInProgress = false;
          console.log('Interceptor re-setting refreshingInProgress', this.refreshingInProgress);
          let token = this.authService.getToken().getValue();
          console.log('==== REFRESHED TOKEN', res, ' => ', token);

          this.accessTokenSubject.next(token);

          // repeat failed request with new token
          request = request.clone({
            headers: request.headers.set('Authorization', 'JWT ' + token),
          });

          return next.handle(request);
        }),
        catchError((err, caught) => {
          console.log('=========== ERROR REFRESHING TOKEN', err, caught);
          return throwError(err);
        })
      );
    } else {
      // wait while getting new token
      console.log('Interceptor wait while getting new token', this.refreshingInProgress);
      return this.accessTokenSubject.pipe(
        filter((token) => token !== 'uninitialized'),
        take(1),
        switchMap((token) => {
          // repeat failed request with new token
          console.log('Interceptor wait while getting new token', this.refreshingInProgress, token);
          request = request.clone({
            headers: request.headers.set('Authorization', 'JWT ' + token),
          });

          return next.handle(request);
        })
      );
    }
  }

  private logoutAndRedirect(err, nextURL): Observable<HttpEvent<any>> {
    this.authService.logout();
    this.router.navigate(['/auth/login'], {
      queryParams: { nextURL: nextURL },
    });
    return throwError(err);
  }
}
