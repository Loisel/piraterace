import { IonicModule } from '@ionic/angular';
import { IonModal } from '@ionic/angular';
import { ToastController } from '@ionic/angular';
import { AlertController } from '@ionic/angular';
import { Platform } from '@ionic/angular';
import { Component, OnInit, AfterViewInit, OnDestroy, ViewChild, ElementRef, ViewContainerRef } from '@angular/core';
import { Router, ActivatedRoute } from '@angular/router';
import { interval, BehaviorSubject } from 'rxjs';
import { filter, pairwise } from 'rxjs/operators';
import { timer, Subject, of, Subscription } from 'rxjs';
import { map, takeUntil, takeWhile, finalize } from 'rxjs/operators';
import { HttpService } from '../services/http.service';
import { environment } from '../../environments/environment';
import { GameInfo } from '../model/gameinfo';

import { GameRenderer } from './game-renderer';
import { GameAudio } from './game-audio';
import { LobbyAudioService } from '../services/lobby-audio.service';

@Component({
  selector: 'app-game',
  templateUrl: './game.component.html',
  styleUrls: ['./game.component.scss'],
})
export class GameComponent {
  canvasId: string = null;
  renderer: GameRenderer;
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
  currentPlayerUpgrades: { type: string; charges?: number }[] = [];
  currentPlayerHealth: number = 0;
  audio = new GameAudio();
  private musicPrefSub: Subscription;

  @ViewChild('cards_menu', { read: ElementRef }) cards_menu: ElementRef;
  @ViewChild('tools_menu', { read: ElementRef }) tools_menu: ElementRef;
  @ViewChild('cannonModal') cannonModal: IonModal;
  @ViewChild('rerigModal') rerigModal: IonModal;
  @ViewChild('statsModal') statsModal: IonModal;
  @ViewChild('soundModal') soundModal: IonModal;
  @ViewChild('appgamecontent') appGameContent: ViewContainerRef;

  constructor(
    private httpService: HttpService,
    private route: ActivatedRoute,
    private router: Router,
    private toastController: ToastController,
    private alertController: AlertController,
    private lobbyAudio: LobbyAudioService
  ) {
    this.canvasId = 'piraterace-game-' + Math.random().toString(36).substring(2);
    // keep the in-game music toggle in sync with the shared header preference
    this.musicPrefSub = this.lobbyAudio.musicOn$.subscribe((val) => this.audio.setMusicOn(val));
  }

  ionViewDidEnter() {
    this.load_gameinfo().subscribe(
      (gameinfo) => {
        console.log('Game:', gameinfo);
        this.gameinfo = gameinfo;
        this.Ngameround.next(gameinfo['Ngameround']);

        this.cards_menu.nativeElement.style.borderColor = gameinfo['players'][gameinfo['me']]['color'];
        this.tools_menu.nativeElement.style.borderColor = gameinfo['players'][gameinfo['me']]['color'];

        const canvas = document.getElementById(this.canvasId) as HTMLCanvasElement;
        this.renderer = new GameRenderer(canvas, this);
        this.renderer.preload().then(() => this.renderer.create()).catch((err) => console.error('GameRenderer preload failed:', err));
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
        this.audio.playRoundStart();
      });
  }

  finalizeCountDown() {
    this.countDownValue = -1;
    this.countDownTimer = of(1); // hold bar at full until next round's setupCountDown overwrites it
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
    console.log('Leaving Game');
    this.musicPrefSub?.unsubscribe();
    this.audio.destroy();
    this.renderer?.destroy();
    this.renderer = null;
    try {
      this.appGameContent.clear();
    } catch {
      console.log('Could not clear game content on leave');
    }
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
      return i >= this.gameinfo.players[this.gameinfo.me]['effective_health'];
    } else {
      return false;
    }
  }

  highlightCard(i: number) {
    return i === this.highlightedCardSlot;
  }

  onCardsReorder(event) {
    event.detail.complete(true);
    this.audio.playCardReorder();
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

  setSfxOn(event: any) { this.audio.setSfxOn(event.detail.checked); }

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

  private static readonly UPGRADE_META: Record<string, { emoji: string; label: string; description: string }> = {
    burning_cannons: {
      emoji: '🔥',
      label: 'Burning Cannons',
      description: 'Your cannon shots set opponents on fire. They take 1 extra damage at the end of each round.',
    },
    shield: {
      emoji: '🛡',
      label: 'Shield',
      description: 'Absorbs up to 3 damage from cannon hits. Disappears when all charges are used.',
    },
    checkpoint_rush: {
      emoji: '⚑',
      label: 'Checkpoint Rush',
      description: 'Instantly skips your next required checkpoint — or wins the race if it was the last one.',
    },
    ghost_ship: {
      emoji: '👻',
      label: 'Ghost Ship',
      description: 'Your ship passes through void tiles unharmed. Vortexes still spin you around.',
    },
    solid_rock: {
      emoji: '🪨',
      label: 'Solid as a Rock',
      description: 'Your ship cannot be pushed by other ships. They will be blocked if they try.',
    },
    odysseus_curse: {
      emoji: '🌊',
      label: "Odysseus' Curse",
      description: "You sail too far ahead of the fleet. The gods punish your hubris — all reserve cards are frozen and cannot be reordered.",
    },
    rose_cannons: {
      emoji: '🧭',
      label: 'Rose Cannons',
      description: 'Your cannons fire in all four cardinal directions simultaneously.',
    },
    quartermaster: {
      emoji: '🗺️',
      label: 'Quartermaster',
      description: 'A skilled quartermaster expands your options — you draw one extra card each round to choose from.',
    },
    carpenter: {
      emoji: '🔧',
      label: 'Carpenter',
      description: "The ship's carpenter patches the hull each round, restoring +1 health.",
    },
    shipwright: {
      emoji: '⚓',
      label: 'Shipwright',
      description: 'A master shipwright keeps the vessel battle-ready, restoring +2 health each round.',
    },
  };

  upgradeEmoji(type: string): string {
    return GameComponent.UPGRADE_META[type]?.emoji ?? '?';
  }

  upgradeLabel(type: string): string {
    return GameComponent.UPGRADE_META[type]?.label ?? type;
  }

  async showTreasureInfo(upgradeType: string | null) {
    let header: string;
    let message: string;
    if (upgradeType) {
      const meta = GameComponent.UPGRADE_META[upgradeType];
      header = `Treasure Chest — ${meta?.emoji ?? '?'} ${meta?.label ?? upgradeType}`;
      message = (meta?.description ?? upgradeType) + '<br><br><i>Stand on this tile at the end of a round to collect it.</i>';
    } else {
      const all = Object.entries(GameComponent.UPGRADE_META)
        .filter(([k]) => k !== 'odysseus_curse')
        .map(([, m]) => `${m.emoji} ${m.label}`)
        .join(', ');
      header = 'Treasure Chest';
      message = `Contains one of: ${all}.<br><br><i>Stand on this tile at the end of a round to collect it.</i>`;
    }
    const alert = await this.alertController.create({ header, message, buttons: ['OK'] });
    await alert.present();
  }

  async showUpgradeInfo(upg: { type: string; charges?: number }) {
    const meta = GameComponent.UPGRADE_META[upg.type];
    if (!meta) return;
    const chargesLine = upg.type === 'shield' ? `<br><b>Charges remaining:</b> ${upg.charges}` : '';
    const alert = await this.alertController.create({
      header: `${meta.emoji} ${meta.label}`,
      message: meta.description + chargesLine,
      buttons: ['OK'],
    });
    await alert.present();
  }
}
