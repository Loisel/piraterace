import { Component, OnInit } from '@angular/core';
import { ToastController } from '@ionic/angular';
import { Router, ActivatedRoute } from '@angular/router';
import { BehaviorSubject } from 'rxjs';

import { GameConfig } from '../../model/gameconfig';
import { HttpService } from '../../services/http.service';
import { environment } from '../../../environments/environment';

@Component({
  selector: 'app-gamelist',
  templateUrl: './gamelist.component.html',
  styleUrls: ['./gamelist.component.scss'],
})
export class GamelistComponent implements OnInit {
  gameConfigs: GameConfig[] = [];
  reconnectGameId = new BehaviorSubject<number>(null);
  updateTimer: ReturnType<typeof setInterval>;

  constructor(
    private httpService: HttpService,
    private route: ActivatedRoute,
    private router: Router,
    private toastController: ToastController
  ) {}

  ngOnInit() {}

  ionViewWillEnter() {
    this.updateGameConfigs();
    this.updateTimer = setInterval(() => {
      this.updateGameConfigs();
    }, 2000);
  }

  ionViewWillLeave() {
    clearInterval(this.updateTimer);
  }

  updateGameConfigs() {
    this.httpService.getGamesList().subscribe((ret) => {
      console.log(ret);
      this.gameConfigs = ret['gameconfigs'];
      this.reconnectGameId.next(ret['reconnect_game']);
    });
  }

  joinGameConfig(id: number): void {
    console.log('Join');
    this.httpService.joinGameConfig(id).subscribe(
      (ret) => {
        console.log(ret);
        this.router.navigate(['view_gameconfig', ret.id], {
          relativeTo: this.route,
        });
      },
      (error) => {
        console.log('Failed request', error);
        this.presentToast(error.error, 'danger');
      }
    );
  }

  newGameConfig(): void {
    console.log('NewGameConfig');
    this.httpService.get_create_new_gameConfig().subscribe(
      (ret) => {
        console.log(ret);
        this.router.navigate(['newgameconfig'], {
          relativeTo: this.route,
        });
      },
      (error) => {
        console.log('Failed request', error);
        this.presentToast(error.error, 'danger');
      }
    );
  }

  reconnectGame() {
    console.log('Reconnect to game: ', ['game', this.reconnectGameId.getValue()]);
    //this.router.navigate(['game', this.reconnectGameId.getValue()]);
    let id = this.reconnectGameId.getValue();
    this.router.navigate(['game', id]);
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
