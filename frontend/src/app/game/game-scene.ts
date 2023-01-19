import Phaser from 'phaser';

import { environment } from '../../environments/environment';

export class GameScene extends Phaser.Scene {
  updateTimer: Phaser.Time.TimerEvent;
  animationTimer: Phaser.Time.TimerEvent;
  boats: any = {};
  pathHighlights: Phaser.GameObjects.Group;
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
    let GI = this.component.gameinfo;

    this.load.image('tileset', `${environment.STATIC_URL}/maps/${GI.map.tilesets[0].image}`);
    this.load.tilemapTiledJSON('tilemap', `${environment.STATIC_URL}/maps/${GI.mapfile}`);
    this.load.spritesheet('boat', `${environment.STATIC_URL}/sprites/boat.png`, { frameWidth: 160, frameHeight: 160 });
    Object.entries(GI.CARDS).forEach(([cardid, card]) => {
      this.load.image(card['descr'], `${environment.STATIC_URL}/${card['tile_url']}`);
    });
    this.load.spritesheet('octopus', `../../assets/img/octopus.png`, { frameWidth: 48, frameHeight: 48 });
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
        console.log('Error: Inconsistent boat position in x ! Should be ', player, player['pos_x'], ' in game: ', boat_x);
        valid = false;
      }
      if (boat_y !== player['pos_y']) {
        console.log('Error: Inconsistent boat position in y ! Should be ', player, player['pos_y'], ' in game: ', boat_y);
        valid = false;
      }
    });
    console.log('check_player_state: ', valid);
  }

  reset_health_bar() {
    let GI = this.component.gameinfo;
    Object.entries(GI.players).forEach(([playerid, player]) => {
      this.update_healthbar(+playerid, player['health']);
    });
  }

  update_healthbar(boat_id: number, value: number) {
    let hbar = this.boats[boat_id].getChildren()[2];
    console.log('Health value ', value);
    let frac = value / this.component.gameinfo.initial_health;
    console.log('Health frac ', frac);
    this.setHealthBar(hbar, frac);
  }

  getTileX(tileidx: number): number {
    return +this.component.gameinfo.map.tilewidth * (tileidx + 0.5);
  }
  getTileY(tileidx: number): number {
    return +this.component.gameinfo.map.tileheight * (tileidx + 0.5);
  }

  play_actionstack(animation_time_ms: number) {
    let GI = this.component.gameinfo;
    let actionstack = this.component.gameinfo.actionstack;

    console.log('this.last_played_action', this.last_played_action, actionstack.length);

    if (this.component.gameinfo.actionstack.length <= this.last_played_action) {
      return;
    }

    // let tm = new Phaser.Tweens.TweenManager(this);
    console.log('Animation time:', animation_time_ms);
    let timeline = this.tweens.createTimeline({
      duration: animation_time_ms,
      onComplete: function () {
        this.drawCheckpoints();
        this.check_player_state();
        this.reset_health_bar();
        this.component.highlightedCardSlot = -1;
        this.updateBoatFrames();
      },
      callbackScope: this,
    });
    for (let i = this.last_played_action; i < actionstack.length; i++) {
      let offset = (i - this.last_played_action) * animation_time_ms;
      let action_grp = actionstack[i];
      for (let action of action_grp) {
        console.log('Action:', action);
        this.timeline_add_rotate(timeline, action, animation_time_ms, offset);
        this.timeline_add_move_x(timeline, action, animation_time_ms, offset);
        this.timeline_add_move_y(timeline, action, animation_time_ms, offset);
        this.timeline_add_collision_x(timeline, action, animation_time_ms, offset);
        this.timeline_add_collision_y(timeline, action, animation_time_ms, offset);
        this.timeline_add_shot(timeline, action, animation_time_ms, offset);
        this.timeline_add_death(timeline, action, animation_time_ms, offset);
        this.timeline_add_respawn(timeline, action, animation_time_ms, offset);
        this.timeline_add_repair(timeline, action, animation_time_ms, offset);
        this.timeline_add_card_is_played(timeline, action, animation_time_ms, offset);
        this.timeline_add_powerdownrepair(timeline, action, animation_time_ms, offset);
        this.timeline_add_win(timeline, action, animation_time_ms, offset);
      }
    }

    console.log('Timeline: ', timeline);
    timeline.play();
    this.last_played_action = actionstack.length;
  }

  timeline_add_rotate(timeline, action, animation_time_ms, offset) {
    if (action.key === 'rotate') {
      let boatGroup = this.boats[action.target].getChildren();
      // boat.angle += 90 * action.val;
      let targetAngle = action.to * 90;
      if (action.from == 0 && action.to == 3) {
        targetAngle = -90;
      }
      if (action.from == 3 && action.to == 0) {
        targetAngle = 360;
      }
      if (animation_time_ms < 100) {
        boatGroup[0].setAngle(targetAngle);
      } else {
        timeline.add({
          targets: boatGroup,
          duration: animation_time_ms,
          angle: {
            from: action.from * 90,
            to: targetAngle,
          },
          offset: offset,
        });
      }
    }
  }

  timeline_add_move_x(timeline, action, animation_time_ms, offset) {
    if (action.key === 'move_x') {
      let GI = this.component.gameinfo;
      let boatGroup = this.boats[action.target];
      let targetX = this.getTileX(action.to);
      if (animation_time_ms < 100) {
        boatGroup.setX(targetX);
      } else {
        timeline.add({
          targets: boatGroup.getChildren(),
          duration: animation_time_ms,
          x: {
            from: (action.from + 0.5) * GI.map.tilewidth,
            to: targetX,
          },
          offset: offset,
        });
      }
    }
  }

  timeline_add_move_y(timeline, action, animation_time_ms, offset) {
    if (action.key === 'move_y') {
      let GI = this.component.gameinfo;
      let boatGroup = this.boats[action.target];
      let targetY = this.getTileY(action.to);
      if (animation_time_ms < 100) {
        boatGroup.setY(targetY);
      } else {
        timeline.add({
          targets: boatGroup.getChildren(),
          duration: animation_time_ms,
          y: {
            from: (action.from + 0.5) * GI.map.tileheight,
            to: targetY,
          },
          offset: offset,
        });
      }
    }
  }

  timeline_add_collision_x(timeline, action, animation_time_ms, offset) {
    if (action.key === 'collision_x' && animation_time_ms >= 100) {
      let GI = this.component.gameinfo;
      let wiggle_delta_x = GI.map.tilewidth * 0.1;
      let nWiggles = 4;
      let boatGroup = this.boats[action.target].getChildren();

      timeline.add({
        targets: boatGroup,
        x: function (target, key, value) {
          return value + action.val * wiggle_delta_x;
        },
        offset: offset,
        duration: animation_time_ms / (nWiggles * 2),
        yoyo: true,
        repeat: nWiggles,
        callbackScope: this,
        onComplete: function () {
          this.update_healthbar(action.target, action.health);
        },
      });
    }
  }

  timeline_add_collision_y(timeline, action, animation_time_ms, offset) {
    if (action.key === 'collision_y' && animation_time_ms >= 100) {
      let GI = this.component.gameinfo;
      let boatGroup = this.boats[action.target].getChildren();
      let wiggle_delta_y = GI.map.tileheight * 0.1;
      let nWiggles = 4;
      timeline.add({
        targets: boatGroup,
        y: function (target, key, value) {
          return value + action.val * wiggle_delta_y;
        },
        duration: animation_time_ms / (nWiggles * 2),
        repeat: nWiggles,
        offset: offset,
        yoyo: true,
        onComplete: function () {
          this.update_healthbar(action.target, action.health);
        },
        callbackScope: this,
      });
    }
  }

  timeline_add_shot(timeline, action, animation_time_ms, offset) {
    if (action.key === 'shot' && animation_time_ms >= 100) {
      let GI = this.component.gameinfo;
      let cannonball = this.add.circle((action.src_x + 0.5) * GI.map.tilewidth, (action.src_y + 0.5) * GI.map.tilewidth, 7, 0);
      cannonball.setVisible(false);
      timeline.add({
        targets: cannonball,
        x: (action.collided_at[0] + 0.5) * GI.map.tilewidth,
        y: (action.collided_at[1] + 0.5) * GI.map.tilewidth,
        callbackScope: this,
        onStart: function (tween, target) {
          cannonball.setVisible(true);
        },
        onComplete: function (tween, target) {
          cannonball.destroy();
          if (action.other_player !== undefined) {
            this.update_healthbar(action.other_player, action.other_player_health);
          }
        },
        duration: (animation_time_ms * 2) / 3,
        offset: offset,
      });
      if (action.other_player !== undefined) {
        timeline.add(
          this.showStars(
            this.getTileX(action.collided_at[0]),
            this.getTileY(action.collided_at[1]),
            0xff0000,
            animation_time_ms / 3,
            offset + (animation_time_ms * 2) / 3
          )
        );
      }
    }
  }

  timeline_add_death(timeline, action, animation_time_ms, offset) {
    if (action.key === 'death' && animation_time_ms >= 100) {
      let boatGroup = this.boats[action.target].getChildren();
      if (action.type === 'void') {
        timeline.add({
          targets: boatGroup,
          scale: '-=.5',
          angle: '+=360',
          offset: offset,
          duration: animation_time_ms,
        });
      } else if (action.type === 'collision') {
        timeline.add({
          targets: boatGroup,
          scale: '-=.5',
          offset: offset,
          duration: animation_time_ms,
        });
      } else if (action.type === 'cannon') {
        timeline.add({
          targets: boatGroup,
          scale: '-=.5',
          offset: offset,
          duration: animation_time_ms,
        });
      } else {
        console.log('unknown type of death: ', action.type);
      }
    }
  }

  timeline_add_respawn(timeline, action, animation_time_ms, offset) {
    if (action.key === 'respawn') {
      let boatGroup = this.boats[action.target];
      if (animation_time_ms < 100) {
        boatGroup.setXY(this.getTileX(action.posx), this.getTileY(action.posy));
        let pboat = boatGroup.getChildren()[0];
        pboat.setAngle(90 * action['direction']);
      } else {
        timeline.add({
          targets: boatGroup.getChildren(),
          scale: '+=.5',
          offset: offset,
          duration: animation_time_ms,
          onStart: function () {
            let boatGroup = this.boats[action.target];
            boatGroup.setXY(this.getTileX(action.posx), this.getTileY(action.posy));
            let pboat = boatGroup.getChildren()[0];
            pboat.setAngle(90 * action['direction']);
          },
          onComplete: function () {
            this.update_healthbar(action.target, action.health);
          },
          callbackScope: this,
        });
      }
    }
  }

  timeline_add_repair(timeline, action, animation_time_ms, offset) {
    if (action.key === 'repair' && animation_time_ms >= 100) {
      let boatGroup = this.boats[action.target].getChildren();
      timeline.add(this.showStars(this.getTileX(action.posx), this.getTileY(action.posy), 0x00ff00, animation_time_ms, offset));

      timeline.add({
        targets: boatGroup,
        offset: offset,
        duration: animation_time_ms,
        onComplete: function () {
          this.update_healthbar(action.target, action.health);
        },
        callbackScope: this,
      });
    }
  }

  timeline_add_card_is_played(timeline, action, animation_time_ms, offset) {
    if (action.key === 'card_is_played' && animation_time_ms >= 100) {
      {
        // show played card on top of a boat
        let GI = this.component.gameinfo;
        let cardsprite = this.add.sprite(0, 0, action.card.descr);
        cardsprite.displayWidth = GI.map.tilewidth;
        cardsprite.displayHeight = GI.map.tileheight;
        cardsprite.alpha = 0;
        timeline.add({
          targets: cardsprite,
          offset: offset,
          duration: animation_time_ms * 0.5,
          alpha: 0.5,
          callbackScope: this,
          onStart: function () {
            let boatGroup = this.boats[action.target].getChildren();
            let boat = boatGroup[0];

            cardsprite.x = boat.x;
            cardsprite.y = boat.y;
            cardsprite.angle = boat.angle;
          },
        });
        timeline.add({
          targets: cardsprite,
          offset: offset + animation_time_ms * 0.5,
          duration: animation_time_ms * 0.5,
          alpha: 0,
          callbackScope: this,
          onComplete: function () {
            cardsprite.destroy(true);
          },
        });
      }

      if (action.target === this.component.gameinfo.me) {
        let boatGroup = this.boats[action.target].getChildren();
        timeline.add({
          targets: boatGroup,
          offset: offset,
          duration: animation_time_ms,
          onComplete: function () {
            this.component.highlightedCardSlot = action.cardslot;
          },
          callbackScope: this,
        });
      }
    }
  }

  timeline_add_powerdownrepair(timeline, action, animation_time_ms, offset) {
    if (action.key === 'powerdownrepair' && animation_time_ms >= 100) {
      let boatGroup = this.boats[action.target].getChildren();
      timeline.add({
        targets: boatGroup,
        offset: offset,
        duration: 0,
        onComplete: function () {
          this.update_healthbar(action.target, action.health);
          this.boats[action.target].getChildren()[0].setFrame(1);
        },
        callbackScope: this,
      });
    }
  }

  timeline_add_win(timeline, action, animation_time_ms, offset) {
    if (action.key === 'win') {
      let boatGroup = this.boats[action.target].getChildren();
      timeline.add({
        targets: boatGroup,
        offset: offset,
        duration: 0,
        onComplete: function () {
          this.updateTimer.paused = true;
          this.component.presentSummary();
        },
        callbackScope: this,
      });
    }
  }

  showStars(x, y, color, duration, offset) {
    let stars = this.add.group();
    stars.add(this.add.star(x - 2, y + 6, 5, 6, 11, color));
    stars.add(this.add.star(x - 5, y - 11, 5, 8, 13, color));
    stars.setVisible(false);
    return {
      targets: stars,
      offset: offset,
      y: '+= GI.map.tileheight/2',
      onStart: function (tween, target) {
        stars.setVisible(true);
      },
      onComplete: function (tween, target) {
        stars.clear(true, true);
      },
      callbackScope: this,
      duration: duration,
    };
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
      let num = this.add.text((pos[0] + 0.5) * GI.map.tilewidth, (pos[1] + 0.5) * GI.map.tileheight, name, {
        fontSize: '30px',
        strokeThickness: 5,
        stroke: color,
        color: color,
      });
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

  makeHealthBar(x, y) {
    let cfg = this.getHealthBarConfig();

    let bgbar = this.add.graphics({ x: x, y: y });
    //  BG
    bgbar.fillStyle(0x000000);
    bgbar.fillRect(cfg.xoffset, cfg.yoffset, cfg.width, cfg.height);

    bgbar.fillStyle(0xffffff);
    bgbar.fillRect(cfg.xoffset + 2, cfg.yoffset + 2, cfg.width - 4, cfg.height - 2);

    //  Health
    let hbar = this.add.graphics({ x: x, y: y });
    hbar.fillStyle(0x00ff00);
    hbar.fillRect(cfg.xoffset + 2, cfg.yoffset + 2, cfg.width - 4, cfg.height - 2);

    return [hbar, bgbar];
  }

  getHealthBarConfig() {
    let GI = this.component.gameinfo;
    return {
      xoffset: -GI.map.tilewidth * 0.4,
      yoffset: GI.map.tileheight * 0.3,
      width: GI.map.tilewidth * 0.8,
      height: GI.map.tileheight * 0.12,
    };
  }

  setHealthBar(hbar, value) {
    let cfg = this.getHealthBarConfig();
    console.log('set health value:', value);
    hbar.clear();
    if (value <= 0.3) {
      hbar.fillStyle(0xff0000);
    } else if (value <= 0.6) {
      hbar.fillStyle(0xffe900);
    } else {
      hbar.fillStyle(0x00ff00);
    }
    hbar.fillRect(cfg.xoffset + 2, cfg.yoffset + 2, value * (cfg.width - 4), cfg.height - 2);
  }

  drawBoat(player, playerid) {
    let GI = this.component.gameinfo;
    let color = Phaser.Display.Color.HexStringToColor(player['color']);
    let backdrop = this.add.rectangle(
      this.getTileX(player['start_pos_x']),
      this.getTileY(player['start_pos_y']),
      GI.map.tilewidth,
      GI.map.tileheight,
      color.color,
      0.5
    );
    if (playerid == GI.me) {
      backdrop.setStrokeStyle(5, color.color);
    }

    var boat = this.add.sprite(this.getTileX(player['start_pos_x']), this.getTileY(player['start_pos_y']), 'boat');
    boat.setFrame(0);

    //set the width of the sprite
    boat.displayHeight = GI.map.tileheight * 1.1;
    //scale evenly
    boat.scaleX = boat.scaleY;
    boat.angle = player['start_direction'] * 90;

    boat.setInteractive({ useHandCursor: true });
    boat.on(
      'pointerdown',
      function (playerid, pointer) {
        let boat = this.boats[playerid].getChildren()[0];
        let player = this.component.gameinfo.players[playerid];
        let text = this.add
          .text(boat.x, boat.y, player['name'] + ' \u2794 ' + player['next_checkpoint'], {
            fontFamily: 'Arial',
            color: '#ffffff',
            fontSize: 24,
            backgroundColor: player['color'],
          })
          .setOrigin(0.5, 0.5);
        this.tweens.add({
          targets: text,
          alpha: 0,
          duration: 2000,
        });
      }.bind(this, playerid)
    );

    let hList = this.makeHealthBar(this.getTileX(player['start_pos_x']), this.getTileY(player['start_pos_y']));

    let group = this.add.group();
    group.add(boat);
    group.add(backdrop);
    group.add(hList[0]);
    group.add(hList[1]);
    return group;
  }

  updateBoatFrames() {
    let GI = this.component.gameinfo;
    for (let playerid in GI.players) {
      let boat = this.boats[playerid].getChildren()[0];
      let player = GI.players[playerid];
      if (player.is_zombie) {
        boat.setFrame(2);
      } else if (player.powered_down) {
        boat.setFrame(1);
      } else {
        boat.setFrame(0);
      }
    }
  }

  updateEvent(): void {
    this.component.load_gameinfo().subscribe((gameinfo) => {
      console.log('GameInfo ', gameinfo);
      this.component.gameinfo = gameinfo;
      this.component.Ngameround.next(gameinfo['Ngameround']);

      this.play_actionstack(gameinfo['time_per_action'] * 900);

      if (gameinfo.countdown) {
        if (this.component.countDownValue < 0) {
          this.component.setupCountDown(gameinfo.countdown_duration - gameinfo.countdown, gameinfo.countdown_duration);
        }
      }
    });
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
    this.animateOctopus();

    this.drawGrid();
    this.drawCheckpoints();

    Object.entries(GI.players).forEach(([playerid, player]) => {
      this.boats[playerid] = this.drawBoat(player, playerid);
    });
    this.updateBoatFrames();
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

    this.play_actionstack(0); // play the first action stack really quickly in case user does a reload

    this.updateTimer = this.time.addEvent({
      callback: this.updateEvent,
      callbackScope: this,
      delay: 1000, // 1000 = 1 second
      loop: true,
    });

    // enable zooming in and out of phaser map
    this.input.on('wheel', (pointer, gameObjects, deltaX, deltaY, deltaZ) => {
      if (deltaY > 0) {
        if (cam.zoom >= 0.3) {
          cam.zoom -= 0.1;
        }
      }
      if (deltaY < 0) {
        if (cam.zoom < 3) {
          cam.zoom += 0.1;
        }
      }
    });

    this.pathHighlights = this.add.group();
    this.component.cardsinfo.subscribe((cardsinfo) => {
      this.pathHighlighting();
    });
  }

  animateOctopus() {
    this.anims.create({
      key: 'octopus_animation',
      frames: 'octopus',
      frameRate: 5,
      repeat: -1,
    });

    let anim = this.anims.get('octopus_animation');

    let voids = this.component.gameinfo.map['property_locations']['void'];
    if (voids !== undefined) {
      for (let v of voids) {
        this.add.sprite(this.getTileX(+v[0]), this.getTileY(+v[1]), 'octopus').play({
          key: 'octopus_animation',
          startFrame: Phaser.Math.RND.between(0, anim.getTotalFrames() - 1),
        });
      }
    }
  }

  pathHighlighting() {
    if (!this.component.gameinfo.path_highlighting) {
      return;
    }
    this.component.loadPathHighlighting().subscribe(
      (path) => {
        this.pathHighlights.clear(true, true);
        let GI = this.component.gameinfo;
        let player = GI.players[GI.me];
        let color = Phaser.Display.Color.HexStringToColor(player['color']);
        path.forEach(([x, y]) => {
          let backdrop = this.add.rectangle(
            this.getTileX(x),
            this.getTileY(y),
            GI.map.tilewidth,
            GI.map.tileheight,
            color.color,
            0.5
          );
          this.pathHighlights.add(backdrop);
        });
      },
      (error) => {
        console.log('Error: ', error);
        this.component.presentToast(error.error, 'danger');
      }
    );
  }
}
