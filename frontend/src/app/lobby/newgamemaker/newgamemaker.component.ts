import { Component, OnInit, OnDestroy } from '@angular/core';
import { Router, ActivatedRoute } from '@angular/router';
import Phaser from 'phaser';

import { HttpService } from '../../services/http.service';
import { NewGameMaker } from '../../model/newgamemaker';
import { environment } from '../../../environments/environment';

@Component({
  selector: 'app-newgamemaker',
  templateUrl: './newgamemaker.component.html',
  styleUrls: ['./newgamemaker.component.scss'],
})
export class NewGameMakerComponent implements OnInit {
  data: NewGameMaker = null;
  phaserGame: Phaser.Game = null;

  constructor(
    private httpService: HttpService,
    private router: Router,
    private route: ActivatedRoute
  ) {}

  ngOnInit() {
    this.httpService.get_create_new_gameMakerURL().subscribe((response) => {
      console.log('Get get_create_new_gameMakerURL', response);
      this.data = response;
    });
  }

  ngOnDestroy() {
    this.remove_phaser_snapshot();
  }

  selectMapChange(e) {
    // monitoring changes in the maps dropdown
    console.log('selectMapChange', e);
    this.data.selected_map = e.target.value;

    this.httpService
      .post_create_new_gameMakerURL(this.data)
      .subscribe((response) => {
        console.log('post post_create_new_gameMakerURL', response);
        this.data = response;
        this.draw_phaser_snapshot();
      });
  }

  createGameMaker(event) {
    // create a GameMaker
    console.log('Create a gameMaker');
    this.httpService.createGameMaker(this.data).subscribe(
      (gameMaker) => {
        this.remove_phaser_snapshot();
        console.log('New GameMaker response:', gameMaker);
        this.router.navigate(['../view_gamemaker', gameMaker.id], {
          relativeTo: this.route,
        });
      },
      (err) => {
        console.log(err);
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
      this.load.image(
        'tileset',
        `${environment.STATIC_URL}/maps/${mapinfo.tilesets[0].image}`
      );
      this.load.tilemapTiledJSON(
        'tilemap',
        `${environment.STATIC_URL}/maps/${selected_map}`
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
      scale: {
        mode: Phaser.Scale.FIT,
        parent: 'game',
        width: this.data.map_info.width * this.data.map_info.tilewidth,
        height: this.data.map_info.height * this.data.map_info.tileheight,
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
