import { Component, OnInit } from '@angular/core';
import {
  FormGroup,
  FormBuilder,
  FormControl,
  Validators,
} from '@angular/forms';
import { ToastController } from '@ionic/angular';
import { Router } from '@angular/router';

import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-login',
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.scss'],
})
export class LoginComponent implements OnInit {
  validations_form: FormGroup;
  passwordType = 'password';
  passwordIcon = 'eye-outline';
  errormsg: string = '';

  constructor(
    private router: Router,
    private toastController: ToastController,
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
        this.router.navigateByUrl('/auth/userdetail');
      },
      (error) => {
        console.log('login returned with error', error);
        let errmsg = '';
        Object.entries(error.error).forEach(
          ([key, value]) => (errmsg += value + ' ')
        );
        this.presentToast(errmsg, 'danger');
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

  ngOnInit() {}
}
