import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { GameConfig } from '../model/gameconfig';
import { NewGameConfig } from '../model/newgameconfig';
import { environment } from '../../environments/environment';

@Injectable({
  providedIn: 'root',
})
export class HttpService {
  gamesURL = `${environment.API_URL}/pigame/list_gameconfigs`;
  view_gameConfigURL = `${environment.API_URL}/pigame/view_gameconfig`;
  create_gameConfigURL = `${environment.API_URL}/pigame/create_gameconfig`;
  create_new_gameConfigURL = `${environment.API_URL}/pigame/create_new_gameconfig`;
  join_gameConfigURL = `${environment.API_URL}/pigame/join_gameconfig`;
  leave_gameConfigURL = `${environment.API_URL}/pigame/leave_gameconfig`;
  create_gameURL = `${environment.API_URL}/pigame/create_game`;
  get_gameURL = `${environment.API_URL}/pigame/game`;
  player_cardsURL = `${environment.API_URL}/pigame/player_cards`;
  submitCardsURL = `${environment.API_URL}/pigame/submit_cards`;
  powerDownURL = `${environment.API_URL}/pigame/power_down`;
  player_infoURL = `${environment.API_URL}/pigame/update_gm_player_info`;
  get_leaveGameURL = `${environment.API_URL}/pigame/leave_game`;

  constructor(private httpClient: HttpClient) {}
  getGamesList() {
    return this.httpClient.get<GameConfig[]>(this.gamesURL);
  }
  getGameConfig(id: number) {
    return this.httpClient.get<GameConfig>(`${this.view_gameConfigURL}/${id}`);
  }
  createGameConfig(data: NewGameConfig) {
    return this.httpClient.post<GameConfig>(`${this.create_gameConfigURL}`, data);
  }
  createGame(game_id: number) {
    return this.httpClient.get(`${this.create_gameURL}/${game_id}`);
  }
  joinGameConfig(id: number) {
    return this.httpClient.get<GameConfig>(`${this.join_gameConfigURL}/${id}`);
  }
  leaveGameConfig() {
    return this.httpClient.get(`${this.leave_gameConfigURL}`);
  }
  getGame(id: number) {
    return this.httpClient.get(`${this.get_gameURL}/${id}`);
  }
  getPlayerCards() {
    return this.httpClient.get(`${this.player_cardsURL}`);
  }
  submitCards() {
    return this.httpClient.get(`${this.submitCardsURL}`);
  }
  powerDown() {
    return this.httpClient.get(`${this.powerDownURL}`);
  }
  switchPlayerCards(from: number, to: number) {
    let data = [from, to];
    return this.httpClient.post(`${this.player_cardsURL}`, data);
  }
  updateGMPlayerInfo(id: number, data) {
    console.log(data);
    return this.httpClient.post(`${this.player_infoURL}/${id}`, data);
  }
  get_create_new_gameConfig() {
    return this.httpClient.get<NewGameConfig>(`${this.create_new_gameConfigURL}`);
  }
  post_create_new_gameConfig(data: NewGameConfig) {
    return this.httpClient.post<NewGameConfig>(`${this.create_new_gameConfigURL}`, data);
  }
  get_leaveGame() {
    return this.httpClient.get(`${this.get_leaveGameURL}`);
  }
}
