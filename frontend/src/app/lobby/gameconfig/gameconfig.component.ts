import { Component, OnInit } from '@angular/core';
import { ToastController } from '@ionic/angular';
import { Router, ActivatedRoute } from '@angular/router';
import { FormGroup, FormBuilder, FormControl, Validators, AbstractControl, ValidationErrors, ValidatorFn } from '@angular/forms';
import { debounceTime, distinctUntilChanged, distinctUntilKeyChanged } from 'rxjs/operators';

import { GameConfig } from '../../model/gameconfig';
import { HttpService } from '../../services/http.service';

@Component({
  selector: 'app-gameconfig',
  templateUrl: './gameconfig.component.html',
  styleUrls: ['./gameconfig.component.scss'],
})
export class GameConfigComponent implements OnInit {
  gameConfig: GameConfig = null;
  updateTimer: ReturnType<typeof setInterval>;
  cfgOptionsRequestId: number = 0;
  cfgOptionsForm: FormGroup = null;

  constructor(
    private httpService: HttpService,
    private route: ActivatedRoute,
    private router: Router,
    private toastController: ToastController,
    private formBuilder: FormBuilder
  ) {}

  ngOnInit() {}

  buildcfgOptionsForm() {
    if (!this.gameConfig) return;

    if (this.gameConfig['creator_userid'] === this.gameConfig['caller_id']) {
      this.cfgOptionsForm = this.formBuilder.group(
        {
          ncardsavail: new FormControl(
            this.gameConfig.ncardsavail,
            Validators.compose([Validators.required, Validators.min(1), Validators.pattern('^[0-9]+$')])
          ),
          ncardslots: new FormControl(
            this.gameConfig.ncardslots,
            Validators.compose([Validators.required, Validators.min(1), Validators.pattern('^[0-9]+$')])
          ),
        },
        { validators: cardsSlotsLECardsAvailValidator }
      );

      this.cfgOptionsForm.valueChanges
        .pipe(
          debounceTime(1000),
          distinctUntilChanged((prev, curr) => {
            if (!prev) {
              prev = curr;
            }
            return JSON.stringify(prev) === JSON.stringify(curr);
          })
        )
        .subscribe((options) => {
          let id = +this.route.snapshot.paramMap.get('id');

          this.cfgOptionsRequestId += 1;
          console.log('options:', options, this.cfgOptionsRequestId + 1);
          if (this.cfgOptionsForm.valid) {
            this.httpService.updateGameCfgOptions(id, this.cfgOptionsRequestId, options).subscribe(
              (gameconfig) => {
                this.handleNewGameConfig(gameconfig);
              },
              (error) => {
                this.presentToast(error.error, 'danger');
              }
            );
          } else {
            console.log('invalid options', options);
          }
        });
    }
  }

  registerupdateGameConfigInterval() {
    let id = +this.route.snapshot.paramMap.get('id');
    this.updateTimer = setInterval(() => {
      this.updateGameConfig(id);
    }, 2000);
  }

  updateGameConfig(id: number) {
    this.httpService.getGameConfig(id).subscribe(
      (gameconfig) => {
        this.handleNewGameConfig(gameconfig);
      },
      (error) => {
        this.presentToast(error.error, 'danger');
        this.router.navigate(['/lobby']);
      }
    );
  }

  handleNewGameConfig(gameconfig) {
    if (gameconfig['request_id'] > this.cfgOptionsRequestId) {
      console.log('receiving new gamecfg info: local', this.cfgOptionsRequestId, 'remote', gameconfig['request_id'], gameconfig);
      this.gameConfig = gameconfig;
      this.cfgOptionsRequestId = gameconfig.request_id;

      if (gameconfig.creator_userid === gameconfig.caller_id) {
        if (!this.cfgOptionsForm) {
          this.buildcfgOptionsForm();
        }

        this.cfgOptionsForm.setValue({
          ncardsavail: gameconfig['ncardsavail'],
          ncardslots: gameconfig['ncardslots'],
        });
      }
      if (this.gameConfig['game']) {
        this.router.navigate(['game', this.gameConfig['game']]);
      }
    } else {
      console.log('drop new gamecfg info: local', this.cfgOptionsRequestId, 'remote', gameconfig['request_id']);
    }
  }

  createGame() {
    if (!this.cfgOptionsForm.valid) {
      this.presentToast('Cant start game until options are all valid', 'danger');
      return;
    }
    this.httpService.createGame(this.gameConfig.id).subscribe(
      (payload) => {
        console.log(payload);
        // this.router.navigate(['game', payload['game_id']]);
      },
      (error) => {
        console.log('Failed this.httpService.createGame:', error);
        this.presentToast(error.error, 'danger');
      }
    );
  }

  ionViewWillEnter() {
    let id = +this.route.snapshot.paramMap.get('id');
    this.updateGameConfig(id);
    this.registerupdateGameConfigInterval();
  }

  ionViewWillLeave() {
    clearInterval(this.updateTimer);
    this.leaveGameConfig();
  }

  leaveGameConfig() {
    this.httpService.leaveGameConfig().subscribe(
      (payload) => {
        console.log(payload);
      },
      (error) => {
        console.log('Failed to leave this GameConfig:', error);
        this.presentToast(error.error, 'danger');
      }
    );
  }

  onPlayerInfoChange(event) {
    // console.log("Color", this.playerColor);
    this.cfgOptionsRequestId += 1;
    this.httpService
      .updateGameCfgPlayerInfo(this.gameConfig.id, this.cfgOptionsRequestId, {
        color: this.gameConfig['player_colors'][this.gameConfig['caller_idx']],
        team: this.gameConfig['player_teams'][this.gameConfig['caller_idx']],
        ready: this.gameConfig['player_ready'][this.gameConfig['caller_idx']],
      })
      .subscribe(
        (data: any) => {
          this.handleNewGameConfig(data);
        },
        (error) => {
          this.presentToast(error.error, 'danger');
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

export const cardsSlotsLECardsAvailValidator: ValidatorFn = (control: AbstractControl): ValidationErrors | null => {
  const slots = control.get('ncardslots');
  const avail = control.get('ncardsavail');

  let ret = slots && avail && slots.value > avail.value ? { slotsLTavail: true } : null;
  return ret;
};
