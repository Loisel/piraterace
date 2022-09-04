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
  playerColor: string;
  playerTeam: number;
  playerReady: boolean;
  constructor(
    private httpService: HttpService,
    private route: ActivatedRoute,
    private router: Router
  ) {}

  ngOnInit() {
    let id = +this.route.snapshot.paramMap.get('id');
    console.log(id);
    this.httpService.getGameMaker(id).subscribe((gamemaker) => {
      console.log(gamemaker);
      this.gameMaker = gamemaker;
    });
  }

  createGame() {
    this.httpService.createGame(this.gameMaker.id).subscribe((payload) => {
      console.log(payload);
      this.router.navigate(['game', payload['game_id']]);
    });
  }

  onPlayerInfoChange(event) {
    console.log("Color", this.playerColor);
    // this.httpService.updatePlayerInfo(this.gameMaker.id, {
    //   color: this.playerColor,
    //   team: this.playerTeam,
    //   ready: this.playerReady
    // }).subscribe((gamemaker) => {
    //   this.gameMaker = gamemaker;
    // });
  }
}
