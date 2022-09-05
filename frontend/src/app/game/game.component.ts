import { IonicModule } from '@ionic/angular';
import { Component, OnInit, OnDestroy } from '@angular/core';
import { HttpService } from '../services/http.service';
import { Router, ActivatedRoute } from '@angular/router';
import { interval, BehaviorSubject } from 'rxjs';
import { filter, pairwise } from 'rxjs/operators';
import Phaser from 'phaser';
import { environment } from '../../environments/environment';

@Component({
  selector: 'app-game',
  templateUrl: './game.component.html',
  styleUrls: ['./game.component.scss'],
})
export class GameComponent implements OnInit, OnDestroy {
  phaserGame: Phaser.Game;
  defaultScene: GameScene;
  config: Phaser.Types.Core.GameConfig;
  gameinfo: any = null;
  cardsinfo: any = [];
  CARDS_URL = environment.STATIC_URL;
  Ngameround = new BehaviorSubject<number>(0);

  constructor(
    private httpService: HttpService,
    private route: ActivatedRoute,
    private router: Router
  ) {}

  ngOnInit() {
    this.load_gameinfo().subscribe(
      (gameinfo) => {
        console.log('Game:', gameinfo);
        this.gameinfo = gameinfo;
        this.Ngameround.next(gameinfo['Ngameround']);
        this.config = {
          type: Phaser.AUTO,
          physics: { default: 'None' },
          scale: {
            mode: Phaser.Scale.FIT,
            parent: 'game',
            width: this.gameinfo.map.width * this.gameinfo.map.tilewidth,
            height: this.gameinfo.map.height * this.gameinfo.map.tileheight,
          },
          fps: {
            target: 24,
            forceSetTimeOut: true,
          },
        };

        this.config.scene = new GameScene(this.config, this);
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
        this.getPlayerCards();
      });
  }

  ngOnDestroy() {}

  ionViewWillLeave() {
    this.phaserGame.destroy(true, false);
    // this.defaultScene.updateTimer.paused = true;
  }

  load_gameinfo() {
    let id = +this.route.snapshot.paramMap.get('game_id');
    return this.httpService.getGame(id);
  }

  getPlayerCards() {
    this.httpService.getPlayerCards().subscribe((result) => {
      this.cardsinfo = result;
    });
  }

  onCardsReorder({ detail }) {
    console.log(detail);
    this.httpService
      .switchPlayerCards(detail.from, detail.to)
      .subscribe((result) => {
        console.log('switch cards:', result);
        this.cardsinfo = result;
        detail.complete(true);
      });
  }
}

class GameScene extends Phaser.Scene {
  updateTimer: Phaser.Time.TimerEvent;
  animationTimer: Phaser.Time.TimerEvent;
  boats: any = {};
  last_played_action: number = 0;
  component: any = null;
  // animation config
  move_frames: number = 3;
  anim_frac: number = 0.5;
  anim_cutoff: number = 10; // below this duration we just skip animations
  constructor(config, component) {
    super(config);
    this.component = component;
    this.component.defaultScene = this;
  }

  preload() {
    console.log('Component', this.component);
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

  rotate_boat(boat_id: number, angle: number, time: number) {
    time *= this.anim_frac;
    let frame_delay = time / this.move_frames;
    let boat = this.boats[boat_id];
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
      boat.x += move_x;
      boat.y += move_y;
    } else {
      this.animationTimer = this.time.addEvent({
        callback: () => {
          boat.x += move_x / this.move_frames;
          boat.y += move_y / this.move_frames;
        },
        callbackScope: this,
        delay: frame_delay, // 1000 = 1 second
        repeat: this.move_frames - 1,
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
      let action = actionstack[i];
      this.animationTimer = this.time.addEvent({
        callback: () => {
          console.log(action);

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
            } else {
              console.log('Error, key not found.');
            }
          }
        },
        callbackScope: this,
        delay: (i - this.last_played_action) * animation_time_ms, // 1000 = 1 second
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

    Object.entries(GI.players).forEach(([playerid, player]) => {
      console.log(playerid, player);
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
      this.boats[playerid] = boat;
    });

    //return;
    this.play_actionstack(100); // play the first action stack really quickly in case user does a reload

    this.updateTimer = this.time.addEvent({
      callback: this.updateEvent,
      callbackScope: this,
      delay: 1000, // 1000 = 1 second
      loop: true,
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
      console.log('UpdateEvent:', gameinfo);
      this.component.gameinfo = gameinfo;
      this.component.Ngameround.next(gameinfo['Ngameround']);
      this.play_actionstack(1000);
    });
  }

  update() {}
}
