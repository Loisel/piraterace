import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IonicModule } from '@ionic/angular';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';

import { RegisterComponent } from './register/register.component';

import { AuthmoduleRoutingModule } from './authmodule-routing.module';

@NgModule({
  declarations: [RegisterComponent],
  imports: [
    CommonModule,
    IonicModule,
    AuthmoduleRoutingModule,
    FormsModule,
    ReactiveFormsModule,
  ],
})
export class AuthmoduleModule {}
