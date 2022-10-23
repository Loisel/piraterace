import { Component, OnInit } from '@angular/core';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-userdetail',
  templateUrl: './userdetail.component.html',
  styleUrls: ['./userdetail.component.scss'],
})
export class UserdetailComponent implements OnInit {
  constructor(public authService: AuthService) {
    this.load_userdetails();
  }

  ngOnInit() {}

  load_userdetails() {
    this.authService.updateUserDetail();
  }
}
