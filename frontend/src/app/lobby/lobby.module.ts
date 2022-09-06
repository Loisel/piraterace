import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { GamelistComponent } from './gamelist/gamelist.component';
import { GameMakerComponent } from './gamemaker/gamemaker.component';
import { NewGameMakerComponent } from './newgamemaker/newgamemaker.component';
import { IonicModule } from '@ionic/angular';
import { FormsModule } from '@angular/forms';

import { LobbyRoutingModule } from './lobby-routing.module';

@NgModule({
  declarations: [GamelistComponent, GameMakerComponent, NewGameMakerComponent],
  imports: [CommonModule, IonicModule, LobbyRoutingModule, FormsModule],
})
export class LobbyModule {}
