import { Component, OnInit } from '@angular/core';
import { ToastController } from '@ionic/angular';
import { Router, ActivatedRoute } from '@angular/router';
import { BehaviorSubject } from 'rxjs';

import { GameMaker } from '../../model/gamemaker';
import { HttpService } from '../../services/http.service';
import { environment } from '../../../environments/environment';

@Component({
  selector: 'app-gamelist',
  templateUrl: './gamelist.component.html',
  styleUrls: ['./gamelist.component.scss'],
})
export class GamelistComponent implements OnInit {
  gameMakers: GameMaker[] = [];
  reconnectGameId = new BehaviorSubject<number>(null);
  updateTimer: ReturnType<typeof setInterval>;

  constructor(
    private httpService: HttpService,
    private route: ActivatedRoute,
    private router: Router,
    private toastController: ToastController
  ) {}

  ngOnInit() {
    this.updateGameMakers();
    this.updateTimer = setInterval(() => {
      this.updateGameMakers();
    }, 2000);
  }

  ionViewWillLeave() {
    clearInterval(this.updateTimer);
  }

  updateGameMakers() {
    this.httpService.getGamesList().subscribe((ret) => {
      console.log(ret);
      this.gameMakers = ret['gameMakers'];
      this.reconnectGameId.next(ret['reconnect_game']);
    });
  }

  joinGameMaker(id: number): void {
    console.log('Join');
    this.httpService.joinGameMaker(id).subscribe(
      (ret) => {
        console.log(ret);
        this.router.navigate(['view_gamemaker', ret.id], {
          relativeTo: this.route,
        });
      },
      (error) => {
        console.log('Failed request', error);
        this.presentToast(error.error, 'danger');
      }
    );
  }

  newGameMaker(id: number): void {
    console.log('NewGameMaker');
    this.httpService.get_create_new_gameMaker().subscribe(
      (ret) => {
        console.log(ret);
        this.router.navigate(['newgamemaker'], {
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
    console.log('Reconnect to game: ', [
      'game',
      this.reconnectGameId.getValue(),
    ]);
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
