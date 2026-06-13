#!/usr/bin/env python3
"""
Generate explosion sprite sheets for PirateRace cannon hits.

Outputs:
  backend/static/sprites/explosion.png  — 8-frame explosion (96×96 px each, 768×96 strip)
  backend/static/sprites/ember.png      — 4-frame ember/spark (24×24 px each, 96×24 strip)
"""
import os
import math
import numpy as np

OUTDIR = os.path.join(os.path.dirname(__file__), "..", "backend", "static", "sprites")
os.makedirs(OUTDIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def radial(img, cx, cy, r, color, falloff=1.8):
    """Add a soft radial glow at (cx,cy) with radius r and given RGBA color."""
    H, W = img.shape[:2]
    x = np.arange(W, dtype=np.float32)
    y = np.arange(H, dtype=np.float32)
    xx, yy = np.meshgrid(x, y)
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    a = np.clip(1 - (d / r) ** falloff, 0, 1).astype(np.float32)
    for c in range(3):
        img[:, :, c] = np.clip(img[:, :, c] + a * (color[c] / 255.0), 0, 1)
    img[:, :, 3] = np.clip(img[:, :, 3] + a * (color[3] / 255.0), 0, 1)


def ring(img, cx, cy, r, thickness, color):
    """Add a glowing ring."""
    H, W = img.shape[:2]
    x = np.arange(W, dtype=np.float32)
    y = np.arange(H, dtype=np.float32)
    xx, yy = np.meshgrid(x, y)
    d = np.abs(np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) - r)
    a = np.clip(1 - d / thickness, 0, 1).astype(np.float32)
    for c in range(3):
        img[:, :, c] = np.clip(img[:, :, c] + a * (color[c] / 255.0), 0, 1)
    img[:, :, 3] = np.clip(img[:, :, 3] + a * (color[3] / 255.0), 0, 1)


def elongated(img, cx, cy, angle_deg, length, width, color, falloff=2.0):
    """Add an elongated flame jet."""
    if length <= 0 or width <= 0:
        return
    H, W = img.shape[:2]
    x = np.arange(W, dtype=np.float32)
    y = np.arange(H, dtype=np.float32)
    xx, yy = np.meshgrid(x, y)
    dx = xx - cx
    dy = yy - cy
    angle_rad = math.radians(angle_deg)
    ca, sa = math.cos(angle_rad), math.sin(angle_rad)
    # Project onto axis and perpendicular
    along  = dx * ca + dy * sa
    perp   = -dx * sa + dy * ca
    da = np.clip(1 - (np.maximum(0, along) / length) ** falloff, 0, 1)
    dp = np.clip(1 - (np.abs(perp) / width) ** 2.0, 0, 1)
    a = (da * dp).astype(np.float32)
    for c in range(3):
        img[:, :, c] = np.clip(img[:, :, c] + a * (color[c] / 255.0), 0, 1)
    img[:, :, 3] = np.clip(img[:, :, 3] + a * (color[3] / 255.0), 0, 1)


def smoke_puff(img, cx, cy, r, grey, alpha):
    """Add a soft grey smoke puff."""
    radial(img, cx, cy, r, (grey, grey, grey, int(alpha * 255)), falloff=1.2)


def save_png(filename, frames_list):
    """Save a horizontal strip of RGBA frame arrays as a PNG file."""
    import struct, zlib

    H = frames_list[0].shape[0]
    W_total = sum(f.shape[1] for f in frames_list)

    # Combine frames into one wide image (values already 0..1 floats)
    combined = np.concatenate(frames_list, axis=1)
    combined = np.nan_to_num(combined, nan=0.0, posinf=1.0, neginf=0.0)
    px = (np.clip(combined, 0, 1) * 255).astype(np.uint8)

    def _chunk(tag, data):
        c = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", c)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", W_total, H, 8, 6, 0, 0, 0))

    # Build IDAT
    raw = b""
    for row in range(H):
        raw += b"\x00"  # filter type None
        raw += px[row].tobytes()
    idat = _chunk(b"IDAT", zlib.compress(raw, 9))
    iend = _chunk(b"IEND", b"")

    with open(filename, "wb") as f:
        f.write(sig + ihdr + idat + iend)

    print(f"  Wrote {filename}  ({W_total}x{H}, {len(frames_list)} frames)")


# ---------------------------------------------------------------------------
# Explosion sprite — 8 frames, 96×96 each
# ---------------------------------------------------------------------------

