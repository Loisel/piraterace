import { IonicModule } from '@ionic/angular';
import { ToastController } from '@ionic/angular';
import {
  Component,
  OnInit,
  AfterViewInit,
  OnDestroy,
  ViewChild,
  ElementRef,
} from '@angular/core';
import { Router, ActivatedRoute } from '@angular/router';
import { interval, BehaviorSubject } from 'rxjs';
import { filter, pairwise } from 'rxjs/operators';
import { timer, Subject } from 'rxjs';
import { map, takeUntil, takeWhile, finalize } from 'rxjs/operators';
import Phaser from 'phaser';

import { HttpService } from '../services/http.service';
import { environment } from '../../environments/environment';

@Component({
  selector: 'app-game',
  templateUrl: './game.component.html',
  styleUrls: ['./game.component.scss'],
})
export class GameComponent {
  phaserGame: Phaser.Game;
  config: Phaser.Types.Core.GameConfig;
  gameinfo: any = null;
  cardsinfo: any = [];
  CARDS_URL = environment.STATIC_URL;
  Ngameround = new BehaviorSubject<number>(0);

  countDownStop = new Subject<any>();
  countDownValue: number = -1;
  countDownTimer: any;

  @ViewChild('game_div', { read: ElementRef }) game_div: ElementRef;

  constructor(
    private httpService: HttpService,
    private route: ActivatedRoute,
    private router: Router,
    private toastController: ToastController
  ) {}

