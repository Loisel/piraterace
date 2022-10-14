import { Component } from '@angular/core';
import { MenuController } from '@ionic/angular';
import { StorageService } from './services/storage.service';
import { AuthService } from './services/auth.service';
import { NavService } from './services/nav.service';
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
  showLeaveGame: BehaviorSubject<boolean>;
  constructor(
    private menu: MenuController,
    public authService: AuthService,
    private navService: NavService,
    private httpService: HttpService,
    private router: Router,
    private toastController: ToastController
  ) {}

  ngOnInit() {
    this.showLeaveGame = this.navService.getShowLeaveGame();
  }

  leaveGame() {
    this.httpService.get_leaveGame().subscribe(
      (success) => {
        console.log('Success leave game: ', success);
        this.presentToast(success, 'success');
        this.router.navigate(['/']);
      },
      (error) => {
        console.log('failed leave game: ', error);
        this.presentToast(error.error, 'danger');
      }
    );
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
