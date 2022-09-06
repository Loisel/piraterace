import { Component, OnInit } from '@angular/core';
import { ToastController } from '@ionic/angular';
import { Router, ActivatedRoute } from '@angular/router';

import { GameMaker } from '../../model/gamemaker';
import { HttpService } from '../../services/http.service';
import { environment } from '../../../environments/environment';

@Component({
  selector: 'app-gamemaker',
  templateUrl: './gamemaker.component.html',
  styleUrls: ['./gamemaker.component.scss'],
})
export class GameMakerComponent implements OnInit {
  gameMaker: GameMaker;
  updateTimer: ReturnType<typeof setInterval>;
  constructor(
    private httpService: HttpService,
    private route: ActivatedRoute,
    private router: Router,
    private toastController: ToastController
  ) {}

  ngOnInit() {
    let id = +this.route.snapshot.paramMap.get('id');
    console.log(id);
    this.updateGameMaker(id);
    this.updateTimer = setInterval(() => {
      this.updateGameMaker(id);
    }, 2000);
  }

  updateGameMaker(id: number) {
    this.httpService.getGameMaker(id).subscribe((gamemaker) => {
      this.gameMaker = gamemaker;
      if (this.gameMaker['game']) {
        this.router.navigate(['game', this.gameMaker['game']]);
      }
    });
  }

  createGame() {
    this.httpService.createGame(this.gameMaker.id).subscribe(
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

  ionViewWillLeave() {
    clearInterval(this.updateTimer);
  }

  onPlayerInfoChange(event) {
    // console.log("Color", this.playerColor);
    this.httpService
      .updateGMPlayerInfo(this.gameMaker.id, {
        color: this.gameMaker['player_colors'][this.gameMaker['caller_idx']],
        team: this.gameMaker['player_teams'][this.gameMaker['caller_idx']],
        ready: this.gameMaker['player_ready'][this.gameMaker['caller_idx']],
      })
      .subscribe((data: any) => {
        this.gameMaker = data;
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
