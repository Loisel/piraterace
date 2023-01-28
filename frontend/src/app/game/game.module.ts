import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IonicModule } from '@ionic/angular';
import { FormsModule } from '@angular/forms';
import { AppModule } from '../app.module';
import { GameComponent } from './game.component';
import { StatsComponent } from './stats/stats.component';
import { GameRoutingModule } from './game-routing.module';
import { ChatboxModule } from '../chatbox/chatbox.module';

@NgModule({
  imports: [CommonModule, FormsModule, IonicModule, GameRoutingModule, ChatboxModule],
  declarations: [GameComponent, StatsComponent],
})
export class GameModule {}