  ionViewWillEnter() {
    this.load_gameinfo().subscribe(
      (gameinfo) => {
        console.log('Game:', gameinfo);
        console.log(
          'Game_div size:',
          this.game_div.nativeElement.offsetWidth,
          this.game_div.nativeElement.offsetHeight
        );
        this.gameinfo = gameinfo;
        this.Ngameround.next(gameinfo['Ngameround']);
        this.config = {
          parent: 'piraterace-game',
          type: Phaser.AUTO,
          width: this.gameinfo.map.width * this.gameinfo.map.tilewidth,
          height: this.gameinfo.map.height * this.gameinfo.map.tileheight,
          scale: {
            min: {
              height: this.game_div.nativeElement.offsetHeight,
            },
            max: {
              height: this.game_div.nativeElement.offsetHeight,
            },
            mode: Phaser.Scale.FIT,
            autoCenter: Phaser.Scale.CENTER_BOTH,
          },
          physics: { default: 'None' },
          fps: {
            target: 24,
            forceSetTimeOut: true,
          },
        };

        this.config.scene = new GameScene(this);
        this.phaserGame = new Phaser.Game(this.config);
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
        this.countDownValue =
          this.countDownValue + (1 / (end - start)) * (updatefreq / 1000);
        return this.countDownValue; // [0,1] for progressbar
      })
    );
  }

  ionViewWillLeave() {
    this.phaserGame.destroy(true, false);
    // this.defaultScene.updateTimer.paused = true;
  }

  load_gameinfo() {
    let id = +this.route.snapshot.paramMap.get('id');
    return this.httpService.getGame(id);
  }

  getPlayerCards() {
    this.httpService.getPlayerCards().subscribe((result) => {
      this.cardsinfo = result;
    });
  }

  onCardsReorder({ detail }) {
    console.log(detail);
    this.httpService.switchPlayerCards(detail.from, detail.to).subscribe(
      (result) => {
        console.log('switch cards:', result);
        this.cardsinfo = result;
        detail.complete(true);
      },
      (error) => {
        console.log('failed reorder cards: ', error);
        this.presentToast(error.error, 'danger');
        detail.complete(false);
      }
    );
  }

  submitCards() {
    this.httpService.submitCards().subscribe(
      (ret) => {
        console.log('submitCards: ', ret);
        this.presentToast(ret, 'success');
        // set cards inactive
      },
      (error) => {
        console.log('failed leave game: ', error);
        this.presentToast(error.error, 'danger');
      }
    );
  }

  leaveGame() {
    this.httpService.get_leaveGame().subscribe(
      (ret) => {
        console.log('Success leave game: ', ret);
        this.presentToast(ret, 'success');
        this.router.navigate(['/']);
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
}

class GameScene extends Phaser.Scene {
  updateTimer: Phaser.Time.TimerEvent;
  animationTimer: Phaser.Time.TimerEvent;
  boats: any = {};
  last_played_action: number = 0;
  component: any = null;
  // animation config
  move_frames: number = 3; // number of sub steps of animations
  anim_frac: number = 0.5; // fraction of animation time we spend with doing things
  anim_cutoff: number = 10; // below this duration we just skip animations
  checkpointLabels: Phaser.GameObjects.Text[] = [];
  constructor(component) {
    super('MainGameScene');
    this.component = component;
  }

  preload() {
    this.load.image(
      'tileset',
      `${environment.STATIC_URL}/maps/${this.component.gameinfo.map.tilesets[0].image}`
    );
    this.load.tilemapTiledJSON(
      'tilemap',
      `${environment.STATIC_URL}/maps/${this.component.gameinfo.mapfile}`
    );
    this.load.spritesheet(
      'boat',
      `${environment.STATIC_URL}/sprites/boat.png`,
      { frameWidth: 24, frameHeight: 72 }
    );
  }

  damage_stars(target_x: number, target_y: number, time: number) {
    time *= this.anim_frac;
    let frame_delay = time / this.move_frames;
    if (frame_delay >= this.anim_cutoff) {
      let stars = this.add.group();
      stars.add(this.add.star(target_x - 2, target_y + 6, 5, 6, 11, 0xff0000));
      stars.add(this.add.star(target_x - 5, target_y - 11, 5, 8, 13, 0xff0000));
      let iternum = 0;
      this.animationTimer = this.time.addEvent({
        callback: () => {
          stars.incY(-4);
          iternum += 1;
          if (iternum == this.move_frames) {
            stars.destroy(true);
          }
        },
        callbackScope: this,
        delay: frame_delay, // 1000 = 1 second
        repeat: this.move_frames - 1,
      });
    }
  }

  shoot_cannon(
    boat_id: number,
    target_x: number,
    target_y: number,
    tilewidth: number,
    tileheight: number,
    show_stars: boolean,
    time: number
  ) {
    let boat = this.boats[boat_id];
    let dX = target_x - boat.boat.x;
    let dY = target_y - boat.boat.y;
    // distance in number of tiles
    let dist = Math.round(
      Math.max(Math.abs(dX) / tilewidth, Math.abs(dY) / tileheight)
    );
    time *= this.anim_frac;
    // one frame per tile
    let move_frames = dist;
    let frame_delay = time / move_frames;
    if (frame_delay >= this.anim_cutoff) {
      console.log('Shooting:', boat_id, 'at x/y', target_x, target_y);

      let cannonball = this.add.circle(boat.boat.x, boat.boat.y, 10, 0);
      let iternum = 0;
      this.animationTimer = this.time.addEvent({
        callback: () => {
          cannonball.x += dX / move_frames;
          cannonball.y += dY / move_frames;
          iternum += 1;
          if (iternum == move_frames) {
            cannonball.destroy();
            if (show_stars) {
              this.damage_stars(target_x, target_y, time);
            }
          }
        },
        callbackScope: this,
        delay: frame_delay, // 1000 = 1 second
        repeat: move_frames - 1,
      });
    }
  }

  rotate_boat(boat_id: number, angle: number, time: number) {
    time *= this.anim_frac;
    let frame_delay = time / this.move_frames;
    let boat = this.boats[boat_id];
    if (frame_delay < this.anim_cutoff) {
      boat.boat.angle += angle;
    } else {
      this.animationTimer = this.time.addEvent({
        callback: () => {
          boat.boat.angle += angle / this.move_frames;
        },
        callbackScope: this,
        delay: frame_delay, // 1000 = 1 second
        repeat: this.move_frames - 1,
      });
    }
  }

  move_boat(boat_id: number, move_x: number, move_y: number, time: number) {
    time *= this.anim_frac;
    let frame_delay = time / this.move_frames;
    let boat = this.boats[boat_id];
    if (frame_delay < this.anim_cutoff) {
      boat.boat.x += move_x;
      boat.boat.y += move_y;
      boat.bd.x += move_x;
      boat.bd.y += move_y;
    } else {
      this.animationTimer = this.time.addEvent({
        callback: () => {
          boat.boat.x += move_x / this.move_frames;
          boat.boat.y += move_y / this.move_frames;
          boat.bd.x += move_x / this.move_frames;
          boat.bd.y += move_y / this.move_frames;
        },
        callbackScope: this,
        delay: frame_delay, // 1000 = 1 second
        repeat: this.move_frames - 1,
      });
    }
  }

  collision_boat(
    boat_id: number,
    shake_x: number,
    shake_y: number,
    time: number
  ) {
    time *= this.anim_frac;
    const num_frames = 8; // fw, fw, fw, bw, fw, bw, bw, bw
    const dt_frames = time / num_frames;
    if (dt_frames > this.anim_cutoff) {
      let boat = this.boats[boat_id];
      this.animationTimer = this.time.addEvent({
        callback: () => {
          console.log('Collision forward steps');
          boat.boat.x += shake_x / num_frames;
          boat.boat.y += shake_y / num_frames;
          boat.bd.x += shake_x / num_frames;
          boat.bd.y += shake_y / num_frames;
        },
        callbackScope: this,
        delay: dt_frames,
        repeat: num_frames / 2,
      });
      this.animationTimer = this.time.addEvent({
        callback: () => {
          console.log('Collision backward steps');
          boat.boat.x -= shake_x / num_frames;
          boat.boat.y -= shake_y / num_frames;
          boat.bd.x -= shake_x / num_frames;
          boat.bd.y -= shake_y / num_frames;
        },
        callbackScope: this,
        delay: dt_frames * 3.5, // add a bit more to have backwards shakes shortly after forward moves
        repeat: num_frames / 2,
      });
    }
  }

  play_actionstack(animation_time_ms: number) {
    let GI = this.component.gameinfo;
    let actionstack = this.component.gameinfo.actionstack;

    console.log(
      'this.last_played_action',
      this.last_played_action,
      actionstack.length
    );

    for (let i = this.last_played_action; i < actionstack.length; i++) {
      let action_grp = actionstack[i];
      this.animationTimer = this.time.addEvent({
        callback: () => {
          console.log(action_grp);

          for (let action of action_grp) {
            if (action.target > 0) {
              let boat = this.boats[action.target];
              if (action.key === 'rotate') {
                // boat.angle += 90 * action.val;
                this.rotate_boat(
                  action.target,
                  90 * action.val,
                  animation_time_ms
                );
              } else if (action.key === 'move_x') {
                // boat.x += action.val * GI.map.tilewidth;
                this.move_boat(
                  action.target,
                  action.val * GI.map.tilewidth,
                  0,
                  animation_time_ms
                );
              } else if (action.key === 'move_y') {
                // boat.y += action.val * GI.map.tileheight;
                this.move_boat(
                  action.target,
                  0,
                  action.val * GI.map.tileheight,
                  animation_time_ms
                );
              } else if (action.key === 'collision_x') {
                this.collision_boat(
                  action.target,
                  action.val * GI.map.tileheight * 0.3,
                  0,
                  animation_time_ms
                );
              } else if (action.key === 'collision_y') {
                this.collision_boat(
                  action.target,
                  0,
                  action.val * GI.map.tileheight * 0.3,
                  animation_time_ms
                );
              } else if (action.key === 'shot') {
                let show_stars = action.other_player !== undefined;
                this.shoot_cannon(
                  action.target,
                  (action.collided_at[0] + 0.5) * GI.map.tilewidth,
                  (action.collided_at[1] + 0.5) * GI.map.tilewidth,
                  GI.map.tilewidth,
                  GI.map.tileheight,
                  show_stars,
                  animation_time_ms
                );
              } else {
                console.log('Error, key not found.');
              }
            }
          }
        },
        callbackScope: this,
        delay: (i - this.last_played_action) * animation_time_ms, // 1000 = 1 second
      });
    }

    this.animationTimer = this.time.addEvent({
      callback: () => {
        this.drawCheckpoints();
      },
      callbackScope: this,
      delay: (actionstack.length - this.last_played_action) * animation_time_ms, // 1000 = 1 second
    });

    this.last_played_action = actionstack.length;
  }

  create() {
    let GI = this.component.gameinfo;

    // create the Tilemap
    const map = this.make.tilemap({
      key: 'tilemap',
      tileWidth: GI.map.tilewidth,
      tileHeight: GI.map.tileheight,
    });

    // add the tileset image we are using
    const tileset = map.addTilesetImage(GI.map.tilesets[0].name, 'tileset');

    // create the layers we want in the right order
    map.createLayer(GI.map.layers[0].name, tileset, 0, 0);

    this.drawGrid();
    this.drawCheckpoints();

    Object.entries(GI.players).forEach(([playerid, player]) => {
      let color = Phaser.Display.Color.HexStringToColor(player['color']);
      let backdrop = this.add.rectangle(
        (player['start_pos_x'] + 0.5) * GI.map.tilewidth,
        (player['start_pos_y'] + 0.5) * GI.map.tileheight,
        GI.map.tilewidth,
        GI.map.tileheight,
        color.color,
        0.75
      );

      var boat = this.add.sprite(
        (player['start_pos_x'] + 0.5) * GI.map.tilewidth,
        (player['start_pos_y'] + 0.5) * GI.map.tileheight,
        'boat'
      );
      //set the width of the sprite
      boat.displayHeight = GI.map.tileheight * 1.5;
      //scale evenly
      boat.scaleX = boat.scaleY;
      boat.angle = player['start_direction'] * 90;

      this.boats[playerid] = {
        boat: boat,
        bd: backdrop,
      };
    });

    //return;
    this.play_actionstack(10); // play the first action stack really quickly in case user does a reload

    this.updateTimer = this.time.addEvent({
      callback: this.updateEvent,
      callbackScope: this,
      delay: 1000, // 1000 = 1 second
      loop: true,
    });
  }

  drawCheckpoints(): void {
    for (let text of this.checkpointLabels) {
      text.destroy();
    }
    this.checkpointLabels = [];
    let GI = this.component.gameinfo;
    let next_cp = GI.players[GI.me]['next_checkpoint'];
    Object.entries(GI.checkpoints).forEach(([name, pos]) => {
      let color = 'white';
      if (name < next_cp) {
        color = 'green';
      } else if (name == next_cp) {
        color = 'red';
      }
      let num = this.add.text(
        (pos[0] + 0.5) * GI.map.tilewidth,
        (pos[1] + 0.5) * GI.map.tileheight,
        name,
        {
          fontSize: '30px',
          strokeThickness: 5,
          stroke: color,
          color: color,
        }
      );
      num.setOrigin(0.5, 0.5);
      this.checkpointLabels.push(num);
    });
  }

  drawGrid(color = 0x000000, alpha = 0.2): void {
    let GI = this.component.gameinfo;
    console.log(GI);
    const Nx = GI.map.width;
    const Ny = GI.map.height;
    const maxX = GI.map.tilewidth * Nx; // FJ: no idea why the 2 is here
    const maxY = GI.map.tileheight * Ny; // FJ: no idea why the 2 is here

    for (let i = 0; i < Ny; i++) {
      //horizontal lines
      const y = i * GI.map.tileheight;
      this.add.line(maxX * 0.5, y, 0, 0, maxX, 0, color, alpha);
    }
    for (let j = 0; j < Nx; j++) {
      // vertical lines
      const x = j * GI.map.tilewidth;
      this.add.line(x, maxY * 0.5, 0, 0, 0, maxY, color, alpha);
    }
  }

  updateEvent(): void {
    this.component.load_gameinfo().subscribe((gameinfo) => {
      console.log('GameInfo ', gameinfo);
      this.component.gameinfo = gameinfo;
      this.component.Ngameround.next(gameinfo['Ngameround']);
      this.play_actionstack(1000);

      if (gameinfo.countdown) {
        if (this.component.countDownValue < 0) {
          this.component.setupCountDown(
            gameinfo.countdown_duration - gameinfo.countdown,
            gameinfo.countdown_duration
          );
        }
      }
    });
  }

  update() {}
}
