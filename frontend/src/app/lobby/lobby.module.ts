import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { GamelistComponent } from './gamelist.component';
import { GameMakerComponent } from './gamemaker.component';
import { IonicModule } from '@ionic/angular';

import { LobbyRoutingModule } from './lobby-routing.module';

@NgModule({
  declarations: [GamelistComponent, GameMakerComponent],
  imports: [
    CommonModule,
    IonicModule,
    LobbyRoutingModule
  ]
})
export class LobbyModule { }
