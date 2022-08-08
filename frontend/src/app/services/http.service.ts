import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { GameMaker } from '../model/gamemaker';
import { environment } from '../../environments/environment';

@Injectable({
  providedIn: 'root',
})
export class HttpService {
  gamesURL = `${environment.API_URL}/pigame/list_gamemakers`;
  view_gameMakerURL = `${environment.API_URL}/pigame/view_gamemaker`;
  create_gameMakerURL = `${environment.API_URL}/pigame/create_gamemaker`;
  join_gameMakerURL = `${environment.API_URL}/pigame/join_gamemaker`;
  create_gameURL = `${environment.API_URL}/pigame/create_game`;
  get_gameURL = `${environment.API_URL}/pigame/game`;

  constructor(private httpClient: HttpClient) {}
  getGamesList() {
    return this.httpClient.get<GameMaker[]>(this.gamesURL);
  }
  getGameMaker(id: number) {
    return this.httpClient.get<GameMaker>(`${this.view_gameMakerURL}/${id}`);
  }
  createGameMaker() {
    return this.httpClient.get<GameMaker>(`${this.create_gameMakerURL}`);
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
}
