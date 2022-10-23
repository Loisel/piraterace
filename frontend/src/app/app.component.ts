import { Component } from '@angular/core';
import { MenuController } from '@ionic/angular';
import { StorageService } from './services/storage.service';
import { AuthService } from './services/auth.service';
import { HttpService } from './services/http.service';
import { BehaviorSubject } from 'rxjs';
import { ToastController } from '@ionic/angular';
import { Router } from '@angular/router';

@Component({
  selector: 'app-root',
  templateUrl: 'app.component.html',
  styleUrls: ['app.component.scss'],
})
export class AppComponent {
  constructor(
    private menu: MenuController,
    public authService: AuthService,
    private httpService: HttpService,
    private router: Router,
    private toastController: ToastController
  ) {}

  leaveGame() {
    this.httpService.get_leaveGame().subscribe(
      (success) => {
        console.log('Success leave game: ', success);
        this.presentToast(success, 'success');
        this.router.navigate(['/lobby']);
      },
      (error) => {
        console.log('failed leave game: ', error);
        this.presentToast(error.error, 'danger');
      }
    );
  }

  reconnectCurrentGame() {
    let id = this.authService.userDetail.value.game;
    if (id) {
      this.presentToast('Reconnecting to game ' + id, 'success');
      this.router.navigate(['game', id]);
    } else {
      this.presentToast('Cannot reconnect to game ' + id, 'danger');
    }
  }

  async presentToast(msg, color = 'primary') {
    const toast = await this.toastController.create({
      message: msg,
      color: color,
      duration: 5000,
    });
    toast.present();
  }
}
