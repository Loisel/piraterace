import { IonicModule } from '@ionic/angular';
import { ToastController } from '@ionic/angular';
import { Platform } from '@ionic/angular';
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

  gameWidth: number;
  gameHeight: number;
  submittedCards: boolean = false;
  poweredDown: boolean = false;

  @ViewChild('game_div', { read: ElementRef }) game_div: ElementRef;
  @ViewChild('cards_menu', { read: ElementRef }) cards_menu: ElementRef;
  @ViewChild('tools_menu', { read: ElementRef }) tools_menu: ElementRef;

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
            // min: {
            //   height: this.game_div.nativeElement.offsetHeight,
            // },
            // max: {
            //   height: this.game_div.nativeElement.offsetHeight,
            // },
            mode: Phaser.Scale.NONE,
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

        this.cards_menu.nativeElement.style.borderColor =
          gameinfo['players'][gameinfo['me']]['color'];
        this.tools_menu.nativeElement.style.borderColor =
          gameinfo['players'][gameinfo['me']]['color'];
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

  cardCheck(i: number) {
    if (this.gameinfo) {
      if (this.gameinfo.players[this.gameinfo.me]['powered_down']) {
        return true;
      }
      if (this.gameinfo['state'] === 'animate') {
        return true;
      }
      return i >= this.gameinfo.players[this.gameinfo.me]['health'];
    } else {
      return false;
    }
  }

  onCardsReorder(event) {
    console.log(event.detail);
    this.httpService
      .switchPlayerCards(event.detail.from, event.detail.to)
      .subscribe(
        (result) => {
          console.log('switch cards:', result);
          this.cardsinfo = result;
          event.detail.complete(true);
        },
        (error) => {
          console.log('failed reorder cards: ', error);
          this.presentToast(error.error, 'danger');
          event.detail.complete(false);
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
      },
      (error) => {
        this.presentToast(error.error, 'danger');
        this.poweredDown = true;
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
    //console.log('damage_stars @ ', target_x, target_y);
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

  repair_animation(boat_id: number, time: number) {
    let boat = this.boats[boat_id].getChildren()[0];
    let target_x = boat.x;
    let target_y = boat.y;
    console.log('repair animation @ ', target_x, target_y);
    time *= this.anim_frac;
    let frame_delay = time / this.move_frames;
    if (frame_delay >= this.anim_cutoff) {
      let stars = this.add.group();
      stars.add(this.add.star(target_x - 2, target_y + 6, 5, 6, 11, 0x00ff00));
      stars.add(this.add.star(target_x - 5, target_y - 11, 5, 8, 13, 0x00ff00));
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

  check_player_state() {
    let valid = true;
    let GI = this.component.gameinfo;
    Object.entries(GI.players).forEach(([playerid, player]) => {
      console.log('check_player_state', player);
      let boatgrp = this.boats[playerid];
      let boat = boatgrp.getChildren()[0];
      let boat_x = Math.floor(boat.x / GI.map.tilewidth);
      let boat_y = Math.floor(boat.y / GI.map.tileheight);
      if (boat_x !== player['pos_x']) {
        console.log(
          'Error: Inconsistent boat position in x ! Should be ',
          player,
          player['pos_x'],
          ' in game: ',
          boat_x
        );
        valid = false;
      }
      if (boat_y !== player['pos_y']) {
        console.log(
          'Error: Inconsistent boat position in y ! Should be ',
          player,
          player['pos_y'],
          ' in game: ',
          boat_y
        );
        valid = false;
      }
    });
    console.log('check_player_state: ', valid);
  }

  shoot_cannon(
    src_x: number,
    src_y: number,
    target_x: number,
    target_y: number,
    damage: number,
    tilewidth: number,
    tileheight: number,
    show_stars: boolean,
    time: number
  ) {
    let dX = target_x - src_x;
    let dY = target_y - src_y;
    // distance in number of tiles
    let dist = Math.round(
      Math.max(Math.abs(dX) / tilewidth, Math.abs(dY) / tileheight)
    );
    time *= this.anim_frac;
    // one frame per tile
    let move_frames = dist;
    let frame_delay = time / move_frames;
    if (frame_delay >= this.anim_cutoff) {
      console.log(
        'Shooting cannon: from',
        src_x,
        src_y,
        'to x/y',
        target_x,
        target_y
      );

      let cannonball = this.add.circle(src_x, src_y, 7, 0);
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

  update_healthbar(
    boat_id: number,
    damage: number,
    time: number,
    value: number = undefined
  ) {
    let bar = this.boats[boat_id].getChildren()[2];
    this.animationTimer = this.time.addEvent({
      callback: () => {
        if (value) {
          bar.setHealth(value);
        } else {
          bar.decrease(damage);
        }
      },
      callbackScope: this,
      delay: time, // 1000 = 1 second
      repeat: 0,
    });
  }

  rotate_boat(boat_id: number, angle: number, time: number) {
    time *= this.anim_frac;
    let frame_delay = time / this.move_frames;
    let boat = this.boats[boat_id].getChildren()[0];
    if (frame_delay < this.anim_cutoff) {
      boat.angle += angle;
    } else {
      this.animationTimer = this.time.addEvent({
        callback: () => {
          boat.angle += angle / this.move_frames;
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
      boat.incX(move_x);
      boat.incY(move_y);
    } else {
      this.animationTimer = this.time.addEvent({
        callback: () => {
          boat.incX(move_x / this.move_frames);
          boat.incY(move_y / this.move_frames);
        },
        callbackScope: this,
        delay: frame_delay, // 1000 = 1 second
        repeat: this.move_frames - 1,
      });
    }
  }

  flush_down_boat(boat_id: number, time: number) {
    let GI = this.component.gameinfo;
    let GIplayer = this.component.gameinfo.players[boat_id];
    time *= this.anim_frac;
    let N = 8;
    let frame_delay = time / N;
    let angle = (2 * Math.PI) / N;
    let boat = this.boats[boat_id];
    if (frame_delay < this.anim_cutoff) {
    } else {
      this.animationTimer = this.time.addEvent({
        callback: () => {
          boat.scaleXY(-1 / N, -1 / N);
          boat.rotate(angle);
        },
        callbackScope: this,
        delay: frame_delay, // 1000 = 1 second
        repeat: N - 1,
      });
    }
  }

  death_by_collision(boat_id: number, time: number) {
    let GI = this.component.gameinfo;
    let GIplayer = this.component.gameinfo.players[boat_id];
    time *= this.anim_frac;
    let N = 8;
    let frame_delay = time / N;
    let boat_group = this.boats[boat_id];

    let boat = boat_group.getChildren()[0];
    this.damage_stars(boat.x, boat.y, time);

    if (frame_delay < this.anim_cutoff) {
    } else {
      this.animationTimer = this.time.addEvent({
        callback: () => {
          boat_group.scaleXY(-1 / N, -1 / N);
        },
        callbackScope: this,
        delay: frame_delay, // 1000 = 1 second
        repeat: N - 1,
      });
    }
  }

  death_by_cannon(boat_id: number, time: number) {
    let GI = this.component.gameinfo;
    let GIplayer = this.component.gameinfo.players[boat_id];
    time *= this.anim_frac;
    let N = 8;
    let frame_delay = time / N;
    let boat_group = this.boats[boat_id];

    let boat = boat_group.getChildren()[0];
    this.damage_stars(boat.x, boat.y, time);

    if (frame_delay < this.anim_cutoff) {
    } else {
      this.animationTimer = this.time.addEvent({
        callback: () => {
          boat_group.scaleXY(-1 / N, -1 / N);
        },
        callbackScope: this,
        delay: frame_delay, // 1000 = 1 second
        repeat: N - 1,
      });
    }
  }

  respawn_boat(boat_id: number, time: number) {
    let GI = this.component.gameinfo;
    let GIplayer = this.component.gameinfo.players[boat_id];
    time *= this.anim_frac;
    let frame_delay = time / this.move_frames;
    let boat = this.boats[boat_id];
    boat.setXY(
      (GIplayer['start_pos_x'] + 0.5) * GI.map.tilewidth,
      (GIplayer['start_pos_y'] + 0.5) * GI.map.tileheight
    );
    if (frame_delay < this.anim_cutoff) {
    } else {
      let N = this.move_frames;
      boat.scaleXY(N + 1, N + 1);
      this.animationTimer = this.time.addEvent({
        callback: () => {
          boat.scaleXY(-1, -1);
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
    damage: number,
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
          boat.incX(shake_x / num_frames);
          boat.incY(shake_y / num_frames);
        },
        callbackScope: this,
        delay: dt_frames,
        repeat: num_frames / 2,
      });
      this.animationTimer = this.time.addEvent({
        callback: () => {
          console.log('Collision backward steps');
          boat.incX(-shake_x / num_frames);
          boat.incY(-shake_y / num_frames);
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
          console.log('Action Group:', action_grp);

          for (let action of action_grp) {
            console.log('Action:', action);
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
                action.damage,
                animation_time_ms
              );
              this.update_healthbar(
                action.target,
                action.damage,
                animation_time_ms
              );
            } else if (action.key === 'collision_y') {
              this.collision_boat(
                action.target,
                0,
                action.val * GI.map.tileheight * 0.3,
                action.damage,
                animation_time_ms
              );
              this.update_healthbar(
                action.target,
                action.damage,
                animation_time_ms
              );
            } else if (action.key === 'shot') {
              let show_stars = action.other_player !== undefined;
              this.shoot_cannon(
                (action.src_x + 0.5) * GI.map.tilewidth,
                (action.src_y + 0.5) * GI.map.tilewidth,
                (action.collided_at[0] + 0.5) * GI.map.tilewidth,
                (action.collided_at[1] + 0.5) * GI.map.tilewidth,
                action.damage,
                GI.map.tilewidth,
                GI.map.tileheight,
                show_stars,
                animation_time_ms
              );
              if (action.other_player !== undefined) {
                this.update_healthbar(
                  action.other_player,
                  action.damage,
                  animation_time_ms
                );
              }
            } else if (action.key === 'death') {
              if (action.type === 'void') {
                this.flush_down_boat(action.target, animation_time_ms);
              } else if (action.type === 'collision') {
                this.death_by_collision(action.target, animation_time_ms);
              } else if (action.type === 'cannon') {
                this.death_by_cannon(action.target, animation_time_ms);
              } else {
                console.log('unknown type of death: ', action.type);
              }
            } else if (action.key === 'respawn') {
              this.respawn_boat(action.target, animation_time_ms);
              this.update_healthbar(
                action.target,
                0,
                animation_time_ms,
                GI.players[action.target]['health']
              );
            } else if (action.key === 'repair') {
              this.repair_animation(action.target, animation_time_ms);
              this.update_healthbar(
                action.target,
                -action.val,
                animation_time_ms
              );
            } else {
              console.log('Error, key not found.');
            }
          }
        },
        callbackScope: this,
        delay: (i - this.last_played_action) * animation_time_ms, // 1000 = 1 second
      });
    }

    if (this.last_played_action < actionstack.length) {
      this.animationTimer = this.time.addEvent({
        callback: () => {
          this.drawCheckpoints();
          this.check_player_state();
        },
        callbackScope: this,
        delay:
          (actionstack.length - this.last_played_action) * animation_time_ms, // 1000 = 1 second
      });
    }

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

      let hp = new HealthBar(
        this,
        (player['start_pos_x'] + 0.5) * GI.map.tilewidth,
        (player['start_pos_y'] + 0.5) * GI.map.tileheight,
        GI.map.tilewidth * 0.8,
        GI.map.tileheight * 0.12,
        GI.initial_health
      );

      let group = this.add.group();
      group.add(boat);
      group.add(backdrop);
      group.add(hp);
      this.boats[playerid] = group;
    });

    // camera draggable, start on player boat
    var cam = this.cameras.main;
    var myBoat = this.boats[GI.me].getChildren()[0];
    // would be nice to have camera respect bounds, but tests with responsive mode not successful
    cam.centerOn(myBoat.x, myBoat.y);
    //cam.setBounds(0, 0, GI.map.tilewidth * GI.map.width, GI.map.tileheight * GI.map.height);

    this.input.on('pointermove', function (p) {
      if (!p.isDown) return;

      cam.scrollX -= (p.x - p.prevPosition.x) / cam.zoom;
      cam.scrollY -= (p.y - p.prevPosition.y) / cam.zoom;
    });

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
      this.play_actionstack(gameinfo['time_per_action'] * 1000);

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
}

class HealthBar extends Phaser.GameObjects.Container {
  value: number;
  initial_health: number;
  width: number;
  height: number;
  bar: Phaser.GameObjects.Graphics;
  scene: GameScene;
  constructor(scene, x, y, width, height, initial_health) {
    super(scene);
    this.scene = scene;
    this.x = x;
    this.y = y;
    this.width = width;
    this.height = height;

    this.bar = this.scene.add.graphics();
    this.add(this.bar);

    this.initial_health = initial_health;
    this.value = initial_health;

    this.draw();
    this.scene.add.existing(this);
  }

  decrease(amount) {
    this.value -= amount;

    if (this.value < 0) {
      this.value = 0;
    }
    this.draw();
    return this.value === 0;
  }

  setHealth(value) {
    //console.log('Set healthbar value... from ', this.value, ' to ', value);
    this.value = value;
    this.draw();
  }

  draw() {
    this.bar.clear();
    let GI = this.scene.component.gameinfo;
    const xoffset = -GI.map.tilewidth * 0.4;
    const yoffset = GI.map.tileheight * 0.3;

    //  BG
    this.bar.fillStyle(0x000000);
    this.bar.fillRect(xoffset, yoffset, this.width, this.height);

    //  Health

    this.bar.fillStyle(0xffffff);
    this.bar.fillRect(
      xoffset + 2,
      yoffset + 2,
      this.width - 4,
      this.height - 2
    );

    console.log('initial health:', this.initial_health, 'value:', this.value);
    if (this.value <= this.initial_health * 0.3) {
      this.bar.fillStyle(0xff0000);
    } else if (this.value <= this.initial_health * 0.6) {
      this.bar.fillStyle(0xffe900);
    } else {
      this.bar.fillStyle(0x00ff00);
    }
    var d = Math.floor((this.value / this.initial_health) * (this.width - 4));
    this.bar.fillRect(xoffset + 2, yoffset + 2, d, this.height - 2);
  }
}
