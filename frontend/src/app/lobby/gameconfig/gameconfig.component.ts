import { Component, OnInit } from '@angular/core';
import { ToastController } from '@ionic/angular';
import { Router, ActivatedRoute } from '@angular/router';

import { GameConfig } from '../../model/gameconfig';
import { HttpService } from '../../services/http.service';

@Component({
  selector: 'app-gameconfig',
  templateUrl: './gameconfig.component.html',
  styleUrls: ['./gameconfig.component.scss'],
})
export class GameConfigComponent implements OnInit {
  gameConfig: GameConfig = null;
  updateTimer: ReturnType<typeof setInterval>;

  constructor(
    private httpService: HttpService,
    private route: ActivatedRoute,
    private router: Router,
    private toastController: ToastController
  ) {}

  ngOnInit() {}

  registerupdateGameConfigInterval() {
    let id = +this.route.snapshot.paramMap.get('id');
    this.updateTimer = setInterval(() => {
      this.updateGameConfig(id);
    }, 2000);
  }

  updateGameConfig(id: number) {
    this.httpService.getGameConfig(id).subscribe(
      (gameconfig) => {
        this.gameConfig = gameconfig;
        console.log('GameConfig data', this.gameConfig);
        if (this.gameConfig['game']) {
          this.router.navigate(['game', this.gameConfig['game']]);
        }
      },
      (error) => {
        console.log('Failed updateGameConfig:', error);
        this.presentToast(error.error, 'danger');
        this.router.navigate(['/lobby']);
      }
    );
  }

  createGame() {
    this.httpService.createGame(this.gameConfig.id).subscribe(
      (payload) => {
        console.log(payload);
        // this.router.navigate(['game', payload['game_id']]);
      },
      (error) => {
        console.log('Failed this.httpService.createGame:', error);
        this.presentToast(error.error, 'danger');
      }
    );
  }

  ionViewWillEnter() {
    let id = +this.route.snapshot.paramMap.get('id');
    this.updateGameConfig(id);
    this.registerupdateGameConfigInterval();
  }

  ionViewWillLeave() {
    clearInterval(this.updateTimer);
    this.leaveGameConfig();
  }

  leaveGameConfig() {
    this.httpService.leaveGameConfig().subscribe(
      (payload) => {
        console.log(payload);
      },
      (error) => {
        console.log('Failed to leave this GameConfig:', error);
        this.presentToast(error.error, 'danger');
      }
    );
  }

  onPlayerInfoChange(event) {
    // console.log("Color", this.playerColor);
    this.httpService
      .updateGMPlayerInfo(this.gameConfig.id, {
        color: this.gameConfig['player_colors'][this.gameConfig['caller_idx']],
        team: this.gameConfig['player_teams'][this.gameConfig['caller_idx']],
        ready: this.gameConfig['player_ready'][this.gameConfig['caller_idx']],
      })
      .subscribe((data: any) => {
        this.gameConfig = data;
      });
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
