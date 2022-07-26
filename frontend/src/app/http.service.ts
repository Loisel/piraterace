import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { GameMaker } from './gamemaker';
import { environment } from '../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class HttpService {
  gamesURL = `${environment.API_URL}/pigame/list_gamemakers`
  view_gameMakerURL = `${environment.API_URL}/pigame/view_gamemaker`
  create_gameMakerURL = `${environment.API_URL}/pigame/create_gamemaker`
  constructor(private httpClient: HttpClient) { }
  getGamesList() {
    return this.httpClient.get<GameMaker[]>(this.gamesURL);
  }
  getGameMaker(id: number) {
    return this.httpClient.get<GameMaker>(`${this.view_gameMakerURL}/${id}`);
  }
  createGameMaker(){
    return this.httpClient.get<GameMaker>(`${this.create_gameMakerURL}`);    
  }
}