def make_explosion_frames():
    SIZE = 96
    cx = cy = SIZE / 2
    NFRAMES = 8

    # Colour palette
    WHITE  = (255, 255, 220, 255)
    YELLOW = (255, 220,  30, 255)
    ORANGE = (255, 120,  10, 255)
    DKRED  = (180,  20,   5, 255)
    SMOKE1 = ( 80,  70,  65, 255)
    SMOKE2 = ( 55,  50,  45, 255)

    # Jet angles for 5 fire jets spread around the explosion
    jet_angles = [0, 72, 144, 216, 288]

    frames = []
    for fi in range(NFRAMES):
        t = fi / (NFRAMES - 1)          # 0..1  (linear progress)
        img = np.zeros((SIZE, SIZE, 4), dtype=np.float32)

        # --- Phase 0-1: shockwave flash ---
        if t < 0.3:
            ft = t / 0.3
            flash_r = 6 + ft * 46         # core grows 6→52
            ring_r  = 8 + ft * 50
            radial(img, cx, cy, flash_r, WHITE,  falloff=1.0)
            radial(img, cx, cy, flash_r * 0.5, (255, 255, 255, 255), falloff=0.8)
            ring(img, cx, cy, ring_r, 4, (255, 230, 100, 200))

        # --- Phase 0.1-0.6: fireball ---
        fb_t = max(0, min(1, (t - 0.05) / 0.55))
        if fb_t > 0:
            decay = 1 - max(0, (t - 0.45) / 0.55)  # shrinks after peak
            fb_r  = 14 + fb_t * 32 * decay
            core_a = min(1, fb_t * 3) * decay
            # Outer orange halo
            radial(img, cx, cy, fb_r * 1.5, (ORANGE[0], ORANGE[1], ORANGE[2], int(180 * core_a)), falloff=1.5)
            # Mid orange
            radial(img, cx, cy, fb_r, (255, 140, 20, int(220 * core_a)), falloff=1.2)
            # Hot yellow core
            radial(img, cx, cy, fb_r * 0.45, (255, 230, 60, int(240 * core_a)), falloff=1.0)

        # --- Phase 0.1-0.55: fire jets ---
        jet_t = max(0, min(1, (t - 0.05) / 0.5))
        if jet_t > 0:
            jet_decay = max(0, 1 - (t - 0.3) / 0.25) if t > 0.3 else 1.0
            jet_len   = jet_t * 36 * jet_decay
            jet_w     = 6 + jet_t * 6
            jet_a     = int(min(1, jet_t * 3) * jet_decay * 255)
            for ang in jet_angles:
                elongated(img, cx, cy, ang,       jet_len,       jet_w,       (255, 100, 10, jet_a))
                elongated(img, cx, cy, ang + 180, jet_len * 0.6, jet_w * 0.7, (255, 140, 30, jet_a))
            # Diagonal mini-jets
            for ang in [36, 108, 180, 252, 324]:
                elongated(img, cx, cy, ang, jet_len * 0.6, jet_w * 0.55, (200, 60, 5, int(jet_a * 0.7)))

        # --- Phase 0.35-1.0: dark red embers & smoke ---
        ember_t = max(0, (t - 0.35) / 0.65)
        if ember_t > 0:
            ember_a = min(1, ember_t * 2) * (1 - ember_t * 0.5)
            radial(img, cx, cy, 28, (DKRED[0], DKRED[1], DKRED[2], int(180 * ember_a)), falloff=1.4)

        # --- Phase 0.45-1.0: smoke puffs ---
        smoke_t = max(0, (t - 0.45) / 0.55)
        if smoke_t > 0:
            sa = smoke_t * (1 - smoke_t * 0.4)
            smoke_r = 12 + smoke_t * 38
            # Multiple offset smoke puffs
            rng = np.random.RandomState(fi * 7)
            for _ in range(4):
                ox = rng.uniform(-smoke_r * 0.3, smoke_r * 0.3)
                oy = rng.uniform(-smoke_r * 0.5, smoke_r * 0.1)   # drift upward
                smoke_puff(img, cx + ox, cy + oy, smoke_r * rng.uniform(0.5, 0.9),
                           rng.randint(50, 85), sa * rng.uniform(0.5, 0.9))

        frames.append(img)

    return frames


# ---------------------------------------------------------------------------
# Ember sprite — 4 frames, 24×24 each (tiny glowing sparks)
# ---------------------------------------------------------------------------

def make_ember_frames():
    SIZE = 24
    cx = cy = SIZE / 2
    NFRAMES = 4

    frames = []
    for fi in range(NFRAMES):
        t = fi / (NFRAMES - 1)
        img = np.zeros((SIZE, SIZE, 4), dtype=np.float32)

        # Pulsing ember: bright → dim → gone
        brightness = math.sin(t * math.pi)
        r = 2 + brightness * 5
        a = int(brightness * 255)

        radial(img, cx, cy, r + 4, (255, 100, 10, int(a * 0.4)), falloff=1.0)
        radial(img, cx, cy, r, (255, 180, 40, a), falloff=0.9)
        radial(img, cx, cy, r * 0.4, (255, 255, 200, a), falloff=0.7)
        frames.append(img)

    return frames


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Generating explosion sprites...")

    exp_frames = make_explosion_frames()
    save_png(os.path.join(OUTDIR, "explosion.png"), exp_frames)

    ember_frames = make_ember_frames()
    save_png(os.path.join(OUTDIR, "ember.png"), ember_frames)

    print("Done.")
