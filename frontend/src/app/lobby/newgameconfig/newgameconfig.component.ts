import { Component, OnInit, OnDestroy } from '@angular/core';
import { Router, ActivatedRoute } from '@angular/router';
import Phaser from 'phaser';
import { ToastController } from '@ionic/angular';

import { HttpService } from '../../services/http.service';
import { NewGameConfig } from '../../model/newgameconfig';
import { environment } from '../../../environments/environment';

@Component({
  selector: 'app-newgameconfig',
  templateUrl: './newgameconfig.component.html',
  styleUrls: ['./newgameconfig.component.scss'],
})
export class NewGameConfigComponent {
  data: NewGameConfig = null;

  constructor(
    private httpService: HttpService,
    private router: Router,
    private route: ActivatedRoute,
    private toastController: ToastController
  ) {}

  ionViewWillEnter() {
    this.httpService.get_create_new_gameConfig().subscribe((response) => {
      console.log('Get get_create_new_gameConfig', response);
      this.data = response;
    });
  }

  ionViewWillLeave() {}

  selectMapChange(e) {
    // monitoring changes in the maps dropdown
    console.log('selectMapChange', e);
    this.data.selected_map = e.target.value;

    this.httpService.post_create_new_gameConfig(this.data).subscribe((response) => {
      console.log('post post_create_new_gameConfig', response);
      this.data = response;
    });
  }

  createGameConfig(event) {
    // create a GameConfig
    console.log('Create a gameConfig');
    this.httpService.createGameConfig(this.data).subscribe(
      (gameConfig) => {
        console.log('New GameConfig response:', gameConfig);
        this.router.navigate(['../view_gameconfig', gameConfig.id], {
          relativeTo: this.route,
        });
      },
      (err) => {
        console.log(err);
        this.presentToast(err.error, 'danger');
      }
    );
  }

  async presentToast(msg, color = 'primary') {
    const toast = await this.toastController.create({
      message: msg,
      color: color,
      duration: 5000,
    });
    toast.present();
  }
}
