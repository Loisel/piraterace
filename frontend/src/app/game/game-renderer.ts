import { Subscription } from 'rxjs';
import { environment } from '../../environments/environment';
import { loadImage, drawTiledBackground, drawStar } from './canvas-utils';

interface BoatState {
  x: number;
  y: number;
  angle: number; // degrees: 0=up 90=right 180=down 270=left
  health: number;
  frame: number; // 0=normal 1=powered_down 2=zombie
  scale: number; // for death-shrink / respawn-grow
  color: string;
  name: string;
  nextCheckpoint: number;
  isMe: boolean;
}

interface Cannonball {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  progress: number;
  alive: boolean;
}

interface StarBurst {
  x: number;
  baseY: number;
  tileH: number;
  color: string;
  type: 'damage' | 'heal';
  startMs: number;
  durationMs: number;
  alive: boolean;
}

interface CardOverlay {
  x: number;
  y: number;
  angle: number;
  img: HTMLImageElement;
  startMs: number;
  halfDurationMs: number;
  alive: boolean;
}

interface BoatTooltip {
  x: number;
  y: number;
  text: string;
  bgColor: string;
  startMs: number;
  durationMs: number;
}

interface OctopusSprite {
  x: number;
  y: number;
  frame: number;
}

interface AnimStep {
  startMs: number;
  durationMs: number;
  tick: (t: number) => void;
  onComplete?: () => void;
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

export class GameRenderer {
  last_played_action = 0;

  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private component: any;

  // Assets
  private tilesetImg: HTMLImageElement;
  private boatImg: HTMLImageElement;
  private octopusImg: HTMLImageElement;
  private cardImgs = new Map<string, HTMLImageElement>();

  // Camera
  private cameraX = 0;
  private cameraY = 0;
  private zoom = 1;
  private isDragging = false;
  private pointerStartX = 0;
  private pointerStartY = 0;
  private hasMoved = false;

  // Game entities
  private boatStates = new Map<number, BoatState>();
  private octopuses: OctopusSprite[] = [];
  private octopusFrameCount = 5;
  private pathTiles: { x: number; y: number }[] = [];

  // Visual effects
  private cannonballs: Cannonball[] = [];
  private starBursts: StarBurst[] = [];
  private cardOverlays: CardOverlay[] = [];
  private boatTooltips: BoatTooltip[] = [];

  // Animation
  private timeline: AnimStep[] = [];
  private readonly animCutoff = 100; // ms; below this, skip tweening

  // Dirty flag: set whenever something visual changes outside of the animation timeline
  private dirty = true;

  // Timers & RAF
  private rafId = 0;
  private updateIntervalId: any;
  private octopusIntervalId: any;
  private cardsSub: Subscription;

  // Bound event listeners (kept for removeEventListener)
  private onPointerDown: (e: PointerEvent) => void;
  private onPointerMove: (e: PointerEvent) => void;
  private onPointerUp: (e: PointerEvent) => void;
  private onWheel: (e: WheelEvent) => void;
  private resizeObserver: ResizeObserver;

  constructor(canvas: HTMLCanvasElement, component: any) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.component = component;
  }

  // ---------------------------------------------------------------------------
  // Lifecycle
  // ---------------------------------------------------------------------------

  async preload(): Promise<void> {
    const GI = this.component.gameinfo;
    const S = environment.STATIC_URL.replace(/\/$/, ''); // strip trailing slash

    const tasks: Promise<void>[] = [
      loadImage(`${S}/maps/${GI.map.tilesets[0].image}`).then((img) => {
        this.tilesetImg = img;
      }),
      loadImage(`${S}/sprites/boat.png`).then((img) => {
        this.boatImg = img;
      }),
      loadImage(`/assets/img/octopus.png`).then((img) => {
        this.octopusImg = img;
        this.octopusFrameCount = Math.max(1, Math.floor(img.naturalWidth / 48));
      }).catch(() => {}), // octopus is optional
    ];

    Object.entries(GI.CARDS).forEach(([, card]: [string, any]) => {
      if (!card.tile_url) return; // some cards (e.g. repair) have no tile image
      tasks.push(
        loadImage(`${S}/${card.tile_url}`).then((img) => {
          this.cardImgs.set(card.descr, img);
        }).catch(() => {})
      );
    });

    await Promise.all(tasks);
  }

