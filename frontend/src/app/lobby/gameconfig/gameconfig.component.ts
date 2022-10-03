import { Component, OnInit } from '@angular/core';
import { ToastController } from '@ionic/angular';
import { Router, ActivatedRoute } from '@angular/router';

import { GameConfig } from '../../model/gameconfig';
import { HttpService } from '../../services/http.service';
import { environment } from '../../../environments/environment';

@Component({
  selector: 'app-gameconfig',
  templateUrl: './gameconfig.component.html',
  styleUrls: ['./gameconfig.component.scss'],
})
export class GameConfigComponent implements OnInit {
  gameConfig: GameConfig;
  updateTimer: ReturnType<typeof setInterval>;
  phaserGame: Phaser.Game = null;

  constructor(
    private httpService: HttpService,
    private route: ActivatedRoute,
    private router: Router,
    private toastController: ToastController
  ) {}

  ngOnInit() {}

  registerupdateGameConfigInterval() {
    let id = +this.route.snapshot.paramMap.get('id');
    this.updateTimer = setInterval(() => {
      this.updateGameConfig(id);
    }, 2000);
  }

  updateGameConfig(id: number) {
    this.httpService.getGameConfig(id).subscribe(
      (gameconfig) => {
        this.gameConfig = gameconfig;
        console.log('GameConfig data', this.gameConfig);
        if (this.gameConfig['game']) {
          this.router.navigate(['game', this.gameConfig['game']]);
        }
        if (!this.phaserGame) {
          this.draw_phaser_snapshot();
        }
      },
      (error) => {
        console.log('Failed updateGameConfig:', error);
        this.presentToast(error.error, 'danger');
        this.router.navigate(['/lobby']);
      }
    );
  }

  createGame() {
    this.httpService.createGame(this.gameConfig.id).subscribe(
      (payload) => {
        console.log(payload);
        // this.router.navigate(['game', payload['game_id']]);
      },
      (error) => {
        console.log('Failed this.httpService.createGame:', error);
        this.presentToast(error.error, 'danger');
      }
    );
  }

  ionViewWillEnter() {
    let id = +this.route.snapshot.paramMap.get('id');
    console.log(id);
    this.updateGameConfig(id);
    this.registerupdateGameConfigInterval();
  }

  ionViewWillLeave() {
    this.remove_phaser_snapshot;
    clearInterval(this.updateTimer);
    this.leaveGameConfig();
  }

  leaveGameConfig() {
    this.httpService.leaveGameConfig().subscribe(
      (payload) => {
        console.log(payload);
        this.presentToast(payload['success'], 'success');
      },
      (error) => {
        console.log('Failed to leave this GameConfig:', error);
        this.presentToast(error.error, 'danger');
      }
    );
  }

  onPlayerInfoChange(event) {
    // console.log("Color", this.playerColor);
    this.httpService
      .updateGMPlayerInfo(this.gameConfig.id, {
        color: this.gameConfig['player_colors'][this.gameConfig['caller_idx']],
        team: this.gameConfig['player_teams'][this.gameConfig['caller_idx']],
        ready: this.gameConfig['player_ready'][this.gameConfig['caller_idx']],
      })
      .subscribe((data: any) => {
        this.gameConfig = data;
      });
  }

  async presentToast(msg, color = 'primary') {
    const toast = await this.toastController.create({
      message: msg,
      color: color,
      duration: 5000,
    });
    toast.present();
  }

  remove_phaser_snapshot() {
    if (this.phaserGame) {
      // remove old game if there is any
      this.phaserGame.destroy(true);
    }
  }

  draw_phaser_snapshot() {
    // draw a phaser3 map as quickview of a map
    this.remove_phaser_snapshot();

    // define variables for closure before `this` is captured by phaser
    let mapinfo = this.gameConfig.map_info;
    let mapfile = this.gameConfig.mapfile;
    let startinglocs = this.gameConfig.startinglocs;

    function phaser_preload() {
      console.log('phaser_preload', this);
      this.load.image(
        'tileset',
        `${environment.STATIC_URL}/maps/${mapinfo.tilesets[0].image}`
      );
      this.load.tilemapTiledJSON(
        'tilemap',
        `${environment.STATIC_URL}/maps/${mapfile}`
      );
      this.load.spritesheet(
        'boat',
        `${environment.STATIC_URL}/sprites/boat.png`,
        { frameWidth: 24, frameHeight: 72 }
      );
    }

    function phaser_create() {
      console.log('phaser_create', this);
      const map = this.make.tilemap({
        key: 'tilemap',
        tileWidth: mapinfo.tilewidth,
        tileHeight: mapinfo.tileheight,
      });

      // add the tileset image we are using
      const tileset = map.addTilesetImage(mapinfo.tilesets[0].name, 'tileset');

      // create the layers we want in the right order
      map.createLayer(mapinfo.layers[0].name, tileset, 0, 0);

      Object.entries(startinglocs.objects).forEach(([id, sloc]) => {
        console.log(id, sloc);
        var boat = this.add.sprite(sloc['x'], sloc['y'], 'boat');
        //set the width of the sprite
        boat.displayHeight = mapinfo.tileheight * 1.5;
        //scale evenly
        boat.scaleX = boat.scaleY;
      });
    }

    let config = {
      type: Phaser.AUTO,
      physics: { default: 'None' },
      parent: 'map-preview',
      width:
        this.gameConfig.map_info.width * this.gameConfig.map_info.tilewidth,
      height:
        this.gameConfig.map_info.height * this.gameConfig.map_info.tileheight,
      scale: {
        mode: Phaser.Scale.FIT,
      },
      fps: {
        target: 0,
        forceSetTimeOut: true,
      },
      scene: {
        preload: phaser_preload,
        create: phaser_create,
      },
    };

    this.phaserGame = new Phaser.Game(config);
    this.phaserGame.scene.pause('default');
  }
}
