import { Component, OnInit } from '@angular/core';
import {
  FormGroup,
  FormBuilder,
  FormControl,
  Validators,
} from '@angular/forms';

import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-login',
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.scss'],
  providers: [AuthService],
})
export class LoginComponent implements OnInit {
  validations_form: FormGroup;
  passwordType = 'password';
  passwordIcon = 'eye-outline';
  errormsg: string = '';

  constructor(
    private formBuilder: FormBuilder,
    private authService: AuthService
  ) {
    this.createForm();
  }

  createForm() {
    this.validations_form = this.formBuilder.group({
      username: new FormControl('', Validators.compose([Validators.required])),
      password: new FormControl(''),
    });
  }

  showPassword() {
    this.passwordType = 'text';
  }

  onSubmit(values) {
    this.authService.login(values['username'], values['password']).subscribe(
      (ret) => {
        console.log('login return', ret);
      },
      (error) => {
        console.log('login returned with error', error);
      }
    );
  }

  ngOnInit() {}
}