  create(): void {
    const GI = this.component.gameinfo;
    const tileW: number = GI.map.tilewidth;
    const tileH: number = GI.map.tileheight;

    // Size canvas to its CSS dimensions and keep in sync on resize
    this.canvas.width = this.canvas.offsetWidth || 800;
    this.canvas.height = this.canvas.offsetHeight || 600;
    this.resizeObserver = new ResizeObserver(() => {
      // Keep the world point at the canvas centre pinned through the resize
      const worldCX = this.cameraX + this.canvas.width / 2 / this.zoom;
      const worldCY = this.cameraY + this.canvas.height / 2 / this.zoom;
      this.canvas.width = this.canvas.offsetWidth || 800;
      this.canvas.height = this.canvas.offsetHeight || 600;
      this.cameraX = worldCX - this.canvas.width / 2 / this.zoom;
      this.cameraY = worldCY - this.canvas.height / 2 / this.zoom;
      this.dirty = true;
    });
    this.resizeObserver.observe(this.canvas);

    // Build boat states from initial game data
    Object.entries(GI.players).forEach(([pid, player]: [string, any]) => {
      this.boatStates.set(+pid, {
        x: (player.start_pos_x + 0.5) * tileW,
        y: (player.start_pos_y + 0.5) * tileH,
        angle: player.start_direction * 90,
        health: player.health,
        frame: player.is_zombie ? 2 : player.powered_down ? 1 : 0,
        scale: 1,
        color: player.color,
        name: player.name,
        nextCheckpoint: player.next_checkpoint,
        isMe: +pid === GI.me,
      });
    });

    // Center camera on own boat
    const me = this.boatStates.get(GI.me);
    if (me) {
      this.cameraX = me.x - this.canvas.width / 2;
      this.cameraY = me.y - this.canvas.height / 2;
    }

    // Octopus sprites on void tiles
    const voids: [number, number][] = GI.map.property_locations?.void ?? [];
    for (const [vx, vy] of voids) {
      this.octopuses.push({
        x: (vx + 0.5) * tileW,
        y: (vy + 0.5) * tileH,
        frame: Math.floor(Math.random() * this.octopusFrameCount),
      });
    }
    this.octopusIntervalId = setInterval(() => {
      for (const oct of this.octopuses) {
        oct.frame = (oct.frame + 1) % this.octopusFrameCount;
      }
      this.dirty = true;
    }, 200);

    // Input events
    this.onPointerDown = (e: PointerEvent) => {
      this.isDragging = true;
      this.hasMoved = false;
      this.pointerStartX = e.clientX;
      this.pointerStartY = e.clientY;
      this.canvas.setPointerCapture(e.pointerId);
    };
    this.onPointerMove = (e: PointerEvent) => {
      if (!this.isDragging) return;
      const dx = e.clientX - this.pointerStartX;
      const dy = e.clientY - this.pointerStartY;
      if (Math.abs(dx) > 4 || Math.abs(dy) > 4) this.hasMoved = true;
      if (this.hasMoved) {
        this.cameraX -= e.movementX / this.zoom;
        this.cameraY -= e.movementY / this.zoom;
        this.dirty = true;
      }
    };
    this.onPointerUp = (e: PointerEvent) => {
      if (!this.hasMoved) this.handleClick(e);
      this.isDragging = false;
    };
    this.onWheel = (e: WheelEvent) => {
      const oldZoom = this.zoom;
      const newZoom = e.deltaY > 0
        ? Math.max(0.3, this.zoom - 0.1)
        : Math.min(3.0, this.zoom + 0.1);
      if (newZoom === oldZoom) return;
      // Pin the world point under the cursor
      const rect = this.canvas.getBoundingClientRect();
      const sx = e.clientX - rect.left;
      const sy = e.clientY - rect.top;
      const wx = sx / oldZoom + this.cameraX;
      const wy = sy / oldZoom + this.cameraY;
      this.zoom = newZoom;
      this.cameraX = wx - sx / newZoom;
      this.cameraY = wy - sy / newZoom;
      this.dirty = true;
    };
    this.canvas.addEventListener('pointerdown', this.onPointerDown);
    this.canvas.addEventListener('pointermove', this.onPointerMove);
    this.canvas.addEventListener('pointerup', this.onPointerUp);
    this.canvas.addEventListener('wheel', this.onWheel, { passive: true });

    // Subscribe to card changes for path highlighting
    this.cardsSub = this.component.cardsinfo.subscribe(() => this.pathHighlighting());

    // Play any accumulated actionstack immediately (handles reconnect)
    this.play_actionstack(0);

    // 1-second polling loop
    this.updateIntervalId = setInterval(() => this.updateEvent(), 1000);

    // Render loop capped at 30 fps
    const interval = 1000 / 30;
    let lastTs = 0;
    const loop = (ts: number) => {
      this.rafId = requestAnimationFrame(loop);
      if (ts - lastTs < interval) return;
      lastTs = ts;
      this.render(ts);
    };
    this.rafId = requestAnimationFrame(loop);
  }

