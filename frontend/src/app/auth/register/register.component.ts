import { Component, OnInit } from '@angular/core';
import { ToastController } from '@ionic/angular';
import {
  FormGroup,
  FormBuilder,
  FormControl,
  Validators,
} from '@angular/forms';
import { Router } from '@angular/router';

import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-register',
  templateUrl: './register.component.html',
  styleUrls: ['./register.component.scss'],
})
export class RegisterComponent implements OnInit {
  title = 'Angular Form Validation Tutorial';
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

  async ngOnInit() {}

  createForm() {
    this.validations_form = this.formBuilder.group({
      username: new FormControl('', Validators.compose([Validators.required])),
      email: new FormControl(
        '',
        Validators.compose([
          Validators.required,
          Validators.pattern('^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+.[a-zA-Z0-9-.]+$'),
        ])
      ),
      password: new FormControl(
        '',
        Validators.compose([Validators.minLength(8), Validators.required])
      ),
      confirmpassword: new FormControl(
        '',
        Validators.compose([Validators.minLength(8), Validators.required])
      ),
    });
  }

  showPassword() {
    this.passwordType = 'text';
  }

  async onSubmit(values) {
    this.authService
      .registerUser(values['username'], values['password'], values['email'])
      .subscribe(
        (ret) => {
          console.log('register return', ret);
          this.presentToast('User registered', 'success');
          this.authService.login(ret['username'], values['password']);
          this.router.navigateByUrl('/auth/userdetail');
        },
        (error) => {
          console.log('register returned with error', error);
          let errmsg = 'Error registering user!\n';
          Object.entries(error.error).forEach(
            ([key, value]) => (errmsg += '* ' + key + ' : ' + value + '\n')
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
}
