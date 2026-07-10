import { Component, ViewChild } from '@angular/core';
import { MenuController, Platform } from '@ionic/angular';
import { IonModal } from '@ionic/angular';
import { StorageService } from './services/storage.service';
import { AuthService } from './services/auth.service';
import { HttpService } from './services/http.service';
import { LobbyAudioService } from './services/lobby-audio.service';
import { BehaviorSubject } from 'rxjs';
import { ToastController } from '@ionic/angular';
import { NavigationEnd, Router } from '@angular/router';
import { filter } from 'rxjs/operators';
import { StatusBar } from '@capacitor/status-bar';

@Component({
  selector: 'app-root',
  templateUrl: 'app.component.html',
  styleUrls: ['app.component.scss'],
})
export class AppComponent {
  @ViewChild('leaveGameModal') leaveGameModal: IonModal;

  constructor(
    private menu: MenuController,
    public authService: AuthService,
    private httpService: HttpService,
    private router: Router,
    private toastController: ToastController,
    private platform: Platform,
    public lobbyAudio: LobbyAudioService
  ) {
    this.initializeApp();

    this.router.events.pipe(filter((event) => event instanceof NavigationEnd)).subscribe((event: NavigationEnd) => {
      if (event.urlAfterRedirects.startsWith('/lobby')) {
        this.lobbyAudio.start();
      } else {
        this.lobbyAudio.stop();
      }
    });
  }

  toggleLobbyMusic() {
    const val = !this.lobbyAudio.musicOn;
    this.lobbyAudio.setMusicOn(val);
    if (this.router.url.startsWith('/lobby')) {
      if (val) this.lobbyAudio.start();
      else this.lobbyAudio.stop();
    }
  }

  openLeaveGameModal() {
    this.leaveGameModal?.present();
  }

  leaveGame() {
    this.leaveGameModal?.dismiss();
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

  async hideStatusBar() {
    await StatusBar.hide();
  }

  initializeApp() {
    this.platform.ready().then(() => {
      if (this.platform.is('mobile')) {
        this.hideStatusBar();
      }
    });
  }
}
