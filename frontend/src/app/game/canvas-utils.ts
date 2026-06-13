export function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`Failed to load image: ${url}`));
    img.src = url;
  });
}

export function drawTiledBackground(
  ctx: CanvasRenderingContext2D,
  tilesetImg: HTMLImageElement,
  bgLayer: any,
  tileset: any,
  tileW: number,
  tileH: number
): void {
  const cols = tileset.columns || Math.floor(tilesetImg.naturalWidth / tileW);
  const firstgid = tileset.firstgid;
  const width: number = bgLayer.width;
  const height: number = bgLayer.height;
  const data: number[] = bgLayer.data;

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const tileId = data[y * width + x];
      if (!tileId) continue;
      const localId = tileId - firstgid;
      const srcCol = localId % cols;
      const srcRow = Math.floor(localId / cols);
      ctx.drawImage(tilesetImg, srcCol * tileW, srcRow * tileH, tileW, tileH, x * tileW, y * tileH, tileW, tileH);
    }
  }
}

export function drawStar(ctx: CanvasRenderingContext2D, x: number, y: number, points: number, inner: number, outer: number): void {
  ctx.beginPath();
  for (let i = 0; i < points * 2; i++) {
    const angle = (i * Math.PI) / points - Math.PI / 2;
    const r = i % 2 === 0 ? outer : inner;
    if (i === 0) ctx.moveTo(x + r * Math.cos(angle), y + r * Math.sin(angle));
    else ctx.lineTo(x + r * Math.cos(angle), y + r * Math.sin(angle));
  }
  ctx.closePath();
  ctx.fill();
}
