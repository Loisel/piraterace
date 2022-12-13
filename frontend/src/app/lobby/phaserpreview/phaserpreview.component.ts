import { Component, Input } from '@angular/core';
import { ToastController } from '@ionic/angular';
import { HttpService } from '../../services/http.service';

import { environment } from '../../../environments/environment';
import { MapInfo } from '../../model/mapinfo';
import Phaser from 'phaser';

@Component({
  selector: 'app-phaserpreview',
  templateUrl: './phaserpreview.component.html',
  styleUrls: ['./phaserpreview.component.scss'],
})
export class PhaserPreviewComponent {
  constructor(private httpService: HttpService, private toastController: ToastController) {
    this.mapid = 'map-preview-' + Math.random().toString(36).substring(2);
  }
  mapid: string = null;

  _mapfile: string;
  mapinfo: MapInfo = null;
  phaserGame: Phaser.Game = null;
  canvasWidth: number = 350;
  canvasHeight: number = 350;

  @Input() set mapfile(value: string) {
    this._mapfile = value;
    this.getMapInfo();
  }

  getMapInfo() {
    this.httpService.getMapInfo(this._mapfile).subscribe(
      (mapinfo) => {
        this.mapinfo = mapinfo;
        console.log('Load map info ', mapinfo);
        this.drawPhaserSnapshot();
      },
      (error) => {
        console.log('Failed to leave this GameConfig:', error);
        this.presentToast(error.error, 'danger');
      }
    );
  }

  drawPhaserSnapshot() {
    // draw a phaser3 map as quickview of a map
    this.removePhaserSnapshot();

    // define variables for closure before `this` is captured by phaser
    let mapid = this.mapid;
    let startinglocs = this.mapinfo.startinglocs;
    let checkpoints = this.mapinfo.checkpoints;
    let thismapfile = this._mapfile;
    let thismapinfo = this.mapinfo.map_info;

    function phaser_preload() {
      console.log('phaser_preload', this);
      this.load.image('tileset', `${environment.STATIC_URL}/maps/${thismapinfo.tilesets[0].image}`);
      this.load.tilemapTiledJSON('tilemap', `${environment.STATIC_URL}/maps/${thismapfile}`);
      this.load.spritesheet('boat', `${environment.STATIC_URL}/sprites/boat.png`, { frameWidth: 24, frameHeight: 72 });
    }

    function phaser_create() {
      console.log('phaser_create', this);
      const map = this.make.tilemap({
        key: 'tilemap',
        tileWidth: thismapinfo.tilewidth,
        tileHeight: thismapinfo.tileheight,
      });

      // add the tileset image we are using
      const tileset = map.addTilesetImage(thismapinfo.tilesets[0].name, 'tileset');

      // create the layers we want in the right order
      map.createLayer(thismapinfo.layers[0].name, tileset, 0, 0);

      startinglocs.forEach(([x, y]) => {
        var boat = this.add.sprite(x, y, 'boat');
        //set the width of the sprite
        boat.displayHeight = thismapinfo.tileheight;
        //scale evenly
        boat.scaleX = boat.scaleY;
      });

      Object.entries(checkpoints).forEach(([name, pos]) => {
        let color = 'white';
        let num = this.add.text((pos[0] + 0.5) * thismapinfo.tilewidth, (pos[1] + 0.5) * thismapinfo.tileheight, name, {
          fontSize: '30px',
          strokeThickness: 5,
          stroke: color,
          color: color,
        });
        num.setOrigin(0.5, 0.5);
      });
    }

    let config = {
      type: Phaser.AUTO,
      physics: { default: 'None' },
      scale: {
        parent: mapid,
        mode: Phaser.Scale.FIT,
        autoCenter: Phaser.Scale.CENTER_BOTH,
        width: thismapinfo.width * thismapinfo.tilewidth,
        height: thismapinfo.height * thismapinfo.tileheight,
      },
      transparent: true,
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

  removePhaserSnapshot() {
    if (this.phaserGame) {
      // remove old game if there is any
      this.phaserGame.destroy(true);
    }
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
