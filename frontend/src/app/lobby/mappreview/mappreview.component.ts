import { Component, Input } from '@angular/core';
import { ToastController } from '@ionic/angular';
import { HttpService } from '../../services/http.service';
import { environment } from '../../../environments/environment';
import { loadImage, drawTiledBackground } from '../../game/canvas-utils';

@Component({
  selector: 'app-mappreview',
  template: `<canvas [id]="canvasId" style="width:100%; height:auto; display:block; border-radius:15px;"></canvas>`,
})
export class MapPreviewComponent {
  canvasId = 'map-preview-' + Math.random().toString(36).substring(2);

  private _mapfile: string;

  @Input() set mapfile(value: string) {
    this._mapfile = value;
    if (value) this.loadAndDraw();
  }

  constructor(private httpService: HttpService, private toastController: ToastController) {}

  private loadAndDraw(): void {
    this.httpService.getMapInfo(this._mapfile).subscribe(
      (mapinfo) => this.drawPreview(mapinfo),
      (err) => this.presentToast(err.error, 'danger')
    );
  }

  private async drawPreview(mapinfo: any): Promise<void> {
    const canvas = document.getElementById(this.canvasId) as HTMLCanvasElement;
    if (!canvas) return;

    const mi = mapinfo.map_info;
    const tileW: number = mi.tilewidth;
    const tileH: number = mi.tileheight;
    canvas.width = mi.width * tileW;
    canvas.height = mi.height * tileH;

    const ctx = canvas.getContext('2d');
    const S = environment.STATIC_URL.replace(/\/$/, '');

    const [tilesetImg, boatImg] = await Promise.all([
      loadImage(`${S}/maps/${mi.tilesets[0].image}`),
      loadImage(`${S}/sprites/boat.png`),
    ]);

    // Tilemap background
    const bgLayer = mi.layers.find((l: any) => l.name === 'background');
    if (bgLayer) drawTiledBackground(ctx, tilesetImg, bgLayer, mi.tilesets[0], tileW, tileH);

    // Boats at starting locations (pixel-centered coords from backend)
    const boatH = tileH;
    const boatW = (160 * boatH) / 160;
    for (const [x, y] of mapinfo.startinglocs) {
      ctx.drawImage(boatImg, 0, 0, 160, 160, x - boatW / 2, y - boatH / 2, boatW, boatH);
    }

    // Checkpoint labels
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = 'bold 30px Arial';
    ctx.strokeStyle = '#ffffff';
    ctx.fillStyle = '#ffffff';
    ctx.lineWidth = 5;
    Object.entries(mapinfo.checkpoints).forEach(([name, pos]: [string, any]) => {
      const cx = (pos[0] + 0.5) * tileW;
      const cy = (pos[1] + 0.5) * tileH;
      ctx.strokeText(name, cx, cy);
      ctx.fillText(name, cx, cy);
    });
  }

  private async presentToast(msg: string, color = 'primary'): Promise<void> {
    const toast = await this.toastController.create({ message: msg, color, duration: 5000 });
    toast.present();
  }
}
