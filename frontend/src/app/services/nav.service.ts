import { BehaviorSubject } from 'rxjs';
import { Injectable } from '@angular/core';

@Injectable()
export class NavService {
  public showLeaveGame: BehaviorSubject<boolean> = new BehaviorSubject<boolean>(
    false
  );

  setShowLeaveGame(state: boolean) {
    this.showLeaveGame.next(state);
  }
}
