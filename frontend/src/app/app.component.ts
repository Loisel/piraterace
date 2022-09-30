import { Component } from '@angular/core';
import { MenuController } from '@ionic/angular';
import { StorageService } from './services/storage.service';
import { AuthService } from './services/auth.service';

@Component({
  selector: 'app-root',
  templateUrl: 'app.component.html',
  styleUrls: ['app.component.scss'],
})
export class AppComponent {
  constructor(private menu: MenuController, public authService: AuthService) {}

  ngOnInit() {}
}