  destroy(): void {
    cancelAnimationFrame(this.rafId);
    clearInterval(this.updateIntervalId);
    clearInterval(this.octopusIntervalId);
    this.resizeObserver?.disconnect();
    this.cardsSub?.unsubscribe();
    this.canvas.removeEventListener('pointerdown', this.onPointerDown);
    this.canvas.removeEventListener('pointermove', this.onPointerMove);
    this.canvas.removeEventListener('pointerup', this.onPointerUp);
    this.canvas.removeEventListener('wheel', this.onWheel);
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
  }

  // ---------------------------------------------------------------------------
  // Render loop
  // ---------------------------------------------------------------------------

  private render(now: number): void {
    const hasActiveEffects =
      this.timeline.length > 0 ||
      this.cannonballs.some((c) => c.alive) ||
      this.starBursts.length > 0 ||
      this.cardOverlays.length > 0 ||
      this.boatTooltips.length > 0;

    if (!hasActiveEffects && !this.dirty) return;
    this.dirty = false;

    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    ctx.save();
    ctx.scale(this.zoom, this.zoom);
    ctx.translate(-this.cameraX, -this.cameraY);

    this.drawMap();
    this.drawOctopuses();
    this.drawGrid();
    this.drawPathHighlights();
    this.drawCheckpoints();
    this.processTimeline(now);
    this.drawBoats();
    this.drawEffects(now);

    ctx.restore();
  }

  // ---------------------------------------------------------------------------
  // Draw passes
  // ---------------------------------------------------------------------------

  private drawMap(): void {
    if (!this.tilesetImg) return;
    const GI = this.component.gameinfo;
    const bgLayer = GI.map.layers.find((l: any) => l.name === 'background');
    if (bgLayer) drawTiledBackground(this.ctx, this.tilesetImg, bgLayer, GI.map.tilesets[0], GI.map.tilewidth, GI.map.tileheight);
  }

  private drawOctopuses(): void {
    if (!this.octopusImg || !this.octopuses.length) return;
    const GI = this.component.gameinfo;
    const tileH: number = GI.map.tileheight;
    const frameW = 48;
    const frameH = 48;
    const scale = tileH / frameH;
    const dw = frameW * scale;
    const dh = frameH * scale;
    for (const oct of this.octopuses) {
      const frame = Math.min(oct.frame, this.octopusFrameCount - 1);
      this.ctx.drawImage(this.octopusImg, frame * frameW, 0, frameW, frameH, oct.x - dw / 2, oct.y - dh / 2, dw, dh);
    }
  }

  private drawGrid(): void {
    const GI = this.component.gameinfo;
    const ctx = this.ctx;
    const tileW: number = GI.map.tilewidth;
    const tileH: number = GI.map.tileheight;
    ctx.save();
    ctx.strokeStyle = 'rgba(0,0,0,0.2)';
    ctx.lineWidth = 1;
    for (let y = 0; y <= GI.map.height; y++) {
      ctx.beginPath();
      ctx.moveTo(0, y * tileH);
      ctx.lineTo(GI.map.width * tileW, y * tileH);
      ctx.stroke();
    }
    for (let x = 0; x <= GI.map.width; x++) {
      ctx.beginPath();
      ctx.moveTo(x * tileW, 0);
      ctx.lineTo(x * tileW, GI.map.height * tileH);
      ctx.stroke();
    }
    ctx.restore();
  }

  private drawCheckpoints(): void {
    const GI = this.component.gameinfo;
    const ctx = this.ctx;
    const tileW: number = GI.map.tilewidth;
    const tileH: number = GI.map.tileheight;
    const nextCp: number = GI.players[GI.me]?.next_checkpoint ?? 999;

    ctx.save();
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = 'bold 30px Arial';
    ctx.lineWidth = 5;

    Object.entries(GI.checkpoints).forEach(([name, pos]: [string, any]) => {
      const n = +name;
      const color = n < nextCp ? '#00cc00' : n === nextCp ? '#ff3333' : '#ffffff';
      const cx = (pos[0] + 0.5) * tileW;
      const cy = (pos[1] + 0.5) * tileH;
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.strokeText(name, cx, cy);
      ctx.fillText(name, cx, cy);
    });
    ctx.restore();
  }

