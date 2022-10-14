import { BehaviorSubject } from 'rxjs';
import { Injectable } from '@angular/core';

@Injectable()
export class NavService {
  private showLeaveGame: BehaviorSubject<boolean>;

  constructor() {
    this.showLeaveGame = new BehaviorSubject(false);
  }

  getShowLeaveGame() {
    return this.showLeaveGame;
  }

  setShowLeaveGame(bool) {
    this.showLeaveGame.next(bool);
  }
}
