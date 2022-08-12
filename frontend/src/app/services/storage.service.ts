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
    storage.forEach((key, value, index) => {
      console.log('InStorage', index, key, value);
    });
  }

  public set(key: string, value: any) {
    return this._storage?.set(key, value);
  }

  //public get(key: string) {
  //  return this._storage?.get(key);
  //}
  //public get(key: string) {
  //  return new Observable((observer) => {
  //    let val = this._storage?.get(key);
  //    console.log('retrieve from storage key <', key, '> val: ', val);
  //    observer.next(val);
  //    observer.complete();
  //  });
  //}
  //
  public get(key) {
    return new Promise(async (resolve) => {
      let ret = await this._storage?.get(key);
      if (ret) {
        resolve(ret);
      } else {
        resolve(null);
      }
    });
  }
}
