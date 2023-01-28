import { Component, OnInit, OnDestroy, Input } from '@angular/core';
import { ToastController } from '@ionic/angular';
import { HttpService } from '../services/http.service';
import { ChatMessage } from '../model/chatmessage';

@Component({
  selector: 'app-chatbox',
  templateUrl: './chatbox.component.html',
  styleUrls: ['./chatbox.component.scss'],
})
export class ChatboxComponent implements OnInit, OnDestroy {
  constructor(private httpService: HttpService, private toastController: ToastController) {}

  updateTimer: ReturnType<typeof setInterval>;
  chat: ChatMessage[] = null;
  message: string = '';
  @Input() chatslug = null;

  ngOnInit() {
    this.updateChat();
    this.updateTimer = setInterval(() => {
      this.updateChat();
    }, 2000);
  }

  ngOnDestroy() {
    clearInterval(this.updateTimer);
  }

  async presentToast(msg, color = 'primary') {
    const toast = await this.toastController.create({
      message: msg,
      color: color,
      duration: 5000,
    });
    toast.present();
  }

  sendMessage(event) {
    let text = (event.target as HTMLInputElement).value;
    console.log('Messge: ', this.message);
    if (this.chatslug !== null) {
      if (this.chatslug === 'global_chat') {
        this.httpService.post_globalChat(this.message).subscribe(
          (ret) => {
            this.message = '';
            this.chat = ret.chat;
          },
          (error) => {
            console.log('failed post chat: ', error);
            this.presentToast(error.error, 'danger');
          }
        );
      } else {
        this.httpService.post_gameChat(this.message).subscribe(
          (ret) => {
            this.message = '';
            this.chat = ret.chat;
          },
          (error) => {
            console.log('failed post chat: ', error);
            this.presentToast(error.error, 'danger');
          }
        );
      }
    }
  }

  updateChat() {
    if (this.chatslug !== null) {
      if (this.chatslug === 'global_chat') {
        this.httpService.get_globalChat().subscribe(
          (ret) => {
            this.chat = ret.chat;
          },
          (error) => {
            console.log('failed update chat: ', error);
            this.presentToast(error.error, 'danger');
          }
        );
      } else {
        this.httpService.get_gameChat().subscribe((ret) => {
          this.chat = ret.chat;
        });
      }
    }
  }
}
