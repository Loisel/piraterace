import { Injectable } from '@angular/core';
import { Storage } from '@ionic/storage-angular';
import { Observable } from 'rxjs';

@Injectable({
  providedIn: 'root',
})
export class StorageService {
  private _storage: Storage | null = null;

  constructor(private storage: Storage) {
    this.init();
  }

  async init() {
    // If using, define drivers here: await this.storage.defineDriver(/*...*/);
    const storage = await this.storage.create();
    this._storage = storage;
    console.log('Storage is up');
    storage.forEach((value, key, index) => {
      console.log('InStorage', index, key, value);
    });
  }

  public set(key: string, value: any) {
    return this._storage?.set(key, value);
  }

  public async get(key) {
    return await this._storage?.get(key);
  }
}
