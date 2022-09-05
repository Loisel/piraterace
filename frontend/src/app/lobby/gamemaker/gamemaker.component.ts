import { Component, OnInit } from '@angular/core';
import { GameMaker } from '../../model/gamemaker';
import { HttpService } from '../../services/http.service';
import { environment } from '../../../environments/environment';
import { Router, ActivatedRoute } from '@angular/router';

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
    private router: Router
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
    this.httpService.createGame(this.gameMaker.id).subscribe((payload) => {
      console.log(payload);
      // this.router.navigate(['game', payload['game_id']]);
    });
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
}
