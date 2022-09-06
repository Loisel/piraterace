import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { GameMaker } from '../model/gamemaker';
import { NewGameMaker } from '../model/newgamemaker';
import { environment } from '../../environments/environment';

@Injectable({
  providedIn: 'root',
})
export class HttpService {
  gamesURL = `${environment.API_URL}/pigame/list_gamemakers`;
  view_gameMakerURL = `${environment.API_URL}/pigame/view_gamemaker`;
  create_gameMakerURL = `${environment.API_URL}/pigame/create_gamemaker`;
  create_new_gameMakerURL = `${environment.API_URL}/pigame/create_new_gamemaker`;
  join_gameMakerURL = `${environment.API_URL}/pigame/join_gamemaker`;
  create_gameURL = `${environment.API_URL}/pigame/create_game`;
  get_gameURL = `${environment.API_URL}/pigame/game`;
  player_cardsURL = `${environment.API_URL}/pigame/player_cards`;
  player_infoURL = `${environment.API_URL}/pigame/update_gm_player_info`;
  get_leaveGameURL = `${environment.API_URL}/pigame/leave_game`;

  constructor(private httpClient: HttpClient) {}
  getGamesList() {
    return this.httpClient.get<GameMaker[]>(this.gamesURL);
  }
  getGameMaker(id: number) {
    return this.httpClient.get<GameMaker>(`${this.view_gameMakerURL}/${id}`);
  }
  createGameMaker(data: NewGameMaker) {
    return this.httpClient.post<GameMaker>(`${this.create_gameMakerURL}`, data);
  }
  createGame(game_id: number) {
    return this.httpClient.get(`${this.create_gameURL}/${game_id}`);
  }
  joinGameMaker(id: number) {
    return this.httpClient.get<GameMaker>(`${this.join_gameMakerURL}/${id}`);
  }
  getGame(id: number) {
    return this.httpClient.get(`${this.get_gameURL}/${id}`);
  }
  getPlayerCards() {
    return this.httpClient.get(`${this.player_cardsURL}`);
  }
  switchPlayerCards(from: number, to: number) {
    let data = [from, to];
    return this.httpClient.post(`${this.player_cardsURL}`, data);
  }
  updateGMPlayerInfo(id: number, data) {
    console.log(data);
    return this.httpClient.post(`${this.player_infoURL}/${id}`, data);
  }
  get_create_new_gameMaker() {
    return this.httpClient.get<NewGameMaker>(`${this.create_new_gameMakerURL}`);
  }
  post_create_new_gameMaker(data: NewGameMaker) {
    console.log('Sending new gamemaker post', data);
    return this.httpClient.post<NewGameMaker>(
      `${this.create_new_gameMakerURL}`,
      data
    );
  }
  get_leaveGame() {
    return this.httpClient.get(`${this.get_leaveGameURL}`);
  }
}
