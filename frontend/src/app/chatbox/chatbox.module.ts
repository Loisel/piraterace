import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IonicModule } from '@ionic/angular';
import { FormsModule } from '@angular/forms';
import { ChatboxComponent } from './chatbox.component';

@NgModule({
  imports: [CommonModule, IonicModule, FormsModule],
  declarations: [ChatboxComponent],
  exports: [ChatboxComponent],
})
export class ChatboxModule {}
