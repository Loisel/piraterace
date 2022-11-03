import { Component, OnInit, OnDestroy } from '@angular/core';
import { Router, ActivatedRoute } from '@angular/router';
import Phaser from 'phaser';
import { ToastController } from '@ionic/angular';

import { HttpService } from '../../services/http.service';
import { NewGameConfig } from '../../model/newgameconfig';
import { environment } from '../../../environments/environment';

@Component({
  selector: 'app-newgameconfig',
  templateUrl: './newgameconfig.component.html',
  styleUrls: ['./newgameconfig.component.scss'],
})
export class NewGameConfigComponent {
  data: NewGameConfig = null;
  phaserGame: Phaser.Game = null;

  constructor(
    private httpService: HttpService,
    private router: Router,
    private route: ActivatedRoute,
    private toastController: ToastController
  ) {}

  ionViewWillEnter() {
    this.httpService.get_create_new_gameConfig().subscribe((response) => {
      console.log('Get get_create_new_gameConfig', response);
      this.data = response;
    });
  }

  ionViewWillLeave() {
    this.remove_phaser_snapshot();
  }

  selectMapChange(e) {
    // monitoring changes in the maps dropdown
    console.log('selectMapChange', e);
    this.data.selected_map = e.target.value;

    this.httpService.post_create_new_gameConfig(this.data).subscribe((response) => {
      console.log('post post_create_new_gameConfig', response);
      this.data = response;
      this.draw_phaser_snapshot();
    });
  }

  createGameConfig(event) {
    // create a GameConfig
    console.log('Create a gameConfig');
    this.httpService.createGameConfig(this.data).subscribe(
      (gameConfig) => {
        this.remove_phaser_snapshot();
        console.log('New GameConfig response:', gameConfig);
        this.router.navigate(['../view_gameconfig', gameConfig.id], {
          relativeTo: this.route,
        });
      },
      (err) => {
        console.log(err);
        this.presentToast(err.error, 'danger');
      }
    );
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
    let mapinfo = this.data.map_info;
    let selected_map = this.data.selected_map;
    let startinglocs = this.data.startinglocs;

    function phaser_preload() {
      console.log('phaser_preload', this);
      this.load.image('tileset', `${environment.STATIC_URL}/maps/${mapinfo.tilesets[0].image}`);
      this.load.tilemapTiledJSON('tilemap', `${environment.STATIC_URL}/maps/${selected_map}`);
      this.load.spritesheet('boat', `${environment.STATIC_URL}/sprites/boat.png`, { frameWidth: 24, frameHeight: 72 });
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
      width: this.data.map_info.width * this.data.map_info.tilewidth,
      height: this.data.map_info.height * this.data.map_info.tileheight,
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

  async presentToast(msg, color = 'primary') {
    const toast = await this.toastController.create({
      message: msg,
      color: color,
      duration: 5000,
    });
    toast.present();
  }
}
