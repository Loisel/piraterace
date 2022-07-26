import { Component, OnInit } from '@angular/core';
import { GameMaker } from '../gamemaker';
import { HttpService } from '../http.service'
import { environment } from '../../environments/environment';
import { ActivatedRoute } from '@angular/router'


@Component({
  selector: 'app-gamemaker',
  templateUrl: './gamemaker.component.html',
  providers: [HttpService],
  styleUrls: ['./gamemaker.component.scss'],
})
export class GameMakerComponent implements OnInit {
  gameMaker: GameMaker;
  start_game_url = `${environment.API_URL}/pigame/create_game`;
  constructor(
    private httpService: HttpService,
    private route: ActivatedRoute
  ) {
  }

  ngOnInit() {
    let id = +this.route.snapshot.paramMap.get("id");
    console.log(id);
    this.httpService.getGameMaker(id).subscribe(gamemaker => {
      console.log(gamemaker);
      this.gameMaker = gamemaker;
    });
  }

}