  private drawPathHighlights(): void {
    if (!this.pathTiles.length) return;
    const GI = this.component.gameinfo;
    const ctx = this.ctx;
    const tileW: number = GI.map.tilewidth;
    const tileH: number = GI.map.tileheight;
    const color = GI.players[GI.me]?.color ?? '#ffffff';
    ctx.save();
    ctx.globalAlpha = 0.4;
    ctx.fillStyle = color;
    for (const { x, y } of this.pathTiles) {
      ctx.fillRect(x * tileW, y * tileH, tileW, tileH);
    }
    ctx.restore();
  }

  private drawBoats(): void {
    if (!this.boatImg) return;
    const GI = this.component.gameinfo;
    const ctx = this.ctx;
    const tileW: number = GI.map.tilewidth;
    const tileH: number = GI.map.tileheight;
    const boatDrawH = tileH * 1.1;
    const boatDrawW = (160 * boatDrawH) / 160; // frame is 160×160

    // Draw "me" last (on top)
    const sorted = [...this.boatStates.entries()].sort(([, a], [, b]) => +a.isMe - +b.isMe);

    for (const [, s] of sorted) {
      if (s.scale <= 0) continue;

      ctx.save();
      ctx.translate(s.x, s.y);
      ctx.rotate((s.angle * Math.PI) / 180);
      ctx.scale(s.scale, s.scale);

      // Backdrop rectangle
      ctx.fillStyle = s.color + '88';
      ctx.fillRect(-tileW / 2, -tileH / 2, tileW, tileH);

      // Stroke border (thicker for "me")
      ctx.strokeStyle = s.color;
      ctx.lineWidth = s.isMe ? 5 : 2;
      ctx.strokeRect(-tileW / 2, -tileH / 2, tileW, tileH);

      // Boat sprite (frame 0/1/2 × 160px wide)
      ctx.drawImage(this.boatImg, s.frame * 160, 0, 160, 160, -boatDrawW / 2, -boatDrawH / 2, boatDrawW, boatDrawH);

      ctx.restore();

      // Health bar is drawn un-rotated below the boat
      this.drawHealthBar(s, tileW, tileH, GI.initial_health);
    }
  }

  private drawHealthBar(s: BoatState, tileW: number, tileH: number, initialHealth: number): void {
    const ctx = this.ctx;
    const xOff = -tileW * 0.4;
    const yOff = tileH * 0.3;
    const barW = tileW * 0.8;
    const barH = tileH * 0.12;
    const bx = s.x + xOff;
    const by = s.y + yOff;

    ctx.fillStyle = '#000';
    ctx.fillRect(bx, by, barW, barH);
    ctx.fillStyle = '#fff';
    ctx.fillRect(bx + 2, by + 2, barW - 4, barH - 2);

    const frac = Math.max(0, s.health / initialHealth);
    ctx.fillStyle = frac <= 0.3 ? '#ff0000' : frac <= 0.6 ? '#ffe900' : '#00ff00';
    ctx.fillRect(bx + 2, by + 2, frac * (barW - 4), barH - 2);
  }

