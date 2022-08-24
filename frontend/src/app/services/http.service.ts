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
  get_create_new_gameMakerURL() {
    return this.httpClient.get<NewGameMaker>(`${this.create_new_gameMakerURL}`);
  }
  post_create_new_gameMakerURL(data: NewGameMaker) {
    console.log('Sending new gamemaker post', data);
    return this.httpClient.post<NewGameMaker>(
      `${this.create_new_gameMakerURL}`,
      data
    );
  }
}
