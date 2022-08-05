import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IonicModule } from '@ionic/angular';
import { FormsModule } from '@angular/forms';
import { GameComponent } from './game.component';
import { GameRoutingModule } from './game-routing.module';

@NgModule({
  imports: [CommonModule, FormsModule, IonicModule, GameRoutingModule],
  declarations: [GameComponent],
})
export class GameModule {}