  private drawHealBurst(ctx: CanvasRenderingContext2D, burst: StarBurst, t: number, tileW: number, tileH: number): void {
    const cx = burst.x;
    const cy = burst.baseY;
    const s = tileH;

    // Expanding glow ring — fades out in first 30% of animation
    const ringAlpha = Math.max(0, 1 - t / 0.3) * 0.35;
    if (ringAlpha > 0) {
      ctx.save();
      ctx.globalAlpha = ringAlpha;
      ctx.strokeStyle = '#88ffaa';
      ctx.lineWidth = tileH * 0.06;
      ctx.beginPath();
      ctx.arc(cx, cy, t * tileH * 0.9, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    // Three floating "+" signs at staggered positions and speeds
    const plusDefs = [
      { dx: -s * 0.28, speed: 0.85, size: s * 0.24, delay: 0.0, rot: -0.15 },
      { dx:  s * 0.04, speed: 1.10, size: s * 0.32, delay: 0.08, rot: 0.1 },
      { dx:  s * 0.30, speed: 0.75, size: s * 0.20, delay: 0.04, rot: 0.2 },
    ];
    for (const def of plusDefs) {
      const pt = Math.max(0, t - def.delay) / (1 - def.delay);
      if (pt <= 0) continue;
      const rise   = pt * s * 0.75 * def.speed;
      const alpha  = pt < 0.25 ? pt / 0.25 : Math.max(0, 1 - (pt - 0.25) / 0.75);
      const arm    = def.size * 0.5;
      const thick  = def.size * 0.18;
      const rot    = def.rot * pt;

      ctx.save();
      ctx.translate(cx + def.dx, cy - rise);
      ctx.rotate(rot);

      // Outer glow pass
      ctx.globalAlpha = alpha * 0.3;
      ctx.fillStyle = '#aaffcc';
      const gArm = arm * 1.3, gThick = thick * 1.6;
      ctx.beginPath();
      ctx.moveTo(-gArm, -gThick);  ctx.lineTo(-gThick, -gThick);
      ctx.lineTo(-gThick, -gArm);  ctx.lineTo( gThick, -gArm);
      ctx.lineTo( gThick, -gThick); ctx.lineTo( gArm, -gThick);
      ctx.lineTo( gArm,  gThick);  ctx.lineTo( gThick,  gThick);
      ctx.lineTo( gThick,  gArm);  ctx.lineTo(-gThick,  gArm);
      ctx.lineTo(-gThick,  gThick); ctx.lineTo(-gArm,  gThick);
      ctx.closePath();
      ctx.fill();

      // Solid "+" shape
      ctx.globalAlpha = alpha;
      ctx.fillStyle = '#33ee66';
      ctx.beginPath();
      ctx.moveTo(-arm, -thick);  ctx.lineTo(-thick, -thick);
      ctx.lineTo(-thick, -arm);  ctx.lineTo( thick, -arm);
      ctx.lineTo( thick, -thick); ctx.lineTo( arm, -thick);
      ctx.lineTo( arm,  thick);  ctx.lineTo( thick,  thick);
      ctx.lineTo( thick,  arm);  ctx.lineTo(-thick,  arm);
      ctx.lineTo(-thick,  thick); ctx.lineTo(-arm,  thick);
      ctx.closePath();
      ctx.fill();

      // White highlight stripe
      ctx.globalAlpha = alpha * 0.5;
      ctx.fillStyle = '#ffffff';
      const hw = thick * 0.45;
      ctx.beginPath();
      ctx.moveTo(-arm, -hw);   ctx.lineTo(-thick, -hw);
      ctx.lineTo(-thick, -arm); ctx.lineTo(-arm + thick * 0.5, -arm);
      ctx.closePath();
      ctx.fill();

      ctx.restore();
    }

    // Sparkles radiating outward — 8 evenly spaced 4-pointed stars
    const nSparkles = 8;
    for (let i = 0; i < nSparkles; i++) {
      const angle  = (i / nSparkles) * Math.PI * 2 + t * 1.2;
      const radius = t * s * 0.65;
      const sx     = cx + Math.cos(angle) * radius;
      const sy     = cy + Math.sin(angle) * radius;
      // each sparkle pulses: peak brightness at t=0.4, gone by t=1
      const st     = Math.max(0, Math.min(1, t / 0.4)) * Math.max(0, 1 - (t - 0.4) / 0.6);
      if (st <= 0) continue;
      const sparkleSize = s * (0.06 + 0.04 * Math.sin(i * 1.7)) * st;
      ctx.save();
      ctx.globalAlpha = st * 0.9;
      ctx.fillStyle = i % 2 === 0 ? '#ffffff' : '#66ffaa';
      drawStar(ctx, sx, sy, 4, sparkleSize * 0.4, sparkleSize);
      ctx.restore();
    }
  }

  private drawEffects(now: number): void {
    const GI = this.component.gameinfo;
    const ctx = this.ctx;
    const tileW: number = GI.map.tilewidth;
    const tileH: number = GI.map.tileheight;

    // Cannonballs
    for (const ball of this.cannonballs) {
      if (!ball.alive) continue;
      const x = lerp(ball.x0, ball.x1, ball.progress);
      const y = lerp(ball.y0, ball.y1, ball.progress);
      ctx.save();
      ctx.fillStyle = '#111';
      ctx.beginPath();
      ctx.arc(x, y, 7, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    // Star bursts (hits and repairs)
    for (let i = this.starBursts.length - 1; i >= 0; i--) {
      const burst = this.starBursts[i];
      if (!burst.alive) continue;
      const t = Math.min(1, (now - burst.startMs) / burst.durationMs);
      if (t < 0) continue;
      if (t >= 1) {
        burst.alive = false;
        this.starBursts.splice(i, 1);
        continue;
      }
      if (burst.type === 'heal') {
        this.drawHealBurst(ctx, burst, t, tileW, tileH);
      } else {
        const dy = t * (burst.tileH / 2);
        ctx.save();
        ctx.globalAlpha = 1 - t;
        ctx.fillStyle = burst.color;
        drawStar(ctx, burst.x - 2, burst.baseY + 6 - dy, 5, 6, 11);
        drawStar(ctx, burst.x - 5, burst.baseY - 11 - dy, 5, 8, 13);
        ctx.restore();
      }
    }

    // Card overlays
    for (let i = this.cardOverlays.length - 1; i >= 0; i--) {
      const ov = this.cardOverlays[i];
      if (!ov.alive) continue;
      const elapsed = now - ov.startMs;
      if (elapsed < 0) continue; // not yet started — skip (negative globalAlpha is ignored by canvas, not clamped)
      const half = ov.halfDurationMs;
      if (elapsed >= half * 2) {
        ov.alive = false;
        this.cardOverlays.splice(i, 1);
        continue;
      }
      const alpha = elapsed < half ? 0.5 * (elapsed / half) : 0.5 * (1 - (elapsed - half) / half);
      ctx.save();
      ctx.translate(ov.x, ov.y);
      ctx.rotate((ov.angle * Math.PI) / 180);
      ctx.globalAlpha = alpha;
      ctx.drawImage(ov.img, -tileW / 2, -tileH / 2, tileW, tileH);
      ctx.restore();
    }

    // Boat name tooltips
    for (let i = this.boatTooltips.length - 1; i >= 0; i--) {
      const tip = this.boatTooltips[i];
      const t = Math.min(1, (now - tip.startMs) / tip.durationMs);
      if (t >= 1) {
        this.boatTooltips.splice(i, 1);
        continue;
      }
      ctx.save();
      ctx.globalAlpha = 1 - t;
      ctx.font = '24px Arial';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      const tw = ctx.measureText(tip.text).width;
      ctx.fillStyle = tip.bgColor;
      ctx.fillRect(tip.x - tw / 2 - 6, tip.y - 14, tw + 12, 28);
      ctx.fillStyle = '#ffffff';
      ctx.fillText(tip.text, tip.x, tip.y);
      ctx.restore();
    }
  }

  // ---------------------------------------------------------------------------
  // Animation timeline
  // ---------------------------------------------------------------------------

  private processTimeline(now: number): void {
    for (let i = 0; i < this.timeline.length; i++) {
      const step = this.timeline[i];
      if (now < step.startMs) continue;
      const t = step.durationMs === 0 ? 1 : Math.min(1, (now - step.startMs) / step.durationMs);
      step.tick(t);
      if (t >= 1) {
        step.onComplete?.();
        this.timeline.splice(i, 1);
        i--;
      }
    }
  }

  play_actionstack(animDurationMs: number): void {
    const GI = this.component.gameinfo;
    const actionstack = GI.actionstack;
    if (actionstack.length <= this.last_played_action) return;

    const now = performance.now();
    let batchEndMs = now;

    for (let i = this.last_played_action; i < actionstack.length; i++) {
      const offset = (i - this.last_played_action) * animDurationMs;
      const startMs = now + offset;
      for (const action of actionstack[i]) {
        this.scheduleAction(action, animDurationMs, startMs);
      }
      batchEndMs = Math.max(batchEndMs, startMs + animDurationMs);
    }

    // Batch-complete step: sync authoritative state from server payload
    this.timeline.push({
      startMs: batchEndMs,
      durationMs: 0,
      tick: () => {},
      onComplete: () => {
        const GI2 = this.component.gameinfo;
        Object.entries(GI2.players).forEach(([pid, player]: [string, any]) => {
          const s = this.boatStates.get(+pid);
          if (!s) return;
          s.health = player.health;
          s.nextCheckpoint = player.next_checkpoint;
          s.frame = player.is_zombie ? 2 : player.powered_down ? 1 : 0;
          s.scale = Math.max(s.scale, 0); // keep whatever death/respawn left
        });
        this.component.highlightedCardSlot = -1;
      },
    });

    this.last_played_action = actionstack.length;
    this.dirty = true;
  }

  private scheduleAction(action: any, dur: number, startMs: number): void {
    const GI = this.component.gameinfo;
    const tileW: number = GI.map.tilewidth;
    const tileH: number = GI.map.tileheight;
    const s = this.boatStates.get(action.target);

    switch (action.key) {
      // -----------------------------------------------------------------------
      case 'rotate': {
        if (!s) return;
        let toAngle = action.to * 90;
        if (action.from === 0 && action.to === 3) toAngle = -90;
        if (action.from === 3 && action.to === 0) toAngle = 360;
        const fromAngle = action.from * 90;
        if (dur < this.animCutoff) {
          s.angle = toAngle;
        } else {
          this.timeline.push({ startMs, durationMs: dur, tick: (t) => (s.angle = lerp(fromAngle, toAngle, t)) });
        }
        break;
      }

      // -----------------------------------------------------------------------
      case 'move_x': {
        if (!s) return;
        const fromX = (action.from + 0.5) * tileW;
        const toX = (action.to + 0.5) * tileW;
        if (dur < this.animCutoff) {
          s.x = toX;
        } else {
          this.timeline.push({ startMs, durationMs: dur, tick: (t) => (s.x = lerp(fromX, toX, t)) });
        }
        break;
      }

      // -----------------------------------------------------------------------
      case 'move_y': {
        if (!s) return;
        const fromY = (action.from + 0.5) * tileH;
        const toY = (action.to + 0.5) * tileH;
        if (dur < this.animCutoff) {
          s.y = toY;
        } else {
          this.timeline.push({ startMs, durationMs: dur, tick: (t) => (s.y = lerp(fromY, toY, t)) });
        }
        break;
      }

      // -----------------------------------------------------------------------
      case 'collision_x': {
        if (!s || dur < this.animCutoff) return;
        const wiggle = tileW * 0.1 * action.val;
        const nWiggles = 4;
        let baseX: number | null = null;
        this.timeline.push({
          startMs,
          durationMs: dur,
          tick: (t) => {
            if (baseX === null) baseX = s.x;
            s.x = baseX + wiggle * Math.sin(t * nWiggles * 2 * Math.PI);
          },
          onComplete: () => {
            if (baseX !== null) s.x = baseX;
            s.health = action.health;
          },
        });
        break;
      }

      // -----------------------------------------------------------------------
      case 'collision_y': {
        if (!s || dur < this.animCutoff) return;
        const wiggle = tileH * 0.1 * action.val;
        const nWiggles = 4;
        let baseY: number | null = null;
        this.timeline.push({
          startMs,
          durationMs: dur,
          tick: (t) => {
            if (baseY === null) baseY = s.y;
            s.y = baseY + wiggle * Math.sin(t * nWiggles * 2 * Math.PI);
          },
          onComplete: () => {
            if (baseY !== null) s.y = baseY;
            s.health = action.health;
          },
        });
        break;
      }

      // -----------------------------------------------------------------------
      case 'shot': {
        if (dur < this.animCutoff) return;
        const ball: Cannonball = {
          x0: (action.src_x + 0.5) * tileW,
          y0: (action.src_y + 0.5) * tileH,
          x1: (action.collided_at[0] + 0.5) * tileW,
          y1: (action.collided_at[1] + 0.5) * tileH,
          progress: 0,
          alive: false,
        };
        this.cannonballs.push(ball);
        const travelDur = (dur * 2) / 3;
        this.timeline.push({
          startMs,
          durationMs: travelDur,
          tick: (t) => {
            ball.alive = true;
            ball.progress = t;
          },
          onComplete: () => {
            ball.alive = false;
            if (action.other_player !== undefined) {
              const target = this.boatStates.get(action.other_player);
              if (target) target.health = action.other_player_health;
              this.starBursts.push({
                x: ball.x1,
                baseY: ball.y1,
                tileH,
                color: '#ff0000',
                type: 'damage',
                startMs: startMs + travelDur,
                durationMs: dur / 3,
                alive: true,
              });
            }
          },
        });
        break;
      }

      // -----------------------------------------------------------------------
      case 'death': {
        if (!s || dur < this.animCutoff) return;
        let baseScale: number | null = null;
        let baseAngle: number | null = null;
        const spinDeath = action.type === 'void';
        this.timeline.push({
          startMs,
          durationMs: dur,
          tick: (t) => {
            if (baseScale === null) {
              baseScale = s.scale;
              baseAngle = s.angle;
            }
            s.scale = Math.max(0, lerp(baseScale, baseScale - 0.5, t));
            if (spinDeath) s.angle = baseAngle + t * 360;
          },
        });
        break;
      }

      // -----------------------------------------------------------------------
      case 'respawn': {
        if (!s) return;
        const tx = (action.posx + 0.5) * tileW;
        const ty = (action.posy + 0.5) * tileH;
        const ta = action.direction * 90;
        if (dur < this.animCutoff) {
          s.x = tx;
          s.y = ty;
          s.angle = ta;
          s.scale = 1;
          s.health = action.health;
        } else {
          // Teleport immediately at startMs, then grow scale 0→1
          this.timeline.push({
            startMs,
            durationMs: 0,
            tick: () => {},
            onComplete: () => {
              s.x = tx;
              s.y = ty;
              s.angle = ta;
              s.scale = 0;
            },
          });
          this.timeline.push({
            startMs,
            durationMs: dur,
            tick: (t) => (s.scale = t),
            onComplete: () => {
              s.scale = 1;
              s.health = action.health;
            },
          });
        }
        break;
      }

      // -----------------------------------------------------------------------
      case 'repair': {
        if (dur < this.animCutoff) return;
        this.starBursts.push({
          x: (action.posx + 0.5) * tileW,
          baseY: (action.posy + 0.5) * tileH,
          tileH,
          color: '#00ff00',
          type: 'heal',
          startMs,
          durationMs: dur,
          alive: true,
        });
        this.timeline.push({
          startMs,
          durationMs: dur,
          tick: () => {},
          onComplete: () => {
            if (s) s.health = action.health;
          },
        });
        break;
      }

      // -----------------------------------------------------------------------
      case 'card_is_played': {
        if (dur < this.animCutoff) return;
        const cardImg = this.cardImgs.get(action.card.descr);
        if (cardImg && s) {
          const overlay: CardOverlay = {
            x: s.x,
            y: s.y,
            angle: s.angle,
            img: cardImg,
            startMs,
            halfDurationMs: dur * 0.5,
            alive: true,
          };
          this.cardOverlays.push(overlay);
          // Capture boat position at animation start (lazy — after preceding moves)
          this.timeline.push({
            startMs,
            durationMs: 0,
            tick: () => {},
            onComplete: () => {
              overlay.x = s.x;
              overlay.y = s.y;
              overlay.angle = s.angle;
            },
          });
        }
        // Highlight card slot in UI for own player
        if (action.target === GI.me) {
          this.timeline.push({
            startMs,
            durationMs: dur,
            tick: () => {},
            onComplete: () => (this.component.highlightedCardSlot = action.cardslot),
          });
        }
        break;
      }

      // -----------------------------------------------------------------------
      case 'powerdownrepair': {
        if (dur < this.animCutoff) return;
        this.timeline.push({
          startMs,
          durationMs: 0,
          tick: () => {},
          onComplete: () => {
            if (s) {
              s.health = action.health;
              s.frame = 1;
            }
          },
        });
        break;
      }

      // -----------------------------------------------------------------------
      case 'win': {
        this.timeline.push({
          startMs,
          durationMs: 0,
          tick: () => {},
          onComplete: () => {
            clearInterval(this.updateIntervalId);
            this.component.presentSummary();
          },
        });
        break;
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Polling and path highlighting
  // ---------------------------------------------------------------------------

  updateEvent(): void {
    this.component.load_gameinfo().subscribe((gameinfo: any) => {
      this.component.gameinfo = gameinfo;
      this.component.Ngameround.next(gameinfo['Ngameround']);
      this.play_actionstack(gameinfo['time_per_action'] * 900);
      if (gameinfo.countdown && this.component.countDownValue < 0) {
        this.component.setupCountDown(gameinfo.countdown_duration - gameinfo.countdown, gameinfo.countdown_duration);
      }
    });
  }

  private pathHighlighting(): void {
    const GI = this.component.gameinfo;
    if (!GI?.path_highlighting) return;
    this.component.loadPathHighlighting().subscribe(
      (path: [number, number][]) => {
        this.pathTiles = path.map(([x, y]) => ({ x, y }));
        this.dirty = true;
      },
      (err: any) => this.component.presentToast(err.error, 'danger')
    );
  }

  // ---------------------------------------------------------------------------
  // Interaction
  // ---------------------------------------------------------------------------

  private handleClick(e: PointerEvent): void {
    const GI = this.component.gameinfo;
    const rect = this.canvas.getBoundingClientRect();
    const worldX = (e.clientX - rect.left) / this.zoom + this.cameraX;
    const worldY = (e.clientY - rect.top) / this.zoom + this.cameraY;
    const tileW: number = GI.map.tilewidth;
    const tileH: number = GI.map.tileheight;

    for (const [pid, s] of this.boatStates) {
      if (Math.abs(worldX - s.x) < tileW / 2 && Math.abs(worldY - s.y) < tileH / 2) {
        const player = GI.players[pid];
        this.boatTooltips.push({
          x: s.x,
          y: s.y,
          text: `${player.name} ➤ ${player.next_checkpoint}`,
          bgColor: s.color,
          startMs: performance.now(),
          durationMs: 2000,
        });
        break;
      }
    }
  }
}
