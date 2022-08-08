import { Component, OnInit } from '@angular/core';
import { GameMaker } from '../model/gamemaker';
import { HttpService } from '../services/http.service';
import { environment } from '../../environments/environment';
import { Router, ActivatedRoute } from '@angular/router';

@Component({
  selector: 'app-gamelist',
  templateUrl: './gamelist.component.html',
  providers: [HttpService],
  styleUrls: ['./gamelist.component.scss'],
})
export class GamelistComponent implements OnInit {
  gameMakers: GameMaker[] = [];
  create_gamemaker_url = `${environment.API_URL}/pigame/create_gamemaker`;
  constructor(
    private httpService: HttpService,
    private router: Router,
    private route: ActivatedRoute
  ) {}

  ngOnInit() {
    this.httpService.getGamesList().subscribe((gameMakers) => {
      console.log(gameMakers);
      this.gameMakers = gameMakers;
    });
  }

  createGameMaker(): void {
    console.log('Ping');
    this.httpService.createGameMaker().subscribe((gameMaker) => {
      console.log(gameMaker);
      this.router.navigate(['view_gamemaker', gameMaker.id], {
        relativeTo: this.route,
      });
    });
  }

  joinGameMaker(id: number): void {
    console.log('Join');
    this.httpService.joinGameMaker(id).subscribe((gameMaker) => {
      console.log(gameMaker);
      this.router.navigate(['view_gamemaker', gameMaker.id], {
        relativeTo: this.route,
      });
    });
  }
}
