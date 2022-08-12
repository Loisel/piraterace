import { Component } from '@angular/core';
import { MenuController } from '@ionic/angular';
import { StorageService } from './services/storage.service';

@Component({
  selector: 'app-root',
  templateUrl: 'app.component.html',
  styleUrls: ['app.component.scss'],
  providers: [StorageService],
})
export class AppComponent {
  constructor(
    private menu: MenuController,
    private storageService: StorageService // storage service instantiated here in root app to make it comes up as one of the first
  ) {}
}
