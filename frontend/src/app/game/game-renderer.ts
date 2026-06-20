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
  upgrades: { type: string; charges?: number }[];
  onFire: boolean;
  isCursed: boolean;
}

interface TreasureSprite {
  id: string;
  x: number; // tile coords
  y: number;
  upgrade: string;
  spawnMs: number;
  alive: boolean;
}

interface Cannonball {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  progress: number;
  alive: boolean;
  onFire?: boolean;
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
  color: string;
  name: string;
  health: number;
  maxHealth: number;
  nextCheckpoint: number;
  upgrades: { type: string; charges?: number }[];
  onFire: boolean;
  startMs: number;
  durationMs: number;
  peerOffset?: number;
}

interface TreasureTooltip {
  x: number;
  y: number;
  upgrade: string | null;
  startMs: number;
  durationMs: number;
  peerOffset?: number;
}

interface OctopusSprite {
  x: number;
  y: number;
  frame: number;
}

interface Explosion {
  x: number;
  y: number;
  startMs: number;
  durationMs: number;
  alive: boolean;
}

interface FireParticle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  color: string;
  startMs: number;
  durationMs: number;
  alive: boolean;
  noGravity?: boolean; // boat-fire rises; explosion fire droops
  grow?: boolean;      // smoke expands as it rises
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
  private explosionImg: HTMLImageElement;
  private emberImg: HTMLImageElement;
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
  private treasures = new Map<string, TreasureSprite>();

  // Visual effects
  private cannonballs: Cannonball[] = [];
  private starBursts: StarBurst[] = [];
  private explosions: Explosion[] = [];
  private fireParticles: FireParticle[] = [];
  private cardOverlays: CardOverlay[] = [];
  private boatTooltips: BoatTooltip[] = [];
  private treasureTooltips: TreasureTooltip[] = [];

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
      loadImage(`${S}/sprites/explosion.png`).then((img) => {
        this.explosionImg = img;
      }).catch(() => {}),
      loadImage(`${S}/sprites/ember.png`).then((img) => {
        this.emberImg = img;
      }).catch(() => {}),
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
        upgrades: player.upgrades ?? [],
        onFire: false,
        isCursed: player.is_cursed ?? false,
      });
    });

    // Restore any active treasures from server state (handles reconnect)
    if (GI.active_treasures) {
      for (const t of GI.active_treasures) {
        this.treasures.set(t.id, { ...t, spawnMs: 0, alive: true });
      }
    }

    // Seed animated state for the HTML panel (reconnect / fresh load)
    this.component.currentPlayerUpgrades = [...(GI.players[GI.me]?.upgrades ?? [])];
    this.component.currentPlayerHealth = GI.players[GI.me]?.health ?? 0;

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
    const anyBoatOnFire = (() => { for (const s of this.boatStates.values()) if (s.onFire && s.scale > 0) return true; return false; })();
    const hasActiveEffects =
      this.timeline.length > 0 ||
      this.cannonballs.some((c) => c.alive) ||
      this.starBursts.length > 0 ||
      this.explosions.length > 0 ||
      this.fireParticles.length > 0 ||
      this.cardOverlays.length > 0 ||
      this.boatTooltips.length > 0 ||
      this.treasureTooltips.length > 0 ||
      this.treasures.size > 0 || // treasures bob continuously
      anyBoatOnFire;

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
    this.drawTreasures(now);
    this.processTimeline(now);
    this.drawBoats();
    if (anyBoatOnFire) this.emitBoatFireParticles(now);
    this.drawEffects(now);

    ctx.restore();
  }

  private emitBoatFireParticles(now: number): void {
    const GI = this.component.gameinfo;
    if (!GI) return;
    const tileW: number = GI.map.tilewidth;
    const tileH: number = GI.map.tileheight;
    const fireColors = ['#ff6600', '#ff9900', '#ffcc00', '#ff4400', '#ff2200'];

    for (const s of this.boatStates.values()) {
      if (!s.onFire || s.scale <= 0) continue;

      // 1-2 fire particles per frame
      const nFire = Math.random() < 0.6 ? 2 : 1;
      for (let i = 0; i < nFire; i++) {
        const angle = -Math.PI / 2 + (Math.random() - 0.5) * 0.9;
        const speed = tileH * (0.8 + Math.random() * 0.8);
        this.fireParticles.push({
          x: s.x + (Math.random() - 0.5) * tileW * 0.5,
          y: s.y + (Math.random() - 0.5) * tileH * 0.25,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed,
          size: 2.5 + Math.random() * 3.5,
          color: fireColors[Math.floor(Math.random() * fireColors.length)],
          startMs: now,
          durationMs: 270 + Math.random() * 220,
          alive: true,
          noGravity: true,
        });
      }

      // occasional smoke puff
      if (Math.random() < 0.35) {
        const grey = 65 + Math.floor(Math.random() * 75);
        this.fireParticles.push({
          x: s.x + (Math.random() - 0.5) * tileW * 0.4,
          y: s.y - tileH * 0.1,
          vx: (Math.random() - 0.5) * tileW * 0.12,
          vy: -tileH * (0.28 + Math.random() * 0.28),
          size: 7 + Math.random() * 9,
          color: `rgb(${grey},${grey},${grey})`,
          startMs: now,
          durationMs: 750 + Math.random() * 500,
          alive: true,
          noGravity: true,
          grow: true,
        });
      }
    }
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
    const nextCp: number = this.boatStates.get(GI.me)?.nextCheckpoint ?? GI.players[GI.me]?.next_checkpoint ?? 999;

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

    // upgrade badges below health bar (upgrades + curse indicator)
    const allBadges: { type: string; charges?: number }[] = [
      ...(s.upgrades ?? []),
      ...(s.isCursed ? [{ type: 'odysseus_curse' }] : []),
    ];
    if (allBadges.length > 0) {
      const badgeSize = tileH * 0.18;
      const gap = badgeSize * 0.25;
      const totalW = allBadges.length * (badgeSize + gap) - gap;
      let bx2 = s.x - totalW / 2;
      const by2 = by + barH + 3;
      for (const upg of allBadges) {
        this.drawUpgradeBadge(ctx, bx2, by2, badgeSize, upg);
        bx2 += badgeSize + gap;
      }
    }

    // fire overlay when on fire
    if (s.onFire) {
      ctx.save();
      ctx.globalAlpha = 0.55;
      const grad = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, tileW * 0.6);
      grad.addColorStop(0, '#ff6600');
      grad.addColorStop(1, 'rgba(255,0,0,0)');
      ctx.fillStyle = grad;
      ctx.fillRect(s.x - tileW / 2, s.y - tileH / 2, tileW, tileH);
      ctx.restore();
    }
  }

  private drawUpgradeBadge(ctx: CanvasRenderingContext2D, x: number, y: number, size: number, upg: { type: string; charges?: number }): void {
    const r = size / 2;
    ctx.save();

    // badge background colour per upgrade type
    const bgColors: Record<string, string> = {
      burning_cannons: '#cc2200',
      shield: '#2244cc',
      checkpoint_rush: '#cc9900',
      ghost_ship: '#8833cc',
      solid_rock: '#6b5a4a',
      carpenter: '#2a6a2a',
      shipwright: '#007a7a',
      odysseus_curse: '#4a1a7a',
      rose_cannons: '#1a5a8a',
      quartermaster: '#8a6000',
    };
    const symbols: Record<string, string> = {
      burning_cannons: '🔥',
      shield: '🛡',
      checkpoint_rush: '⚑',
      ghost_ship: '👻',
      solid_rock: '🪨',
      carpenter: '🔧',
      shipwright: '⚓',
      odysseus_curse: '🌊',
      rose_cannons: '🧭',
      quartermaster: '🗺️',
    };

    ctx.fillStyle = bgColors[upg.type] ?? '#555';
    ctx.beginPath();
    ctx.arc(x + r, y + r, r, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 1;
    ctx.stroke();

    // symbol or letter fallback
    const sym = symbols[upg.type];
    if (sym) {
      ctx.font = `${size * 0.65}px Arial`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = '#fff';
      ctx.fillText(sym, x + r, y + r + 0.5);
    }

    // shield charge counter
    if (upg.type === 'shield' && upg.charges !== undefined) {
      ctx.font = `bold ${size * 0.45}px Arial`;
      ctx.textAlign = 'right';
      ctx.textBaseline = 'bottom';
      ctx.fillStyle = '#fff';
      ctx.fillText(String(upg.charges), x + size - 1, y + size - 1);
    }

    ctx.restore();
  }

  private drawTreasures(now: number): void {
    const GI = this.component.gameinfo;
    const ctx = this.ctx;
    const tileW: number = GI.map.tilewidth;
    const tileH: number = GI.map.tileheight;

    for (const [, t] of this.treasures) {
      if (!t.alive) continue;
      const cx = (t.x + 0.5) * tileW;
      const cy = (t.y + 0.5) * tileH;

      // gentle bob
      const bob = Math.sin(now * 0.003 + t.x * 1.3 + t.y * 0.7) * tileH * 0.06;

      // spawn pop-in scale (0→1 over 300ms)
      const age = t.spawnMs > 0 ? Math.min(1, (now - t.spawnMs) / 300) : 1;
      const sc = age;

      ctx.save();
      ctx.translate(cx, cy + bob);
      ctx.scale(sc, sc);

      const w = tileW * 0.6;
      const h = tileH * 0.45;

      // chest body
      ctx.fillStyle = '#8B4513';
      ctx.fillRect(-w / 2, -h / 4, w, h * 0.7);

      // chest lid
      ctx.fillStyle = '#A0522D';
      ctx.beginPath();
      ctx.ellipse(0, -h / 4, w / 2, h * 0.28, 0, Math.PI, 0);
      ctx.fill();

      // gold trim horizontal
      ctx.strokeStyle = '#FFD700';
      ctx.lineWidth = tileH * 0.05;
      ctx.beginPath();
      ctx.moveTo(-w / 2, -h / 4);
      ctx.lineTo(w / 2, -h / 4);
      ctx.stroke();

      // lock
      ctx.fillStyle = '#FFD700';
      ctx.beginPath();
      ctx.arc(0, 0, w * 0.1, 0, Math.PI * 2);
      ctx.fill();

      // upgrade type colour dot on lid — only when treasure_preview is enabled
      if (GI.treasure_preview !== false) {
        const dotColors: Record<string, string> = {
          burning_cannons: '#ff3300',
          shield: '#3366ff',
          checkpoint_rush: '#ffcc00',
          ghost_ship: '#aa44ff',
          solid_rock: '#c8a882',
          carpenter: '#44cc44',
          shipwright: '#00dddd',
          rose_cannons: '#55aaff',
          quartermaster: '#cc9933',
        };
        ctx.fillStyle = dotColors[t.upgrade] ?? '#fff';
        ctx.beginPath();
        ctx.arc(0, -h / 4 - h * 0.12, w * 0.09, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.restore();
    }
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
      if (ball.onFire) {
        ctx.fillStyle = '#cc0000';
        ctx.shadowColor = '#ff4400';
        ctx.shadowBlur = 14;
      } else {
        ctx.fillStyle = '#111';
      }
      ctx.beginPath();
      ctx.arc(x, y, 7, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    // Explosions (sprite sheet animation on cannon hits)
    if (this.explosionImg) {
      const NFRAMES = 8;
      const FRAME_W = this.explosionImg.naturalWidth / NFRAMES;
      const FRAME_H = this.explosionImg.naturalHeight;
      for (let i = this.explosions.length - 1; i >= 0; i--) {
        const ex = this.explosions[i];
        const t = (now - ex.startMs) / ex.durationMs;
        if (t < 0) continue;
        if (t >= 1) { ex.alive = false; this.explosions.splice(i, 1); continue; }
        const frame = Math.min(NFRAMES - 1, Math.floor(t * NFRAMES));
        const drawW = tileW * 2.2;
        const drawH = tileH * 2.2;
        ctx.save();
        ctx.globalAlpha = Math.min(1, (1 - t) * 3);
        ctx.drawImage(this.explosionImg, frame * FRAME_W, 0, FRAME_W, FRAME_H,
          ex.x - drawW / 2, ex.y - drawH / 2, drawW, drawH);
        ctx.restore();
      }
    }

    // Fire particles (embers from explosions and continuous boat fire)
    for (let i = this.fireParticles.length - 1; i >= 0; i--) {
      const p = this.fireParticles[i];
      const t = (now - p.startMs) / p.durationMs;
      if (t < 0) continue;
      if (t >= 1) { p.alive = false; this.fireParticles.splice(i, 1); continue; }
      const x = p.x + p.vx * t;
      const y = p.y + p.vy * t + (p.noGravity ? 0 : 40 * t * t);
      const alpha = t < 0.15 ? t / 0.15 : 1 - (t - 0.15) / 0.85;
      const size = p.grow ? p.size * (1 + t * 1.5) : p.size * (1 - t * 0.5);
      ctx.save();
      ctx.globalAlpha = (p.grow ? alpha * 0.55 : alpha * 0.9); // smoke is dimmer
      ctx.fillStyle = p.color;
      if (!p.grow) { ctx.shadowColor = p.color; ctx.shadowBlur = size * 2; }
      ctx.beginPath();
      ctx.arc(x, y, Math.max(0.5, size), 0, Math.PI * 2);
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

    // Shared lookup tables for both tooltip types
    const BADGE_COLORS_SHARED: Record<string, string> = {
      burning_cannons: '#cc2200', shield: '#2244cc', checkpoint_rush: '#cc9900',
      ghost_ship: '#8833cc', solid_rock: '#6b5a4a', carpenter: '#2a6a2a', shipwright: '#007a7a',
      odysseus_curse: '#4a1a7a', rose_cannons: '#1a5a8a', quartermaster: '#8a6000',
    };
    const BADGE_SYMBOLS_SHARED: Record<string, string> = {
      burning_cannons: '🔥', shield: '🛡', checkpoint_rush: '⚑', ghost_ship: '👻', solid_rock: '🪨',
      carpenter: '🔧', shipwright: '⚓', odysseus_curse: '🌊', rose_cannons: '🧭', quartermaster: '🗺️',
    };

    // Boat info cards — drawn in screen space so font sizes are always readable
    for (let i = this.boatTooltips.length - 1; i >= 0; i--) {
      const tip = this.boatTooltips[i];
      const elapsed = now - tip.startMs;
      if (elapsed >= tip.durationMs) { this.boatTooltips.splice(i, 1); continue; }

      const fadeDur = 500;
      const alpha = elapsed > tip.durationMs - fadeDur ? 1 - (elapsed - (tip.durationMs - fadeDur)) / fadeDur : 1;
      const scaleIn = Math.min(1, elapsed / 180);

      // Convert boat world position → screen pixels
      const sx = (tip.x - this.cameraX) * this.zoom;
      const sy = (tip.y - this.cameraY) * this.zoom;

      // Fixed screen-space dimensions
      const hasUpgrades = tip.upgrades.length > 0;
      const HEADER_H = 28;
      const HB_H = 16;
      const INFO_H = 20;
      const BADGE_ROW_H = hasUpgrades ? 34 : 0;
      const PAD = 10;
      const panelW = 192;
      const panelH = HEADER_H + PAD / 2 + HB_H + PAD / 2 + INFO_H + (hasUpgrades ? PAD / 2 + BADGE_ROW_H : 0) + PAD / 2;
      const r = 7;

      // Position: above the boat, clamped to canvas edges
      const boatScreenR = tileH * this.zoom * 0.55;
      let px = sx - panelW / 2 + (tip.peerOffset ?? 0);
      let py = sy - boatScreenR - panelH;
      if (py < 4) py = sy + boatScreenR;
      px = Math.max(4, Math.min(this.canvas.width - panelW - 4, px));
      py = Math.max(4, Math.min(this.canvas.height - panelH - 4, py));

      ctx.save();
      ctx.resetTransform();
      ctx.globalAlpha = alpha;

      // Scale-in from panel centre
      const cx = px + panelW / 2;
      const cy = py + panelH / 2;
      ctx.translate(cx, cy);
      ctx.scale(scaleIn, scaleIn);
      ctx.translate(-cx, -cy);

      // Drop shadow
      ctx.shadowColor = 'rgba(0,0,0,0.6)';
      ctx.shadowBlur = 12;
      ctx.shadowOffsetY = 4;

      // Panel body
      ctx.fillStyle = 'rgba(16,18,28,0.96)';
      ctx.beginPath();
      ctx.moveTo(px + r, py);
      ctx.lineTo(px + panelW - r, py);
      ctx.arcTo(px + panelW, py, px + panelW, py + r, r);
      ctx.lineTo(px + panelW, py + panelH - r);
      ctx.arcTo(px + panelW, py + panelH, px + panelW - r, py + panelH, r);
      ctx.lineTo(px + r, py + panelH);
      ctx.arcTo(px, py + panelH, px, py + panelH - r, r);
      ctx.lineTo(px, py + r);
      ctx.arcTo(px, py, px + r, py, r);
      ctx.closePath();
      ctx.fill();
      ctx.shadowColor = 'transparent';

      // Coloured header strip
      ctx.fillStyle = tip.color;
      ctx.beginPath();
      ctx.moveTo(px + r, py);
      ctx.lineTo(px + panelW - r, py);
      ctx.arcTo(px + panelW, py, px + panelW, py + r, r);
      ctx.lineTo(px + panelW, py + HEADER_H);
      ctx.lineTo(px, py + HEADER_H);
      ctx.lineTo(px, py + r);
      ctx.arcTo(px, py, px + r, py, r);
      ctx.closePath();
      ctx.fill();

      // Player name
      ctx.fillStyle = '#fff';
      ctx.font = 'bold 14px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(tip.name, px + panelW / 2, py + HEADER_H / 2, panelW - 12);

      // Health bar
      const hbX = px + PAD;
      const hbY = py + HEADER_H + PAD / 2;
      const hbW = panelW - PAD * 2;
      const hpFrac = Math.max(0, tip.health / tip.maxHealth);
      const hbColor = hpFrac > 0.6 ? '#00cc44' : hpFrac > 0.3 ? '#ffe900' : '#ff3333';
      ctx.fillStyle = '#2a2a3a';
      ctx.fillRect(hbX, hbY, hbW, HB_H);
      ctx.fillStyle = hbColor;
      ctx.fillRect(hbX, hbY, hbW * hpFrac, HB_H);
      ctx.fillStyle = 'rgba(255,255,255,0.92)';
      ctx.font = 'bold 11px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(`${tip.health} / ${tip.maxHealth}`, hbX + hbW / 2, hbY + HB_H / 2);

      // Checkpoint + on-fire indicator
      const infoY = hbY + HB_H + PAD / 2 + INFO_H / 2;
      ctx.font = '12px sans-serif';
      ctx.textAlign = 'left';
      ctx.fillStyle = '#bbb';
      ctx.fillText(`→ CP ${tip.nextCheckpoint}`, hbX, infoY);
      if (tip.onFire) {
        ctx.textAlign = 'right';
        ctx.fillStyle = '#ff7700';
        ctx.fillText('🔥 on fire', px + panelW - PAD, infoY);
      }

      // Upgrade badges
      if (hasUpgrades) {
        const BADGE_COLORS = BADGE_COLORS_SHARED;
        const BADGE_SYMBOLS = BADGE_SYMBOLS_SHARED;
        const divY = infoY + INFO_H / 2 + PAD / 2;
        ctx.strokeStyle = 'rgba(255,255,255,0.1)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(px + PAD, divY);
        ctx.lineTo(px + panelW - PAD, divY);
        ctx.stroke();

        const badgeR = 13;
        const badgeY = divY + PAD / 2 + badgeR;
        tip.upgrades.forEach((upg, idx) => {
          const bx = hbX + badgeR + idx * (badgeR * 2 + 6);
          ctx.fillStyle = BADGE_COLORS[upg.type] ?? '#555';
          ctx.beginPath();
          ctx.arc(bx, badgeY, badgeR, 0, Math.PI * 2);
          ctx.fill();
          ctx.font = '16px sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(BADGE_SYMBOLS[upg.type] ?? '?', bx, badgeY);
          if (upg.type === 'shield' && upg.charges !== undefined) {
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 9px sans-serif';
            ctx.fillText(String(upg.charges), bx + 9, badgeY - 9);
          }
        });
      }

      ctx.restore();
    }

    // Treasure chest tooltips
    const UPGRADE_LABELS: Record<string, string> = {
      burning_cannons: 'Burning Cannons', shield: 'Shield', checkpoint_rush: 'Checkpoint Rush',
      ghost_ship: 'Ghost Ship', solid_rock: 'Solid as a Rock', carpenter: 'Carpenter',
      shipwright: 'Shipwright', rose_cannons: 'Rose Cannons', quartermaster: 'Quartermaster',
    };
    const UPGRADE_DESCS: Record<string, string> = {
      burning_cannons: 'Shots set opponents on fire each round',
      shield: 'Absorbs up to 3 damage from cannon hits',
      checkpoint_rush: 'Skip your next checkpoint instantly',
      ghost_ship: 'Pass through void tiles unharmed',
      solid_rock: 'Cannot be pushed by other ships',
      carpenter: 'Repairs +1 health at end of each round',
      shipwright: 'Repairs +2 health at end of each round',
      rose_cannons: 'Fires cannons in all 4 directions',
      quartermaster: 'Draw one extra card to choose from',
    };

    for (let i = this.treasureTooltips.length - 1; i >= 0; i--) {
      const tip = this.treasureTooltips[i];
      const elapsed = now - tip.startMs;
      if (elapsed >= tip.durationMs) { this.treasureTooltips.splice(i, 1); continue; }

      const fadeDur = 500;
      const alpha = elapsed > tip.durationMs - fadeDur ? 1 - (elapsed - (tip.durationMs - fadeDur)) / fadeDur : 1;
      const scaleIn = Math.min(1, elapsed / 180);

      const sx = (tip.x - this.cameraX) * this.zoom;
      const sy = (tip.y - this.cameraY) * this.zoom;

      const HEADER_H = 28;
      const PAD = 10;
      const panelW = 192;
      const DESC_H = tip.upgrade ? 32 : 22;
      const FOOTER_H = 20;
      const panelH = HEADER_H + PAD / 2 + DESC_H + PAD / 2 + FOOTER_H + PAD / 2;
      const r = 7;

      const boatScreenR = tileH * this.zoom * 0.55;
      let px = sx - panelW / 2 + (tip.peerOffset ?? 0);
      let py = sy - boatScreenR - panelH;
      if (py < 4) py = sy + boatScreenR;
      px = Math.max(4, Math.min(this.canvas.width - panelW - 4, px));
      py = Math.max(4, Math.min(this.canvas.height - panelH - 4, py));

      ctx.save();
      ctx.resetTransform();
      ctx.globalAlpha = alpha;

      const cx2 = px + panelW / 2;
      const cy2 = py + panelH / 2;
      ctx.translate(cx2, cy2);
      ctx.scale(scaleIn, scaleIn);
      ctx.translate(-cx2, -cy2);

      ctx.shadowColor = 'rgba(0,0,0,0.6)';
      ctx.shadowBlur = 12;
      ctx.shadowOffsetY = 4;

      ctx.fillStyle = 'rgba(16,18,28,0.96)';
      ctx.beginPath();
      ctx.moveTo(px + r, py); ctx.lineTo(px + panelW - r, py);
      ctx.arcTo(px + panelW, py, px + panelW, py + r, r);
      ctx.lineTo(px + panelW, py + panelH - r);
      ctx.arcTo(px + panelW, py + panelH, px + panelW - r, py + panelH, r);
      ctx.lineTo(px + r, py + panelH);
      ctx.arcTo(px, py + panelH, px, py + panelH - r, r);
      ctx.lineTo(px, py + r);
      ctx.arcTo(px, py, px + r, py, r);
      ctx.closePath();
      ctx.fill();
      ctx.shadowColor = 'transparent';

      const headerColor = tip.upgrade ? (BADGE_COLORS_SHARED[tip.upgrade] ?? '#8B4513') : '#5a3010';
      ctx.fillStyle = headerColor;
      ctx.beginPath();
      ctx.moveTo(px + r, py); ctx.lineTo(px + panelW - r, py);
      ctx.arcTo(px + panelW, py, px + panelW, py + r, r);
      ctx.lineTo(px + panelW, py + HEADER_H);
      ctx.lineTo(px, py + HEADER_H);
      ctx.lineTo(px, py + r);
      ctx.arcTo(px, py, px + r, py, r);
      ctx.closePath();
      ctx.fill();

      ctx.fillStyle = '#fff';
      ctx.font = 'bold 13px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      const headerLabel = tip.upgrade
        ? `${BADGE_SYMBOLS_SHARED[tip.upgrade] ?? '?'} ${UPGRADE_LABELS[tip.upgrade] ?? tip.upgrade}`
        : '? Treasure Chest';
      ctx.fillText(headerLabel, px + panelW / 2, py + HEADER_H / 2, panelW - 12);

      const bodyY = py + HEADER_H + PAD / 2;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      if (tip.upgrade) {
        ctx.font = '11px sans-serif';
        ctx.fillStyle = '#ccc';
        const desc = UPGRADE_DESCS[tip.upgrade] ?? '';
        // wrap at ~28 chars
        if (desc.length > 28) {
          const mid = desc.lastIndexOf(' ', 28);
          ctx.fillText(desc.slice(0, mid), px + panelW / 2, bodyY, panelW - PAD * 2);
          ctx.fillText(desc.slice(mid + 1), px + panelW / 2, bodyY + 14, panelW - PAD * 2);
        } else {
          ctx.fillText(desc, px + panelW / 2, bodyY + 8, panelW - PAD * 2);
        }
      } else {
        ctx.font = '16px sans-serif';
        ctx.fillStyle = '#ddd';
        const allSymbols = Object.values(BADGE_SYMBOLS_SHARED).join(' ');
        ctx.fillText(allSymbols, px + panelW / 2, bodyY + 2, panelW - PAD);
      }

      const footerY = py + HEADER_H + PAD / 2 + DESC_H + PAD / 2 + FOOTER_H / 2;
      ctx.font = 'italic 10px sans-serif';
      ctx.fillStyle = '#FFD700';
      ctx.textBaseline = 'middle';
      ctx.fillText('Stand here at round end to collect', px + panelW / 2, footerY, panelW - PAD * 2);

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
          s.upgrades = player.upgrades ?? [];
          s.onFire = false;
          s.isCursed = player.is_cursed ?? false;
        });
        // push animated state to the HTML panel (fires at end of animation, not mid-round)
        const meState = this.boatStates.get(GI2.me);
        if (meState) {
          this.component.currentPlayerUpgrades = [...meState.upgrades];
          this.component.currentPlayerHealth = meState.health;
        }
        // sync treasure map with server's authoritative list
        if (GI2.active_treasures) {
          const serverIds = new Set(GI2.active_treasures.map((t: any) => t.id));
          for (const id of this.treasures.keys()) {
            if (!serverIds.has(id)) this.treasures.delete(id);
          }
          for (const t of GI2.active_treasures) {
            if (!this.treasures.has(t.id)) {
              this.treasures.set(t.id, { ...t, spawnMs: 0, alive: true });
            }
          }
        }
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
        const isMe_cx = action.target === GI.me;
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
            if (isMe_cx) this.component.currentPlayerHealth = s.health;
          },
        });
        break;
      }

      // -----------------------------------------------------------------------
      case 'collision_y': {
        if (!s || dur < this.animCutoff) return;
        const wiggle = tileH * 0.1 * action.val;
        const nWiggles = 4;
        const isMe_cy = action.target === GI.me;
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
            if (isMe_cy) this.component.currentPlayerHealth = s.health;
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
          onFire: !!action.on_fire,
        };
        this.cannonballs.push(ball);
        const travelDur = (dur * 2) / 3;

        // Fire trail for burning cannonballs
        if (ball.onFire) {
          const trailColors = ['#ff0000', '#ff3300', '#ff6600', '#ff9900'];
          const nTrail = 28;
          for (let ti = 0; ti < nTrail; ti++) {
            const frac = ti / nTrail;
            this.fireParticles.push({
              x: lerp(ball.x0, ball.x1, frac) + (Math.random() - 0.5) * tileW * 0.12,
              y: lerp(ball.y0, ball.y1, frac) + (Math.random() - 0.5) * tileH * 0.12,
              vx: (Math.random() - 0.5) * tileW * 0.15,
              vy: (Math.random() - 0.5) * tileH * 0.15 - tileH * 0.1,
              size: 2.5 + Math.random() * 3.5,
              color: trailColors[Math.floor(Math.random() * trailColors.length)],
              startMs: startMs + frac * travelDur,
              durationMs: 200 + Math.random() * 180,
              alive: true,
              noGravity: true,
            });
          }
        }

        this.timeline.push({
          startMs,
          durationMs: travelDur,
          tick: (t) => {
            ball.alive = true;
            ball.progress = t;
          },
          onComplete: () => {
            ball.alive = false;
            const impactMs = startMs + travelDur;
            const impactDur = dur - travelDur;
            const hitBoat = action.other_player !== undefined;
            if (hitBoat) {
              const target = this.boatStates.get(action.other_player);
              if (target) {
                target.health = action.other_player_health;
                if (action.other_player === GI.me) this.component.currentPlayerHealth = target.health;
              }
            }
            // Explosion sprite
            this.explosions.push({
              x: ball.x1, y: ball.y1,
              startMs: impactMs,
              durationMs: impactDur,
              alive: true,
            });
            // Fire particles — more and brighter when hitting a boat
            const nParticles = hitBoat ? 18 : 8;
            const fireColors = ['#ff6600', '#ff9900', '#ffcc00', '#ff3300', '#ffee44'];
            for (let pi = 0; pi < nParticles; pi++) {
              const angle = (pi / nParticles) * Math.PI * 2 + Math.random() * 0.4;
              const speed = tileW * (0.3 + Math.random() * (hitBoat ? 0.9 : 0.5));
              const delay = Math.random() * 80;
              this.fireParticles.push({
                x: ball.x1, y: ball.y1,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed - (hitBoat ? tileH * 0.4 : 0),
                size: 3 + Math.random() * (hitBoat ? 7 : 4),
                color: fireColors[Math.floor(Math.random() * fireColors.length)],
                startMs: impactMs + delay,
                durationMs: impactDur * (0.6 + Math.random() * 0.4),
                alive: true,
              });
            }
          },
        });
        break;
      }

      // -----------------------------------------------------------------------
      case 'death': {
        if (!s) return;
        const isMe_death = action.target === GI.me;
        // Clear upgrades immediately when the boat dies, regardless of animation duration
        this.timeline.push({
          startMs,
          durationMs: 0,
          tick: () => {},
          onComplete: () => {
            s.upgrades = [];
            s.onFire = false;
            s.health = 0;
            if (isMe_death) {
              this.component.currentPlayerUpgrades = [];
              this.component.currentPlayerHealth = 0;
            }
          },
        });
        if (dur < this.animCutoff) break;
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
        const isMe_respawn = action.target === GI.me;
        if (dur < this.animCutoff) {
          s.x = tx;
          s.y = ty;
          s.angle = ta;
          s.scale = 1;
          s.health = action.health;
          if (isMe_respawn) this.component.currentPlayerHealth = s.health;
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
              if (isMe_respawn) this.component.currentPlayerHealth = s.health;
            },
          });
        }
        break;
      }

      // -----------------------------------------------------------------------
      case 'repair': {
        if (dur < this.animCutoff) return;
        const isMe_repair = action.target === GI.me;
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
            if (s) {
              s.health = action.health;
              if (isMe_repair) this.component.currentPlayerHealth = s.health;
            }
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
        const isMe_pdr = action.target === GI.me;
        this.timeline.push({
          startMs,
          durationMs: 0,
          tick: () => {},
          onComplete: () => {
            if (s) {
              s.health = action.health;
              s.frame = 1;
              if (isMe_pdr) this.component.currentPlayerHealth = s.health;
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

      // -----------------------------------------------------------------------
      case 'treasure_spawn': {
        this.timeline.push({
          startMs,
          durationMs: 0,
          tick: () => {},
          onComplete: () => {
            this.treasures.set(action.id, {
              id: action.id,
              x: action.x,
              y: action.y,
              upgrade: action.upgrade,
              spawnMs: startMs,
              alive: true,
            });
          },
        });
        break;
      }

      // -----------------------------------------------------------------------
      case 'treasure_collected': {
        this.timeline.push({
          startMs,
          durationMs: 0,
          tick: () => {},
          onComplete: () => {
            const t = this.treasures.get(action.treasure_id);
            if (t) t.alive = false;
            this.treasures.delete(action.treasure_id);
            // golden sparkle burst at chest position
            const cx = (action.posx + 0.5) * tileW;
            const cy = (action.posy + 0.5) * tileH;
            for (let pi = 0; pi < 12; pi++) {
              const angle = (pi / 12) * Math.PI * 2 + Math.random() * 0.3;
              const speed = tileW * (0.4 + Math.random() * 0.6);
              this.fireParticles.push({
                x: cx, y: cy,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed - tileH * 0.3,
                size: 4 + Math.random() * 5,
                color: Math.random() > 0.5 ? '#FFD700' : '#FFA500',
                startMs,
                durationMs: 600,
                alive: true,
              });
            }
          },
        });
        break;
      }

      // -----------------------------------------------------------------------
      case 'upgrade_gained': {
        if (!s) return;
        const isMe_gained = action.target === GI.me;
        this.timeline.push({
          startMs,
          durationMs: 0,
          tick: () => {},
          onComplete: () => {
            if (!s.upgrades) s.upgrades = [];
            const existing = s.upgrades.find((u) => u.type === action.upgrade);
            if (!existing) {
              const entry: any = { type: action.upgrade };
              if (action.charges !== undefined) entry.charges = action.charges;
              s.upgrades.push(entry);
            } else if (action.charges !== undefined) {
              existing.charges = action.charges;
            }
            if (isMe_gained) this.component.currentPlayerUpgrades = [...s.upgrades];
          },
        });
        break;
      }

      // -----------------------------------------------------------------------
      case 'upgrade_lost': {
        if (!s) return;
        const isMe_lost = action.target === GI.me;
        this.timeline.push({
          startMs,
          durationMs: 0,
          tick: () => {},
          onComplete: () => {
            if (s.upgrades) {
              s.upgrades = s.upgrades.filter((u) => u.type !== action.upgrade);
            }
            if (isMe_lost) this.component.currentPlayerUpgrades = [...(s.upgrades ?? [])];
          },
        });
        break;
      }

      // -----------------------------------------------------------------------
      case 'shield_absorb': {
        if (!s) return;
        const isMe_shield = action.target === GI.me;
        this.timeline.push({
          startMs,
          durationMs: 0,
          tick: () => {},
          onComplete: () => {
            // update shield charges on the badge
            if (s.upgrades) {
              const shieldUpg = s.upgrades.find((u) => u.type === 'shield');
              if (shieldUpg) shieldUpg.charges = action.charges;
            }
            if (isMe_shield) this.component.currentPlayerUpgrades = [...(s.upgrades ?? [])];
          },
        });
        // brief blue flash on the boat
        if (dur >= this.animCutoff) {
          this.starBursts.push({
            x: s.x, baseY: s.y, tileH, color: '#4488ff', type: 'damage',
            startMs, durationMs: dur * 0.5, alive: true,
          });
        }
        break;
      }

      // -----------------------------------------------------------------------
      case 'set_on_fire': {
        if (!s) return;
        this.timeline.push({
          startMs,
          durationMs: 0,
          tick: () => {},
          onComplete: () => { s.onFire = true; },
        });
        break;
      }

      // -----------------------------------------------------------------------
      case 'burn_damage': {
        if (!s) return;
        const isMe_burn = action.target === GI.me;
        this.timeline.push({
          startMs,
          durationMs: 0,
          tick: () => {},
          onComplete: () => {
            s.health = action.health;
            s.onFire = false;
            if (isMe_burn) this.component.currentPlayerHealth = s.health;
          },
        });
        // fire damage star burst
        if (dur >= this.animCutoff) {
          this.starBursts.push({
            x: s.x, baseY: s.y, tileH, color: '#ff4400', type: 'damage',
            startMs, durationMs: dur, alive: true,
          });
        }
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

    const PANEL_W = 192;
    const PEER_SHIFT = PANEL_W / 2 + 4; // half panel + gap

    // find clicked treasure
    let clickedTreasure: TreasureSprite | null = null;
    for (const [, t] of this.treasures) {
      if (!t.alive) continue;
      const cx = (t.x + 0.5) * tileW;
      const cy = (t.y + 0.5) * tileH;
      if (Math.abs(worldX - cx) < tileW * 0.5 && Math.abs(worldY - cy) < tileH * 0.5) {
        clickedTreasure = t;
        break;
      }
    }

    // find clicked boat
    let clickedBoat: BoatState | null = null;
    for (const [, s] of this.boatStates) {
      if (s.scale <= 0) continue;
      if (Math.abs(worldX - s.x) < tileW / 2 && Math.abs(worldY - s.y) < tileH / 2) {
        clickedBoat = s;
        break;
      }
    }

    const hasBoth = clickedTreasure !== null && clickedBoat !== null;

    if (clickedTreasure) {
      const cx = (clickedTreasure.x + 0.5) * tileW;
      const cy = (clickedTreasure.y + 0.5) * tileH;
      this.treasureTooltips = this.treasureTooltips.filter((t) => t.x !== cx || t.y !== cy);
      this.treasureTooltips.push({
        x: cx,
        y: cy,
        upgrade: GI.treasure_preview !== false ? clickedTreasure.upgrade : null,
        startMs: performance.now(),
        durationMs: 3500,
        peerOffset: hasBoth ? PEER_SHIFT : 0,
      });
    }

    if (clickedBoat) {
      const s = clickedBoat;
      this.boatTooltips = this.boatTooltips.filter((t) => t.name !== s.name);
      this.boatTooltips.push({
        x: s.x,
        y: s.y,
        color: s.color,
        name: s.name,
        health: s.health,
        maxHealth: GI.initial_health,
        nextCheckpoint: s.nextCheckpoint,
        upgrades: [
          ...(s.upgrades ?? []),
          ...(s.isCursed ? [{ type: 'odysseus_curse' }] : []),
        ],
        onFire: s.onFire ?? false,
        startMs: performance.now(),
        durationMs: 3500,
        peerOffset: hasBoth ? -PEER_SHIFT : 0,
      });
    }
  }
}
