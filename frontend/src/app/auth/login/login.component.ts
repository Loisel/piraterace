import { Component, OnInit } from '@angular/core';
import { FormGroup, FormBuilder, FormControl, Validators } from '@angular/forms';
import { ToastController } from '@ionic/angular';
import { ActivatedRoute, Router } from '@angular/router';

import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-login',
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.scss'],
})
export class LoginComponent implements OnInit {
  anonymousName: string = null;

  validations_form: FormGroup;
  passwordType = 'password';
  passwordIcon = 'eye-outline';
  errormsg: string = '';
  nextURL: string;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private toastController: ToastController,
    private formBuilder: FormBuilder,
    private authService: AuthService
  ) {
    this.createForm();
    this.nextURL = this.route.snapshot.queryParams['nextURL'] || '/';
    console.log('this.nextURL', this.nextURL);
  }

  ionViewWillEnter() {
    this.updateAnonymousName();
  }

  updateAnonymousName() {
    this.authService.getRandomName().subscribe((ret) => {
      this.anonymousName = ret['name'];
    });
  }

  loginAnonymous() {
    let password = this.genPassword(20, true, true, true);
    let email = this.anonymousName.replace(/\s/g, '') + '@piraterace.com';
    console.log('password', password);
    this.authService.registerUser(this.anonymousName, password, email).subscribe(
      (ret) => {
        console.log('register return', ret);
        this.presentToast('User registered', 'success');
        this.authService.login(ret['username'], password).subscribe(
          (ret) => {
            console.log('login return', ret);
            this.router.navigateByUrl('/lobby');
          },
          (error) => {
            console.log('login returned with error', error);
            let errmsg = '';
            Object.entries(error.error).forEach(([key, value]) => (errmsg += value + ' '));
            this.presentToast(errmsg, 'danger');
          }
        );
        this.router.navigateByUrl('/');
      },
      (error) => {
        console.log('register returned with error', error);
        let errmsg = 'Error registering user!\n';
        Object.entries(error.error).forEach(([key, value]) => (errmsg += '* ' + key + ' : ' + value + '\n'));
        this.presentToast(errmsg, 'danger');
      }
    );
  }

  genPassword(length, useUpper, useNumbers, userSymbols) {
    var passwordLength = length || 12;
    var addUpper = useUpper || true;
    var addNumbers = useNumbers || true;
    var addSymbols = userSymbols || true;

    var lowerCharacters = [
      'a',
      'b',
      'c',
      'd',
      'e',
      'f',
      'g',
      'h',
      'i',
      'j',
      'k',
      'l',
      'm',
      'n',
      'o',
      'p',
      'q',
      'r',
      's',
      't',
      'u',
      'v',
      'w',
      'x',
      'y',
      'z',
    ];
    var upperCharacters = [
      'A',
      'B',
      'C',
      'D',
      'E',
      'F',
      'G',
      'H',
      'I',
      'J',
      'K',
      'L',
      'M',
      'N',
      'O',
      'P',
      'Q',
      'R',
      'S',
      'T',
      'U',
      'V',
      'W',
      'X',
      'Y',
      'Z',
    ];
    var numbers = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9'];
    var symbols = ['!', '?', '@'];

    var getRandom = function (array) {
      return array[Math.floor(Math.random() * array.length)];
    };

    var finalCharacters = '';

    if (addUpper) {
      finalCharacters = finalCharacters.concat(getRandom(upperCharacters));
    }

    if (addNumbers) {
      finalCharacters = finalCharacters.concat(getRandom(numbers));
    }

    if (addSymbols) {
      finalCharacters = finalCharacters.concat(getRandom(symbols));
    }

    for (var i = 1; i < passwordLength - 3; i++) {
      finalCharacters = finalCharacters.concat(getRandom(lowerCharacters));
    }

    //shuffle!
    return finalCharacters
      .split('')
      .sort(function () {
        return 0.5 - Math.random();
      })
      .join('');
  }

  createForm() {
    this.validations_form = this.formBuilder.group({
      username: new FormControl('', Validators.compose([Validators.required])),
      password: new FormControl(''),
    });
  }

  showPassword() {
    if (this.passwordType === 'password') {
      this.passwordType = 'text';
    } else {
      this.passwordType = 'password';
    }
  }

  onSubmit(values) {
    this.authService.login(values['username'], values['password']).subscribe(
      (ret) => {
        console.log('login return', ret);
        this.router.navigateByUrl(this.nextURL);
      },
      (error) => {
        console.log('login returned with error', error);
        let errmsg = '';
        Object.entries(error.error).forEach(([key, value]) => (errmsg += value + ' '));
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
