import { Component, OnInit, OnDestroy, Input, ViewChild, ElementRef, ViewChildren, QueryList, AfterViewInit } from '@angular/core';
import { ToastController } from '@ionic/angular';
import { HttpService } from '../services/http.service';
import { ChatMessage } from '../model/chatmessage';

@Component({
  selector: 'app-chatbox',
  templateUrl: './chatbox.component.html',
  styleUrls: ['./chatbox.component.scss'],
})
export class ChatboxComponent implements OnInit, AfterViewInit, OnDestroy {
  constructor(private httpService: HttpService, private toastController: ToastController) {}

  updateTimer: ReturnType<typeof setInterval>;
  chat: ChatMessage[] = null;
  activeUsers: any[] = null;
  message: string = '';
  @Input() chatslug = null;
  @ViewChild('chatWindow') chatWindow: ElementRef;
  @ViewChildren('messages') messages: QueryList<any>;

  ngOnInit() {
    this.updateChat();
    this.updateTimer = setInterval(() => {
      this.updateChat();
    }, 2000);
  }

  ngOnDestroy() {
    clearInterval(this.updateTimer);
  }

  ngAfterViewInit() {
    this.scrollToBottom();
    this.messages.changes.subscribe(this.scrollToBottom);
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
    if (this.chatslug !== null) {
      if (this.chatslug === 'global_chat') {
        this.httpService.post_globalChat(this.message).subscribe(
          (ret) => {
            this.message = '';
            this.chat = ret.chat.reverse();
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
            this.chat = ret.chat.reverse();
          },
          (error) => {
            console.log('failed post chat: ', error);
            this.presentToast(error.error, 'danger');
          }
        );
      }
    }
  }

  scrollToBottom = () => {
    try {
      this.chatWindow.nativeElement.scrollTop = this.chatWindow.nativeElement.scrollHeight;
    } catch (err) {
      console.log('Scroll error:', err);
    }
  };

  updateChat() {
    if (this.chatslug !== null) {
      if (this.chatslug === 'global_chat') {
        this.httpService.get_globalChat().subscribe(
          (ret) => {
            let chat = ret.chat.reverse();
            this.activeUsers = ret.active_users;
            if (chat.length > 0) {
              if (this.chat) {
                let lastmsg_incoming = chat[chat.length - 1].message;
                let lastmsg_current = this.chat[this.chat.length - 1].message;
                if (lastmsg_incoming != lastmsg_current) {
                  this.chat = chat;
                }
              } else {
                this.chat = chat;
              }
            }
          },
          (error) => {
            console.log('failed update chat: ', error);
            this.presentToast(error.error, 'danger');
          }
        );
      } else {
        this.httpService.get_gameChat().subscribe((ret) => {
          let chat = ret.chat.reverse();
          if (chat.length > 0) {
            if (this.chat) {
              let lastmsg_incoming = chat[chat.length - 1].message;
              let lastmsg_current = this.chat[this.chat.length - 1].message;
              if (lastmsg_incoming != lastmsg_current) {
                this.chat = chat;
              }
            } else {
              this.chat = chat;
            }
          }
        });
      }
    }
  }
}
