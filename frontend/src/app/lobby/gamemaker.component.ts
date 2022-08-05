import { Component, OnInit } from '@angular/core';
import { GameMaker } from '../gamemaker';
import { HttpService } from '../http.service';
import { environment } from '../../environments/environment';
import { Router, ActivatedRoute } from '@angular/router';


@Component({
  selector: 'app-gamemaker',
  templateUrl: './gamemaker.component.html',
  providers: [HttpService],
  styleUrls: ['./gamemaker.component.scss'],
})
export class GameMakerComponent implements OnInit {
  gameMaker: GameMaker;
  constructor(
    private httpService: HttpService,
    private route: ActivatedRoute,
    private router: Router
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

  createGame(){
    this.httpService.createGame(this.gameMaker.id).subscribe(payload => {
      console.log(payload);
      this.router.navigate(['game', payload['game_id']]);
    });
    
  }

}
