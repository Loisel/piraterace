import { Component, OnInit } from '@angular/core';
import { ToastController } from '@ionic/angular';
import {
  FormGroup,
  FormBuilder,
  FormControl,
  Validators,
} from '@angular/forms';

import { HttpService } from '../../services/http.service';

@Component({
  selector: 'app-register',
  templateUrl: './register.component.html',
  styleUrls: ['./register.component.scss'],
  providers: [HttpService],
})
export class RegisterComponent implements OnInit {
  title = 'Angular Form Validation Tutorial';
  validations_form: FormGroup;
  passwordType = 'password';
  passwordIcon = 'eye-outline';
  errormsg: string = '';

  constructor(
    public toastController: ToastController,
    private formBuilder: FormBuilder,
    private httpService: HttpService
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
    let email = values['email'];
    let password = values['password'];
    let confirmpassword = values['confirmpassword'];
    let username = values['username'];

    let params = {
      email: email,
      password: password,
      username: username,
    };
    console.log(params);
    this.httpService.registerUser(username, password, email).subscribe(
      (ret) => {
        console.log('register return', ret);
        this.presentToast('User registered', 'success');
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
  //  createAccount(params) {
  //      this.apiService.registerUser(params).subscribe((resultat) => {
  //        let status = resultat["status"];
  //        if (status=="OK") {
  //          let data = resultat["data"]
  //          this.userManager.setUser(data)
  //            // create a token
  //              // Check email
  //              let paramsToLogin = {
  //                "email": params.email,
  //                "password": params.password,
  //              }
  //              this.authentificationService.login(paramsToLogin).then((resultat) => {
  //                this.apiService.stopLoading();
  //                if (resultat) {
  //                   //Authentified
  //                   this.router.navigateByUrl("/home")
  //                }
  //                else {
  //                  this.apiService.showError(this.translateService.instant("A technical error occured. Account creation impossible"))
  //                }
  //              })
  //        }
  //        else {
  //          this.apiService.stopLoading();
  //          let error = resultat["error"]
  //          if (error.status==400){
  //            this.apiService.showError(this.translateService.instant("An account already exists with this email. Please login !"))
  //          }
  //          else{
  //            this.apiService.showError(this.translateService.instant("A technical error occured. Account creation impossible"))
  //          }
  //
  //        }
  //      })
  //  }
}

//import { Component, OnInit } from '@angular/core';
//import { FormGroup, FormBuilder, FormControl, Validators, AbstractControl, ValidatorFn } from '@angular/forms';
//import { ApiserviceService } from 'src/app/services/apiservice.service';
//import { Platform, AlertController } from '@ionic/angular';
//import { Router } from '@angular/router';
//import { UserManagerProviderService } from 'src/app/services/user-manager-provider.service';
//import { TranslateService } from '@ngx-translate/core';
//import { AuthenticationService } from 'src/app/services/authentication.service';
//@Component({
//  selector: 'app-register',
//  templateUrl: './register.page.html',
//  styleUrls: ['./register.page.scss'],
//})
//export class RegisterPage implements OnInit {
//  validations_form: FormGroup;
//  isIOS: boolean = false;
//  passwordType = "password"
//  passwordIcon = "eye-outline"
//  constructor(public apiService: ApiserviceService,
//    public formBuilder: FormBuilder,
//    public platform: Platform,
//    public router: Router,
//    public alertController: AlertController,
//    public authentificationService: AuthenticationService,
//    public translateService: TranslateService,
//
//    public userManager: UserManagerProviderService) {
//
//    if (this.platform.is("ios")) {
//      this.isIOS = true;
//    }
//
//    this.validations_form = this.formBuilder.group({
//      firstName: new FormControl('', Validators.compose([
//        Validators.required
//      ])),
//      lastName: new FormControl('', Validators.compose([
//        Validators.required
//      ])),
//      email: new FormControl('', Validators.compose([
//        Validators.required,
//        Validators.pattern('^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+.[a-zA-Z0-9-.]+$')
//      ])),
//      password: new FormControl('', Validators.compose([
//        Validators.minLength(6),
//        Validators.required,
//      ])),
//      confirmpassword: new FormControl('', Validators.compose([
//        Validators.minLength(6),
//        Validators.required,
//      ])),
//    });
//  }
//
//
//  goNext() {
//    this.apiService.showMessage(this.translateService.instant("Thanks"), this.translateService.instant("Account created."))
//    this.router.navigateByUrl("/home")
//  }
//
//
//  createAccount(params) {
//    if (this.apiService.networkConnected) {
//      // Création du compte.
//      this.apiService.registerUser(params).subscribe((resultat) => {
//        let status = resultat["status"];
//        if (status=="OK") {
//          let data = resultat["data"]
//          this.userManager.setUser(data)
//            // create a token
//              // Check email
//              let paramsToLogin = {
//                "email": params.email,
//                "password": params.password,
//              }
//              this.authentificationService.login(paramsToLogin).then((resultat) => {
//                this.apiService.stopLoading();
//                if (resultat) {
//                   //Authentified
//                   this.router.navigateByUrl("/home")
//                }
//                else {
//                  this.apiService.showError(this.translateService.instant("A technical error occured. Account creation impossible"))
//                }
//              })
//        }
//        else {
//          this.apiService.stopLoading();
//          let error = resultat["error"]
//          if (error.status==400){
//            this.apiService.showError(this.translateService.instant("An account already exists with this email. Please login !"))
//          }
//          else{
//            this.apiService.showError(this.translateService.instant("A technical error occured. Account creation impossible"))
//          }
//
//        }
//      })
//    }
//    else {
//      this.apiService.showNoNetwork()
//    }
//  }
//
//  goLogin() {
//    this.router.navigateByUrl("/login")
//  }
//
//
//
//  onSubmit(values) {
//
//    let email = values["email"]
//    let password = values["password"]
//    let confirmpassword = values["confirmpassword"]
//    let firstName = values["firstName"]
//    let lastName = values["lastName"]
//
//    if (!email) {
//      this.apiService.showError(this.translateService.instant("Please enter an email"))
//      return
//    }
//    if (confirmpassword != password) {
//      this.apiService.showError(this.translateService.instant("Passwords doesn't match"))
//      return
//    }
//    if (this.apiService.networkConnected) {
//      let params = {
//        "email": email,
//        "password": password,
//        "first_name": firstName,
//        "last_name": lastName
//      }
//      this.createAccount(params)
//    }
//    else {
//      this.apiService.showNoNetwork();
//    }
//  }
//  ngOnInit() {
//  }
//
//}
