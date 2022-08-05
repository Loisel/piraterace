//import { Component } from '@angular/core';
//
//@Component({
//  selector: 'app-home',
//  templateUrl: 'home.page.html',
//  styleUrls: ['home.page.scss'],
//})
//export class HomePage {
//
//  constructor() {}
//
//}

import { Component, OnInit } from '@angular/core';
import Phaser from 'phaser';

class GameScene extends Phaser.Scene {
  constructor(config) {
    super(config);
  }

  preload() {
    this.add.text(0.5, 0.5, 'Huhu');
  }

  create() {}

  update() {}
}

@Component({
  selector: 'app-home',
  templateUrl: 'home.page.html',
  styleUrls: ['home.page.scss'],
})
export class HomePage implements OnInit {
  phaserGame: Phaser.Game;
  config: Phaser.Types.Core.GameConfig;

  constructor() {
    this.config = {
      type: Phaser.AUTO,
      width: 800,
      height: 600,
      physics: {},
      parent: 'game',
      scene: GameScene,
    };
  }

  ngOnInit(): void {
    this.phaserGame = new Phaser.Game(this.config);
  }
}
