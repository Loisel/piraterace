import { NgModule } from '@angular/core';
import { RouterModule, Routes, ActivatedRoute } from '@angular/router';
import { GamelistComponent } from './gamelist/gamelist.component';
import { GameConfigComponent } from './gameconfig/gameconfig.component';
import { NewGameConfigComponent } from './newgameconfig/newgameconfig.component';

const routes: Routes = [
  {
    path: '',
    component: GamelistComponent,
  },
  {
    path: 'newgameconfig',
    component: NewGameConfigComponent,
  },
  {
    path: 'view_gameconfig/:id',
    component: GameConfigComponent,
  },
];

@NgModule({
  imports: [RouterModule.forChild(routes)],
  exports: [RouterModule],
})
export class LobbyRoutingModule {}
