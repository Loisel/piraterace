import { NgModule } from '@angular/core';
import { RouterModule, Routes, ActivatedRoute } from '@angular/router';
import { GamelistComponent } from './gamelist.component';
import { GameMakerComponent } from './gamemaker.component';

const routes: Routes = [
  {
    path: '',
    component: GamelistComponent,
  },
  {
    path: 'view_gamemaker/:id',
    component: GameMakerComponent,
  }
];

@NgModule({
  imports: [RouterModule.forChild(routes)],
  exports: [RouterModule]
})
export class LobbyRoutingModule {}
