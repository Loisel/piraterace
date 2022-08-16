import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IonicModule } from '@ionic/angular';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';

import { RegisterComponent } from './register/register.component';
import { LoginComponent } from './login/login.component';
import { LogoutComponent } from './logout/logout.component';
import { UserdetailComponent } from './userdetail/userdetail.component';

import { AuthRoutingModule } from './auth-routing.module';

@NgModule({
  declarations: [
    RegisterComponent,
    LoginComponent,
    LogoutComponent,
    UserdetailComponent,
  ],
  imports: [
    CommonModule,
    IonicModule,
    AuthRoutingModule,
    FormsModule,
    ReactiveFormsModule,
  ],
})
export class AuthModule {}
