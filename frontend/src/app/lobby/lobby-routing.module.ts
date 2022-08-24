import { NgModule } from '@angular/core';
import { RouterModule, Routes, ActivatedRoute } from '@angular/router';
import { GamelistComponent } from './gamelist/gamelist.component';
import { GameMakerComponent } from './gamemaker/gamemaker.component';
import { NewGameMakerComponent } from './newgamemaker/newgamemaker.component';

const routes: Routes = [
  {
    path: '',
    component: GamelistComponent,
  },
  {
    path: 'newgamemaker',
    component: NewGameMakerComponent,
  },
  {
    path: 'view_gamemaker/:id',
    component: GameMakerComponent,
  },
];

@NgModule({
  imports: [RouterModule.forChild(routes)],
  exports: [RouterModule],
})
export class LobbyRoutingModule {}
