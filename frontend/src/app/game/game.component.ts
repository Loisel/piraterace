import { IonicModule } from '@ionic/angular';
import { Component, OnInit } from '@angular/core';
import { HttpService } from '../http.service'
import { Router, ActivatedRoute } from '@angular/router'
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
  ) {
  }

  ngOnInit() {
    let id = +this.route.snapshot.paramMap.get("game_id");

    this.httpService.getGame(id).subscribe(gameinfo => {
      console.log("Game:", gameinfo);
      this.gameinfo = gameinfo;
      this.config = {
        type: Phaser.AUTO,
        physics: {},
        scale: {
          mode: Phaser.Scale.FIT,
          parent: 'game',
          width: this.gameinfo.map.width * this.gameinfo.map.tilewidth,
          height: this.gameinfo.map.height * this.gameinfo.map.tileheight,
        },
      };

      this.config.scene = new GameScene(this.config, this)
      this.phaserGame = new Phaser.Game(this.config);
    });
  }

}

class GameScene extends Phaser.Scene {
  boats: any = {};
  component: any = null;
  constructor(config, component) {
    super(config);
    this.component = component;
  }

  preload() {
    console.log("Component", this.component);
    this.load.image('tileset', `${environment.STATIC_URL}/maps/wateru.png`);
    this.load.tilemapTiledJSON('tilemap', `${environment.STATIC_URL}/maps/${this.component.gameinfo.mapfile}`);
    this.load.spritesheet('boat',
        `${environment.STATIC_URL}/sprites/boat.png`,
        { frameWidth: 24, frameHeight: 72 }
    );
  }

  play_actionstack() {
    let GI = this.component.gameinfo;
    let actionstack = this.component.gameinfo.actionstack;
    actionstack.forEach( (action) => {
      console.log(action);
      if (action.target > 0) {
        let boat = this.boats[action.target];
        if (action.key === "rotate") {
          boat.angle += 90 * action.val;
        }
        if (action.key === "move_x") {
          boat.x += action.val * GI.map.tilewidth;
        }
        if (action.key === "move_y") {
          boat.y += action.val * GI.map.tileheight;
        }
      }

    });
  }

  create() {
    let GI = this.component.gameinfo;

    // create the Tilemap
    const map = this.make.tilemap({ key: 'tilemap', tileWidth: 16, tileHeight: 16})

    // add the tileset image we are using
    const tileset = map.addTilesetImage('tileset1', 'tileset')

    // create the layers we want in the right order
    map.createLayer('Background', tileset, 0, 0);

    Object.entries(GI.players).forEach( ([playerid, player]) => {
        console.log(playerid, player);
        var boat = this.add.sprite(
          (player['start_pos_x']-.5) * GI.map.tilewidth,
          (player['start_pos_y']-.5) * GI.map.tileheight,
          "boat");
          //set the width of the sprite
          boat.displayHeight = GI.map.tileheight;
          //scale evenly
          boat.scaleX = boat.scaleY;
          boat.angle = player['start_direction'] * 90;
        this.boats[playerid] = boat;
      }
    );


    this.play_actionstack();
  }

  update() {
  }
}


