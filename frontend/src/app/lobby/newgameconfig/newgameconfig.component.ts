import { Component } from '@angular/core';
import { Router, ActivatedRoute } from '@angular/router';
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
    this.data.selected_map = e.target.value.filename;

    // Only send the fields the backend actually reads (create_new_gameconfig
    // recomputes available_maps/map_info from disk itself). Echoing the full
    // `this.data` blob back — including available_maps, which embeds every
    // map's full tileset — made this POST multi-megabyte and prone to
    // tripping nginx's client_max_body_size as more maps get added.
    const payload = { selected_map: this.data.selected_map, gamename: this.data.gamename };
    this.httpService.post_create_new_gameConfig(payload).subscribe((response) => {
      console.log('post post_create_new_gameConfig', response);
      this.data = response;
    });
  }

  createGameConfig(event) {
    // create a GameConfig
    console.log('Create a gameConfig');
    const payload = {
      selected_map: this.data.selected_map,
      gamename: this.data.gamename,
      Nmaxplayers: this.data.Nmaxplayers,
    };
    this.httpService.createGameConfig(payload).subscribe(
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

  getMapProperty(mapinfo, key) {
    if (mapinfo === null) return '';
    if (mapinfo.properties !== undefined) {
      for (let p of mapinfo.properties) {
        if (p['name'] == key) {
          return p['value'];
        }
      }
    }
    if (key == 'mapname') {
      return mapinfo.filename.replace('.json', '');
    }
    return null;
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
