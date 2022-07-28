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
  game: any = null;
  constructor(
    private httpService: HttpService,
    private route: ActivatedRoute,
    private router: Router
  ) {
    this.config = {
      type: Phaser.AUTO,
      width: 800,
      height: 600,
      physics: {},
      parent: 'game'
    };

    this.config.scene = new GameScene(this.config, this)
    
  }

  ngOnInit() {
    let id = +this.route.snapshot.paramMap.get("game_id");

    this.httpService.getGame(id).subscribe(game => {
      console.log("Game:", game);
      this.game = game;
      this.phaserGame = new Phaser.Game(this.config);
    });
  }

}

class GameScene extends Phaser.Scene {
  component:any = null;
  constructor(config, component) {
    super(config);
    this.component = component;
  }

  preload() {
    console.log("Component", this.component);
    this.load.image('tileset', `${environment.API_URL}/static/maps/wateru.png`);
    this.load.tilemapTiledJSON('tilemap', `${environment.API_URL}/static/maps/${this.component.game.mapfile}`);
    this.add.text(0.5,0.5,"Huhu");
  }

  create() {
  // create the Tilemap
    const map = this.make.tilemap({ key: 'tilemap', tileWidth: 16, tileHeight: 16})

    // add the tileset image we are using
    const tileset = map.addTilesetImage('tileset1', 'tileset')
	
    // create the layers we want in the right order
    map.createLayer('Background', tileset, 0, 0);

  }

  update() {
  }
}


