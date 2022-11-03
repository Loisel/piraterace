import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { GamelistComponent } from './gamelist/gamelist.component';
import { GameConfigComponent } from './gameconfig/gameconfig.component';
import { NewGameConfigComponent } from './newgameconfig/newgameconfig.component';
import { IonicModule } from '@ionic/angular';
import { FormsModule } from '@angular/forms';

import { LobbyRoutingModule } from './lobby-routing.module';

@NgModule({
  declarations: [GamelistComponent, GameConfigComponent, NewGameConfigComponent],
  imports: [CommonModule, IonicModule, LobbyRoutingModule, FormsModule],
})
export class LobbyModule {}
