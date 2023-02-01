import { IonicModule } from '@ionic/angular';
import { IonModal } from '@ionic/angular';
import { ToastController } from '@ionic/angular';
import { AlertController } from '@ionic/angular';
import { Platform } from '@ionic/angular';
import { Component, OnInit, AfterViewInit, OnDestroy, ViewChild, ElementRef, ViewContainerRef } from '@angular/core';
import { Router, ActivatedRoute } from '@angular/router';
import { interval, BehaviorSubject } from 'rxjs';
import { filter, pairwise } from 'rxjs/operators';
import { timer, Subject } from 'rxjs';
import { map, takeUntil, takeWhile, finalize } from 'rxjs/operators';
import Phaser from 'phaser';

import { HttpService } from '../services/http.service';
import { environment } from '../../environments/environment';
import { GameInfo } from '../model/gameinfo';

import { GameScene } from './game-scene';

@Component({
  selector: 'app-game',
  templateUrl: './game.component.html',
  styleUrls: ['./game.component.scss'],
})
export class GameComponent {
  gamedivid: string = null;
  phaserGame: Phaser.Game;
  config: Phaser.Types.Core.GameConfig;
  gameinfo: GameInfo = null;
  cardsinfo: BehaviorSubject<Array<any>> = new BehaviorSubject<Array<any>>([]);
  CARDS_URL = environment.STATIC_URL;
  Ngameround = new BehaviorSubject<number>(0);

  countDownStop = new Subject<any>();
  countDownValue: number = -1;
  countDownTimer: any;

  highlightedCardSlot: number = -1;

  gameWidth: number;
  gameHeight: number;
  submittedCards: boolean = false;
  poweredDown: boolean = false;

  @ViewChild('cards_menu', { read: ElementRef }) cards_menu: ElementRef;
  @ViewChild('tools_menu', { read: ElementRef }) tools_menu: ElementRef;
  @ViewChild('cannonModal') cannonModal: IonModal;
  @ViewChild('rerigModal') rerigModal: IonModal;
  @ViewChild('leaveModal') leaveModal: IonModal;
  @ViewChild('statsModal') statsModal: IonModal;
  @ViewChild('appgamecontent') appGameContent: ViewContainerRef;

  constructor(
    private httpService: HttpService,
    private route: ActivatedRoute,
    private router: Router,
    private toastController: ToastController,
    private alertController: AlertController
  ) {
    this.gamedivid = 'piraterace-game-' + Math.random().toString(36).substring(2);
  }

  ionViewDidEnter() {
    this.load_gameinfo().subscribe(
      (gameinfo) => {
        console.log('Game:', gameinfo);
        this.gameinfo = gameinfo;
        this.Ngameround.next(gameinfo['Ngameround']);

        this.config = {
          parent: this.gamedivid,
          type: Phaser.AUTO,
          transparent: true,
          width: this.gameinfo.map.width * this.gameinfo.map.tilewidth,
          height: this.gameinfo.map.height * this.gameinfo.map.tileheight,
          scale: {
            mode: Phaser.Scale.RESIZE,
            autoCenter: Phaser.Scale.CENTER_BOTH,
            autoRound: true,
          },
          physics: { default: 'None' },
          fps: {
            target: 12,
            forceSetTimeOut: true,
          },
          disableContextMenu: true,
        };

        this.config.scene = new GameScene(this);
        this.phaserGame = new Phaser.Game(this.config);

        this.cards_menu.nativeElement.style.borderColor = gameinfo['players'][gameinfo['me']]['color'];
        this.tools_menu.nativeElement.style.borderColor = gameinfo['players'][gameinfo['me']]['color'];
      },
      (err) => console.error(err),
      () => console.log('observable complete')
    );
    this.getPlayerCards();
    this.Ngameround.asObservable()
      .pipe(
        pairwise(),
        filter((vals) => vals[0] !== vals[1])
      )
      .subscribe((val) => {
        this.countDownStop.next();
        this.submittedCards = false;
        if (this.gameinfo.players[this.gameinfo.me]['powered_down']) {
          this.submittedCards = true;
        }
        this.poweredDown = false;
        this.getPlayerCards();
      });
  }

  finalizeCountDown() {
    this.countDownValue = -1;
    this.countDownTimer = 0;
    console.log('Finalize Countdown');
  }

  setupCountDown(start: number, end: number) {
    this.countDownValue = start / end;
    const updatefreq = 500;
    this.countDownTimer = timer(0, updatefreq).pipe(
      takeUntil(this.countDownStop),
      takeWhile((_) => this.countDownValue < 1),
      finalize(() => this.finalizeCountDown()),
      map((_) => {
        console.log('time increment', this.countDownValue);
        this.countDownValue = this.countDownValue + (1 / (end - start)) * (updatefreq / 1000);
        return this.countDownValue; // [0,1] for progressbar
      })
    );
  }

  ionViewWillLeave() {
    console.log("Leaving Game");
    this.phaserGame.destroy(true, false);
    this.appGameContent.clear();
    // this.defaultScene.updateTimer.paused = true;
  }

  load_gameinfo() {
    let id = +this.route.snapshot.paramMap.get('id');
    return this.httpService.getGame(id);
  }

  loadPathHighlighting() {
    return this.httpService.predictPath();
  }

  getPlayerCards() {
    this.httpService.getPlayerCards().subscribe((result) => {
      this.cardsinfo.next(result);
    });
  }

  cardCheck(i: number) {
    if (this.gameinfo) {
      if (this.gameinfo.players[this.gameinfo.me]['powered_down']) {
        return true;
      }
      if (this.gameinfo['state'] === 'animate') {
        return true;
      }
      if (this.submittedCards) {
        return true;
      }
      return i >= this.gameinfo.players[this.gameinfo.me]['health'];
    } else {
      return false;
    }
  }

  highlightCard(i: number) {
    return i === this.highlightedCardSlot;
  }

  onCardsReorder(event) {
    event.detail.complete(true);
    this.httpService.switchPlayerCards(event.detail.from, event.detail.to).subscribe(
      (result) => {
        console.log('switch cards:', result);
        this.cardsinfo.next(result);
      },
      (error) => {
        console.log('failed reorder cards: ', error);
        this.presentToast(error.error.message, 'danger');
        this.cardsinfo.next(error.error.cards);
      }
    );
  }

  submitCards() {
    this.httpService.submitCards().subscribe(
      (ret) => {
        this.presentToast(ret, 'success');
        this.submittedCards = true;
      },
      (error) => {
        this.presentToast(error.error, 'danger');
      }
    );
  }

  powerDown() {
    this.httpService.powerDown().subscribe(
      (ret) => {
        this.poweredDown = true;
        this.presentToast(ret, 'success');
        this.rerigModal.dismiss();
      },
      (error) => {
        this.presentToast(error.error, 'danger');
        this.poweredDown = true;
        this.rerigModal.dismiss();
      }
    );
  }

  leaveGame() {
    this.leaveModal.dismiss();
    this.httpService.get_leaveGame().subscribe(
      (ret) => {
        console.log('Success leave game: ', ret);
        this.presentToast(ret, 'success');
        this.router.navigate(['/lobby']);
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

  presentSummary() {
    this.statsModal.present();
  }

  changeCannonDirection(event) {
    this.httpService.changeCannonDirection(event.detail.value).subscribe(
      (ret) => {
        this.cannonModal.dismiss();
        console.log('Changed Cannon Direction', this.cannonModal);
        this.presentToast('Redirected deadly cannons.', 'success');
      },
      (error) => {
        this.presentToast(error.error, 'danger');
        this.cannonModal.dismiss();
      }
    );
  }
}
