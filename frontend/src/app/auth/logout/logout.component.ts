import { Component, OnInit } from '@angular/core';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-logout',
  templateUrl: './logout.component.html',
  styleUrls: ['./logout.component.scss'],
})
export class LogoutComponent implements OnInit {
  userdetail: any = null;

  constructor(private authService: AuthService) {}

  ngOnInit() {}

  logout() {
    this.authService.logout();
  }
}
