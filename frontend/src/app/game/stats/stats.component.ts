import { Component, OnInit, Input } from '@angular/core';

import { GameInfo } from '../../model/gameinfo';

@Component({
  selector: 'app-stats',
  templateUrl: './stats.component.html',
  styleUrls: ['./stats.component.scss'],
})
export class StatsComponent implements OnInit {
  @Input() gameinfo!: GameInfo;
  constructor() {}

  ngOnInit() {
    console.log('Stats Component!', this.gameinfo);
  }

  getMinMaxStat(fieldname: string) {
    let arr = this.gameinfo.stats[fieldname].map((el) => +el[1]);
    return { min: Math.min.apply(Math, arr), max: Math.max.apply(Math, arr) };
  }
}
