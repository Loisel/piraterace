import { IonicModule } from '@ionic/angular';
import { Component, OnInit } from '@angular/core';
import { HttpService } from '../http.service';
import { Router, ActivatedRoute } from '@angular/router';
import { interval } from 'rxjs';
import Phaser from 'phaser';
import { environment } from '../../environments/environment';

@Component({
  selector: 'app-game',
  templateUrl: './game.component.html',
  providers: [HttpService],
  styleUrls: ['./game.component.scss'],
})
export class GameComponent implements OnInit {
  phaserGame: Phaser.Game;
  config: Phaser.Types.Core.GameConfig;
  gameinfo: any = null;
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
        this.config = {
          type: Phaser.AUTO,
          physics: { default: 'None' },
          scale: {
            mode: Phaser.Scale.FIT,
            parent: 'game',
            width: this.gameinfo.map.width * this.gameinfo.map.tilewidth,
            height: this.gameinfo.map.height * this.gameinfo.map.tileheight,
          },
        };

        this.config.scene = new GameScene(this.config, this);
        this.phaserGame = new Phaser.Game(this.config);
      },
      (err) => console.error(err),
      () => console.log('observable complete')
    );
  }

  load_gameinfo() {
    let id = +this.route.snapshot.paramMap.get('game_id');
    return this.httpService.getGame(id);
  }
}

class GameScene extends Phaser.Scene {
  updateTimer: Phaser.Time.TimerEvent;
  boats: any = {};
  last_played_action: number = 0;
  component: any = null;
  constructor(config, component) {
    super(config);
    this.component = component;
  }

  preload() {
    console.log('Component', this.component);
    this.load.image('tileset', `${environment.STATIC_URL}/maps/wateru.png`);
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

  async delay(ms: number) {
    return new Promise((resolve) => setTimeout(resolve, ms));
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
      this.delay((i - this.last_played_action) * animation_time_ms).then(
        (any) => {
          console.log(action);

          if (action.target > 0) {
            let boat = this.boats[action.target];
            if (action.key === 'rotate') {
              boat.angle += 90 * action.val;
            }
            if (action.key === 'move_x') {
              boat.x += action.val * GI.map.tilewidth;
            }
            if (action.key === 'move_y') {
              boat.y += action.val * GI.map.tileheight;
            }
          }
        }
      );
    }
    this.last_played_action = actionstack.length;
  }

  create() {
    let GI = this.component.gameinfo;

    // create the Tilemap
    const map = this.make.tilemap({
      key: 'tilemap',
      tileWidth: 16,
      tileHeight: 16,
    });

    // add the tileset image we are using
    const tileset = map.addTilesetImage('tileset1', 'tileset');

    // create the layers we want in the right order
    map.createLayer('Background', tileset, 0, 0);

    Object.entries(GI.players).forEach(([playerid, player]) => {
      console.log(playerid, player);
      var boat = this.add.sprite(
        (player['start_pos_x'] - 0.5) * GI.map.tilewidth,
        (player['start_pos_y'] - 0.5) * GI.map.tileheight,
        'boat'
      );
      //set the width of the sprite
      boat.displayHeight = GI.map.tileheight * 1.5;
      //scale evenly
      boat.scaleX = boat.scaleY;
      boat.angle = player['start_direction'] * 90;
      this.boats[playerid] = boat;
    });

    this.play_actionstack(5); // play the first action stack really quickly in case user does a reload

    this.updateTimer = this.time.addEvent({
      callback: this.updateEvent,
      callbackScope: this,
      delay: 1000, // 1000 = 1 second
      loop: true,
    });
  }

  updateEvent(): void {
    this.component.load_gameinfo().subscribe((gameinfo) => {
      console.log('UpdateEvent:', gameinfo);
      this.component.gameinfo = gameinfo;
      this.play_actionstack(500);
    });
  }

  update() {}
}
