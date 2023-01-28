import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AppModule } from '../app.module';
import { GamelistComponent } from './gamelist/gamelist.component';
import { GameConfigComponent } from './gameconfig/gameconfig.component';
import { PhaserPreviewComponent } from './phaserpreview/phaserpreview.component';
import { NewGameConfigComponent } from './newgameconfig/newgameconfig.component';
import { IonicModule } from '@ionic/angular';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { ChatboxModule } from '../chatbox/chatbox.module';
import { LobbyRoutingModule } from './lobby-routing.module';

@NgModule({
  declarations: [GamelistComponent, GameConfigComponent, NewGameConfigComponent, PhaserPreviewComponent],
  imports: [CommonModule, IonicModule, LobbyRoutingModule, FormsModule, ReactiveFormsModule, ChatboxModule],
  exports: [PhaserPreviewComponent],
})
export class LobbyModule {}
