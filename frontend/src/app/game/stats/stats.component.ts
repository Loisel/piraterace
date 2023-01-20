import { Component, OnInit, Input } from '@angular/core';

import { GameInfo } from '../../model/gameinfo';

@Component({
  selector: 'app-stats',
  templateUrl: './stats.component.html',
  styleUrls: ['./stats.component.scss'],
})
export class StatsComponent implements OnInit {
  @Input() gameinfo!: GameInfo;
  statsfields: string[] = [
    'checkpoints',
    'move_count',
    'rotation_count',
    'death_count',
    'cannondeath_count',
    'void_count',
    'repair_count',
    'powerdown_count',
  ];
  TOTAL_TIME: number = 1000;
  stats: any = {};
  constructor() {}

  ngOnInit() {
    this.createEmptyTable();

    for (let i = 0; i < this.statsfields.length; i++) {
      setTimeout(() => {
        this.countStatsUp(this.statsfields[i]);
      }, this.TOTAL_TIME * i);
    }
  }

  createEmptyTable() {
    this.stats = JSON.parse(JSON.stringify(this.gameinfo.stats));

    for (let fname of this.statsfields) {
      this.stats[fname] = this.stats[fname].map((stat) => (stat = null));
    }
  }

  countStatsUp(fieldname: string) {
    const NCOUNTS = 10;
    let interval = setInterval(() => {
      let allReady = true;
      let minmax = this.getMinMaxStat(fieldname);
      let delta = minmax.max / NCOUNTS + 1e-6;
      for (let i = 0; i < this.stats[fieldname].length; i++) {
        let current = this.stats[fieldname][i];
        let target = this.gameinfo.stats[fieldname][i];

        if (current < target || current == null) {
          allReady = false;
          this.stats[fieldname][i] = Math.min(target, Math.ceil(current + delta));
        }
      }
      if (allReady) {
        clearInterval(interval);
      }
    }, this.TOTAL_TIME / NCOUNTS);
  }

  getMinMaxStat(fieldname: string) {
    let arr = this.gameinfo.stats[fieldname].map((el) => +el);
    return { min: Math.min.apply(Math, arr), max: Math.max.apply(Math, arr) };
  }
}
